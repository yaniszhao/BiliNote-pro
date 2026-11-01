# 变更记录：LLM 思考强度（reasoning_effort）支持

时间：2026-11-01，提交 `5a460c9`。记录一次跨后端/前端/插件的 LLM 调用参数打通。

## 背景

推理模型（GLM、Qwen thinking、OpenAI o/gpt-5 系列等）支持 `reasoning_effort`
参数控制推理深度，但 BiliNote 的请求链路一直没暴露它，模型只能跑默认强度——
生成慢、费用高时没有调节手段。

## 实现方案

### 核心层（`backend/app/gpt/universal_gpt.py`）

- `UniversalGPT.__init__` 新增 `reasoning_effort: str | None = "low"`；
- `_do_create` 把参数随 `chat.completions.create` 下发；
- **自动降级**：供应商返回的错误信息里含 `reasoning_effort` 时，去掉该参数重试
  一次（与既有 `_is_temperature_unsupported_error` 降级同模式，普通模型不认这个
  参数也不会失败）；
- **缓存签名**：`_build_source_signature` 纳入 reasoning_effort，强度变化不会
  命中旧 checkpoint 缓存；
- `reasoning_effort=None` 时不传该参数，走模型端默认。

### 请求链路（backend）

```
VideoRequest.reasoning_effort（默认 "low"，Pydantic 校验 low/medium/high）
  → run_note_task → NoteGenerator.generate(_get_gpt(model, provider, effort))
  → ModelConfig.reasoning_effort → GPTFactory.from_config（None 兜底 "low"）
  → UniversalGPT
```

RAG 问答同步支持：`AskRequest` → `chat_service()`。

### 前端（Web + 插件）

- Web：`NoteForm` 新增「思考强度」下拉（常量 `src/constant/note.ts`），提交时随
  form 发送；`ChatPanel` 问答从 `currentTask.formData.reasoning_effort` 透传；
- 插件：`Settings` 新增字段 + 默认 `'low'`（`logic/constants.ts`），设置页
  `General.vue` 新增下拉，Popup / background 提交时带上。

### 日志

- 任务入口：`开始生成笔记 (task_id=..., model=..., provider_id=..., reasoning_effort=...)`
- LLM 首次调用：`LLM 调用参数: model=..., reasoning_effort=..., temperature=0.7`
  （每次实例只记一次，避免刷屏）

## 测试覆盖（`backend/tests/test_universal_gpt_reasoning_effort.py`，6 用例）

- 配置了 effort 时 create 调用带参数
- 模型不认识时自动去参重试并成功
- None 时不传参数
- 不认参模型 + effort 联合降级（temperature 先被拒，effort 后被拒）
- checkpoint 签名：不同 effort 签名不同，同 effort 签名一致

## 已知边界

- 前端提交的 reasoning_effort 存进 task formData 并持久化到
  `{task_id}_meta.json`（配合历史恢复功能），重试/问答都会带上生成时的强度
- 非 OpenAI 兼容供应商对参数名的接受程度不一，统一按「报错 → 去参重试」兜底，
  日志里能看出实际生效参数
