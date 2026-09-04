# Bounded generate-compare-rewrite protocol

Use this mode only when the user has supplied or authorized a callable generator and evaluator. Lock one target model and experiment configuration before spending generation credits or GPU time.

## Inputs

- immutable reference video and SHA-256;
- validated analysis spec;
- target model name and exact version/checkpoint;
- generator command adapter;
- evaluator command adapter;
- optional prompt rewriter command adapter;
- candidate count, seed schedule, score weights, target score, maximum iterations, and plateau rule.

The command configuration is JSON. Each command is a token array, never a shell string. Supported placeholders are documented by `scripts/closed_loop.py --help`. Start from [closed_loop_config.example.json](closed_loop_config.example.json), replace every executable path and checkpoint placeholder, and save it outside the skill before running.

## Evaluation dimensions

Require evaluator output with normalized scores in `[0, 1]`:

- `semantic`: subject archetype, environment, action and event order;
- `composition`: framing, foreground/midground/background and spatial relationships;
- `motion`: subject trajectory, speed, timing and physical contact;
- `camera`: shot size, camera path, angle and cut pattern;
- `style`: palette, lighting, texture, depth of field and material response;
- `temporal`: identity, wardrobe, background and geometry consistency;
- `audio`: rhythm, ambience, effects, speech function and synchronization, when applicable.

Use an explicit weighted aggregate. Store raw component scores and evaluator evidence; a single opaque similarity number is insufficient.

## Iteration policy

1. Generate `N` candidates from the same prompt using a recorded deterministic seed schedule when the backend supports seeds.
2. Evaluate every completed candidate. Failed generations remain in the ledger with their error class.
3. Select the best candidate by the fixed weighted aggregate.
4. Diagnose the largest supported score gaps. Revise only the relevant prompt clauses; retain already successful anchors.
5. Generate the next batch from the revised prompt.

Stop when any condition occurs:

- aggregate score reaches the configured target;
- maximum iterations is reached;
- best score improves by less than `min_improvement` for `patience` consecutive iterations;
- generator, evaluator, or rewriter fails;
- the remaining mismatch needs reference assets or structural controls rather than prompt changes.

Do not cherry-pick evaluator weights after seeing candidates. Do not switch target models or silently rerun failed candidates. Start a new experiment directory when changing the locked configuration.

## Output ledger

Retain:

- configuration and source hashes;
- every prompt revision and prompt hash;
- commands with secrets redacted;
- candidate paths, hashes, seeds, status and runtime;
- raw evaluator JSON and aggregate calculation;
- chosen candidate per iteration;
- stop reason and remaining mismatches.
