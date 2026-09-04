#!/usr/bin/env python3
"""Run a bounded generator-evaluator-rewriter loop with an immutable ledger.

Configuration commands are JSON token arrays. Available placeholders:
{reference}, {prompt_file}, {candidate_path}, {score_file}, {feedback_file},
{next_prompt_file}, {iteration}, {candidate}, {seed}, and {run_dir}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_WEIGHTS = {
    "semantic": 0.22,
    "composition": 0.14,
    "motion": 0.18,
    "camera": 0.14,
    "style": 0.12,
    "temporal": 0.16,
    "audio": 0.04,
}
SECRET_MARKERS = ("api_key", "apikey", "token", "secret", "authorization", "bearer")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def render_command(tokens: object, values: dict[str, object]) -> list[str]:
    if not isinstance(tokens, list) or not tokens or not all(isinstance(item, str) for item in tokens):
        raise ValueError("each command must be a non-empty JSON array of strings")
    try:
        return [item.format_map(values) for item in tokens]
    except KeyError as exc:
        raise ValueError(f"unknown command placeholder: {exc}") from exc


def redacted(command: list[str]) -> list[str]:
    result: list[str] = []
    redact_next = False
    for token in command:
        lowered = token.lower()
        if redact_next:
            result.append("<redacted>")
            redact_next = False
        elif any(marker in lowered for marker in SECRET_MARKERS):
            if "=" in token:
                result.append(token.split("=", 1)[0] + "=<redacted>")
            else:
                result.append(token)
                redact_next = True
        else:
            result.append(token)
    return result


def execute(command: list[str], stdout_path: Path, stderr_path: Path, timeout: float | None) -> tuple[int, float]:
    started = time.monotonic()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout, shell=False)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        return completed.returncode, time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text((exc.stderr or "") + "\nTIMEOUT\n", encoding="utf-8")
        return 124, time.monotonic() - started


def parse_scores(path: Path, weights: dict[str, float]) -> tuple[dict[str, float], float, object]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    scores = raw.get("scores") if isinstance(raw, dict) else None
    if not isinstance(scores, dict):
        raise ValueError("evaluator JSON must contain an object named 'scores'")
    normalized: dict[str, float] = {}
    for name, weight in weights.items():
        if weight == 0:
            continue
        value = scores.get(name)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"score '{name}' must be numeric within [0, 1]")
        normalized[name] = float(value)
    weight_sum = sum(weights[name] for name in normalized)
    if weight_sum <= 0:
        raise ValueError("score weights must sum to a positive value")
    aggregate = sum(normalized[name] * weights[name] for name in normalized) / weight_sum
    return normalized, aggregate, raw


def fail(ledger_path: Path, ledger: dict, reason: str, detail: str) -> int:
    ledger["status"] = "failed"
    ledger["stop_reason"] = reason
    ledger["error"] = detail
    atomic_json(ledger_path, ledger)
    print(f"ERROR: {reason}: {detail}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    reference = args.reference.resolve()
    initial_prompt = args.prompt.resolve()
    config_path = args.config.resolve()
    output_dir = args.output_dir.resolve()
    for path, label in ((reference, "reference"), (initial_prompt, "prompt"), (config_path, "config")):
        if not path.is_file():
            parser.error(f"{label} file not found: {path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"output directory must be new or empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    target = config.get("target", {})
    if not isinstance(target, dict) or not target.get("model") or not target.get("version"):
        parser.error("config.target must lock non-empty model and version values")
    generator = config.get("generator", {})
    evaluator = config.get("evaluator", {})
    rewriter = config.get("rewriter")
    if not isinstance(generator, dict) or "command" not in generator:
        parser.error("config.generator.command is required")
    if not isinstance(evaluator, dict) or "command" not in evaluator:
        parser.error("config.evaluator.command is required")

    iterations = int(config.get("max_iterations", 3))
    candidate_count = int(config.get("candidates_per_iteration", 3))
    base_seed = int(config.get("base_seed", 1000))
    target_score = float(config.get("target_score", 0.85))
    min_improvement = float(config.get("min_improvement", 0.01))
    patience = int(config.get("patience", 2))
    timeout = config.get("command_timeout_seconds")
    timeout = float(timeout) if timeout is not None else None
    if not (1 <= iterations <= 20 and 1 <= candidate_count <= 20 and 0 <= target_score <= 1 and patience >= 1):
        parser.error("invalid loop bounds or target score")
    weights = config.get("score_weights", DEFAULT_WEIGHTS)
    if not isinstance(weights, dict) or not weights:
        parser.error("score_weights must be a non-empty object")
    weights = {str(key): float(value) for key, value in weights.items()}
    if any(value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        parser.error("score weights must be non-negative and sum to a positive value")

    locked_config = output_dir / "config.lock.json"
    shutil.copy2(config_path, locked_config)
    prompt_zero = output_dir / "prompt_000.txt"
    shutil.copy2(initial_prompt, prompt_zero)
    ledger_path = output_dir / "ledger.json"
    ledger: dict = {
        "ledger_version": "1.0",
        "status": "running",
        "stop_reason": None,
        "locked": {
            "reference": str(reference),
            "reference_sha256": file_hash(reference),
            "config_sha256": file_hash(locked_config),
            "target": target,
            "score_weights": weights,
            "base_seed": base_seed,
        },
        "iterations": [],
    }
    atomic_json(ledger_path, ledger)

    current_prompt = prompt_zero
    global_best = -1.0
    plateau_count = 0
    extension = str(generator.get("candidate_extension", ".mp4"))
    if not extension.startswith(".") or any(char in extension for char in "/\\"):
        return fail(ledger_path, ledger, "invalid_candidate_extension", extension)

    for iteration in range(1, iterations + 1):
        run_dir = output_dir / f"iteration_{iteration:03d}"
        run_dir.mkdir()
        prompt_copy = run_dir / "prompt.txt"
        shutil.copy2(current_prompt, prompt_copy)
        iteration_record: dict = {
            "iteration": iteration,
            "prompt_path": str(prompt_copy),
            "prompt_sha256": file_hash(prompt_copy),
            "candidates": [],
        }
        ledger["iterations"].append(iteration_record)
        atomic_json(ledger_path, ledger)

        for candidate_number in range(1, candidate_count + 1):
            seed = base_seed + (iteration - 1) * candidate_count + candidate_number - 1
            candidate_path = run_dir / f"candidate_{candidate_number:03d}{extension}"
            score_path = run_dir / f"candidate_{candidate_number:03d}.scores.json"
            values = {
                "reference": str(reference), "prompt_file": str(prompt_copy),
                "candidate_path": str(candidate_path), "score_file": str(score_path),
                "feedback_file": str(score_path), "next_prompt_file": "",
                "iteration": iteration, "candidate": candidate_number, "seed": seed,
                "run_dir": str(run_dir),
            }
            candidate_record: dict = {"candidate": candidate_number, "seed": seed, "status": "generating"}
            iteration_record["candidates"].append(candidate_record)
            atomic_json(ledger_path, ledger)

            try:
                generate_command = render_command(generator["command"], values)
            except ValueError as exc:
                return fail(ledger_path, ledger, "generator_config_error", str(exc))
            candidate_record["generator_command"] = redacted(generate_command)
            code, elapsed = execute(generate_command, candidate_path.with_suffix(".generate.stdout.txt"), candidate_path.with_suffix(".generate.stderr.txt"), timeout)
            candidate_record["generation_seconds"] = round(elapsed, 3)
            if code != 0 or not candidate_path.is_file():
                candidate_record["status"] = "generation_failed"
                candidate_record["returncode"] = code
                return fail(ledger_path, ledger, "generator_failure", f"iteration {iteration}, candidate {candidate_number}")
            candidate_record["video_path"] = str(candidate_path)
            candidate_record["video_sha256"] = file_hash(candidate_path)

            try:
                evaluate_command = render_command(evaluator["command"], values)
            except ValueError as exc:
                return fail(ledger_path, ledger, "evaluator_config_error", str(exc))
            candidate_record["evaluator_command"] = redacted(evaluate_command)
            code, elapsed = execute(evaluate_command, score_path.with_suffix(".evaluate.stdout.txt"), score_path.with_suffix(".evaluate.stderr.txt"), timeout)
            candidate_record["evaluation_seconds"] = round(elapsed, 3)
            if code != 0 or not score_path.is_file():
                candidate_record["status"] = "evaluation_failed"
                candidate_record["returncode"] = code
                return fail(ledger_path, ledger, "evaluator_failure", f"iteration {iteration}, candidate {candidate_number}")
            try:
                scores, aggregate, _ = parse_scores(score_path, weights)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                candidate_record["status"] = "invalid_evaluation"
                return fail(ledger_path, ledger, "invalid_evaluation", str(exc))
            candidate_record.update({"status": "scored", "scores": scores, "aggregate": round(aggregate, 6)})
            atomic_json(ledger_path, ledger)

        best = max(iteration_record["candidates"], key=lambda item: item["aggregate"])
        iteration_best = float(best["aggregate"])
        iteration_record["best_candidate"] = best["candidate"]
        iteration_record["best_aggregate"] = iteration_best
        improvement = iteration_best - global_best if global_best >= 0 else None
        iteration_record["improvement_over_previous_global_best"] = improvement
        if global_best >= 0 and improvement is not None and improvement < min_improvement:
            plateau_count += 1
        else:
            plateau_count = 0
        global_best = max(global_best, iteration_best)
        atomic_json(ledger_path, ledger)

        if iteration_best >= target_score:
            ledger.update({"status": "complete", "stop_reason": "target_score_reached", "best_aggregate": global_best})
            atomic_json(ledger_path, ledger)
            print(ledger_path)
            return 0
        if plateau_count >= patience:
            ledger.update({"status": "complete", "stop_reason": "plateau", "best_aggregate": global_best})
            atomic_json(ledger_path, ledger)
            print(ledger_path)
            return 0
        if iteration == iterations:
            ledger.update({"status": "complete", "stop_reason": "maximum_iterations", "best_aggregate": global_best})
            atomic_json(ledger_path, ledger)
            print(ledger_path)
            return 0
        if not isinstance(rewriter, dict) or "command" not in rewriter:
            ledger.update({"status": "complete", "stop_reason": "no_rewriter_configured", "best_aggregate": global_best})
            atomic_json(ledger_path, ledger)
            print(ledger_path)
            return 0

        next_prompt = output_dir / f"prompt_{iteration:03d}.txt"
        best_score = run_dir / f"candidate_{int(best['candidate']):03d}.scores.json"
        rewrite_values = {
            "reference": str(reference), "prompt_file": str(prompt_copy),
            "candidate_path": best["video_path"], "score_file": str(best_score),
            "feedback_file": str(best_score), "next_prompt_file": str(next_prompt),
            "iteration": iteration, "candidate": best["candidate"], "seed": best["seed"],
            "run_dir": str(run_dir),
        }
        try:
            rewrite_command = render_command(rewriter["command"], rewrite_values)
        except ValueError as exc:
            return fail(ledger_path, ledger, "rewriter_config_error", str(exc))
        iteration_record["rewriter_command"] = redacted(rewrite_command)
        code, elapsed = execute(rewrite_command, run_dir / "rewrite.stdout.txt", run_dir / "rewrite.stderr.txt", timeout)
        iteration_record["rewrite_seconds"] = round(elapsed, 3)
        if code != 0 or not next_prompt.is_file() or not next_prompt.read_text(encoding="utf-8-sig").strip():
            return fail(ledger_path, ledger, "rewriter_failure", f"iteration {iteration}")
        iteration_record["next_prompt_sha256"] = file_hash(next_prompt)
        current_prompt = next_prompt
        atomic_json(ledger_path, ledger)

    return fail(ledger_path, ledger, "internal_error", "loop exited without a stop reason")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

