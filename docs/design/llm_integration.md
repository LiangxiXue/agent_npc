# Optional LLM Integration

项目默认运行在 `mock` 模式，保证无 API key 时也能测试、演示和评分。OpenAI-compatible 模式是实验增强路径。

## Default Mode

```powershell
streamlit run app.py
```

默认 provider：

```text
AGENT_NPC_LLM_PROVIDER=mock
```

在该模式下，`src/agent/decision.py` 使用确定性 structured decisions，`src/agent/response.py` 使用模板 fallback，Memory Policy 使用规则候选和程序 gate。

## OpenAI-Compatible Setup

`.env.example` 中提供默认字段：

```text
AGENT_NPC_LLM_PROVIDER=mock
AGENT_NPC_LLM_API_KEY=
AGENT_NPC_LLM_MODEL=gpt-4o-mini
AGENT_NPC_LLM_BASE_URL=https://api.openai.com/v1
AGENT_NPC_LLM_TIMEOUT=60
AGENT_NPC_LLM_RETRIES=1
AGENT_NPC_MEMORY_LLM_ENABLED=1
```

PowerShell 示例：

```powershell
$env:AGENT_NPC_LLM_PROVIDER = "openai_compatible"
$env:AGENT_NPC_LLM_API_KEY = "your_api_key"
$env:AGENT_NPC_LLM_MODEL = "gpt-4o-mini"
$env:AGENT_NPC_LLM_BASE_URL = "https://api.openai.com/v1"
$env:AGENT_NPC_LLM_TIMEOUT = "60"
$env:AGENT_NPC_LLM_RETRIES = "1"
streamlit run app.py
```

DeepSeek 等兼容服务只需替换 model 和 base URL。

## Four LLM Touchpoints

真实 LLM 可参与四个位置：

1. **Structured decision**：生成 intent、reasoning、social metadata、response keywords 和 tools。
2. **Response polish**：工具执行后，根据最新状态和 canonical facts 润色最终 NPC 回复。
3. **Memory candidate generation**：后台 memory job 中提出长期记忆候选。
4. **Memory candidate review**：后台 memory job 中审查候选证据、主语、类型和过度推断风险。

这四个位置共享 `src/agent/llm_client.py` 的 OpenAI-compatible HTTP client。

## Decision Contract

LLM decision 必须返回 JSON，核心字段：

```text
intent
reasoning
memory_policy
social_intent
social_stance
response_style
response_keywords
tools
```

当前允许的 intent 包括：

```text
start_lost_key_quest
complete_lost_key_quest
reveal_ruins_entrance
withhold_ruins_entrance
start_gate_badge_quest
complete_gate_badge_quest
start_ancient_notes_quest
complete_ancient_notes_quest
start_relic_tip_quest
complete_relic_tip_quest
redirect_ruins_inquiry
probe_for_evidence
general_conversation
```

允许工具：

```text
update_trust
update_affection
give_item
update_quest_status
unlock_location
record_world_event
```

LLM 不返回也不猜测 `state_before` / `state_after`。这些状态由 workflow 从 SQLite 读取后写入 trace。

## Decision Safety

所有 LLM decision 都经过：

```text
validate_decision()
-> normalize_intent()
-> normalize_social_fields()
-> validate_tool_call()
-> validate_decision_business_rules()
-> apply_task_state_machine()
```

程序会阻止：

- unsupported intent/tool；
- invalid tool args；
- `not_started -> completed` 直接跳跃；
- 一个 NPC 修改另一个 NPC 的任务；
- `withhold` / `probe` / `redirect` 等意图偷偷解锁地点；
- Sable 的 deceptive dialogue 变成 canonical ruins unlock。

如果失败，系统回退到 mock decision，并在 trace 中记录 `llm_fallback` 或 `state_machine.blocked`。

## Response Polishing

`src/agent/response.py` 在工具执行后调用 LLM。输入包括：

- player input；
- intent、reasoning、social stance；
- `response_style` / `response_keywords`；
- 最新 NPC / player / quest state；
- canonical world facts；
- retrieved lore；
- retrieved memories；
- tool calls 和 state changes。

返回格式：

```json
{
  "npc_response": "NPC 的最终中文回复"
}
```

如果回复违反重大事实，例如错误透露遗迹入口、虚构解锁地点或改变任务结果，系统回退到 deterministic template。

## Memory Candidate And Review

后台 memory job 处理时可调用：

```text
src/agent/llm_memory_candidate.py
src/agent/memory_candidate_review.py
```

它们只生成和审查候选，不直接写 SQLite。最终写入仍由 `memory_candidate_gate.py` 和 `memory_policy.py` 控制。

## Runtime Verification

检查 provider 状态：

```powershell
python -c "from src.agent.llm_client import get_provider_status; print(get_provider_status())"
```

测试 API 连通性：

```powershell
python scripts/test_llm_api.py
```

即使真实 API 失败，mock 模式、测试和基础演示仍应保持可运行。
