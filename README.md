# Video Prompt Reverse

[English](#english) · [简体中文](#简体中文)

<a id="english"></a>

## English

`video-prompt-reverse` is a Codex skill for reverse-engineering a supplied video into a shot-by-shot generation specification, evidence frames, and paired Chinese-English prompt packages.

It supports generic prompt adaptation and model-oriented workflows for Veo, Sora, Kling, and Wan. It focuses on semantic and cinematic similarity; text prompts alone cannot guarantee frame-identical reconstruction.

### Install in Codex

Copy this repository into:

```text
%USERPROFILE%\.codex\skills\video-prompt-reverse
```

The skill is activated by requests such as “视频反推提示词”, “视频转提示词”, and “video-to-prompt”.

### Contents

- `SKILL.md` — skill instructions and invocation rules
- `agents/openai.yaml` — Codex agent metadata
- `references/` — analysis contract, model adapters, and optimization guidance
- `scripts/` — video probing, prompt compilation, validation, and bounded-loop utilities

### Community link

For more AI and developer discussions, visit [Linux Do](https://linux.do/).

<a id="简体中文"></a>

## 简体中文

`video-prompt-reverse` 是一个 Codex skill，用于将视频反向拆解为逐镜头生成规格、带证据的视频帧，以及中英文成对的提示词包。

它支持通用提示词适配，并可面向 Veo、Sora、Kling 和 Wan 等模型工作。它侧重语义与电影感相似度；仅凭文字提示词无法保证逐帧一致的重建结果。

### 在 Codex 中安装

将本仓库复制到：

```text
%USERPROFILE%\.codex\skills\video-prompt-reverse
```

当用户提出“视频反推提示词”“视频转提示词”“从视频生成提示词”或 “video-to-prompt” 等请求时即可触发此 skill。

### 目录内容

- `SKILL.md`：skill 说明与调用规则
- `agents/openai.yaml`：Codex agent 元数据
- `references/`：分析契约、模型适配器与优化流程说明
- `scripts/`：视频探测、提示词编译、校验与有限闭环工具

### 社区友链

欢迎访问 [Linux Do](https://linux.do/)，参与 AI 与开发者社区交流。

[返回 English](#english)

---

This project produces reverse-engineered generation specifications. It does not claim to recover a source video's original prompt.
