# Video to Generation Spec

Codex skill for reverse-engineering a supplied video into a shot-by-shot generation specification, evidence frames, and paired Chinese-English prompt packages.

## Install in Codex

Install the repository root as a skill, or copy this repository into:

```text
%USERPROFILE%\.codex\skills\video-to-generation-spec
```

The skill is activated by requests such as “视频反推提示词”, “视频转提示词”, and “video-to-prompt”.

## Contents

- `SKILL.md` — skill instructions and invocation rules
- `agents/openai.yaml` — Codex agent metadata
- `references/` — analysis contract, model adapters, and optimization guidance
- `scripts/` — video probing, prompt compilation, validation, and bounded-loop utilities

This project produces reverse-engineered generation specifications; it does not claim to recover a source video's original prompt or guarantee pixel-identical reconstruction.
