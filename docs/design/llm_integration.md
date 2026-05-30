# LLM-Required Runtime Integration

面向玩家的主回合运行时要求使用 OpenAI-compatible LLM 配置。也就是说，本地应用、演示和真实对话流程需要：

```text
AGENT_NPC_LLM_PROVIDER=openai_compatible
AGENT_NPC_LLM_API_KEY=<configured API key>
```

如果某个运行时组件存在 deterministic substitute 与 LLM 分支，玩家可见的主流程必须走 LLM 分支。允许保持本地确定性的例外只有 local classification、task-state-machine validation、schema validation 和 business-rule enforcement。单元测试可以 patch OpenAI-compatible 调用以避免网络请求，但不应把主回合 workflow 配成 provider mock。

## OpenAI-Compatible Setup

`.env.example` 中应提供这些字段：

```text
AGENT_NPC_LLM_PROVIDER=openai_compatible
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
```

DeepSeek 等兼容服务只需替换 model 和 base URL。

## Four LLM Touchpoints

主运行时 LLM 参与四个位置：

1. **Structured decision**：生成 intent、reasoning、social metadata、response keywords 和 tools。
2. **Response polish**：工具执行后，根据最新状态和 canonical facts 润色最终 NPC 回复。
3. **Memory candidate generation**：后台 memory job 中提出长期记忆候选。
4. **Memory candidate review**：后台 memory job 中审查候选证据、主语、类型和过度推断风险。

这四个位置共享 `src/agent/llm_client.py` 的 OpenAI-compatible HTTP client。

长期记忆候选当前使用四类主类型：

```text
semantic
episodic
relational
procedural
```

候选还会携带 `facets`、`scope`、`evidence_text`、`stability` 和 `future_usefulness`。最终是否写入仍由程序 gate、去重和 SQLite 写入逻辑控制。

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

这些步骤是 deterministic validator，不是模型替身。LLM decision 失败不能回退到 deterministic model decision；运行时应返回受约束的错误路径。任务状态机或业务规则阻止动作时，trace 会记录 validation/blocking 信息，环境不会执行被拒绝的状态变更。

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

如果回复违反重大事实，例如错误透露遗迹入口、虚构解锁地点或改变任务结果，系统会阻止或约束该回复，避免向玩家声称环境没有执行的结果。

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

测试可通过 patch OpenAI-compatible 调用保持离线可运行。真实本地应用运行需要配置可用 API key；主回合 runtime 不再以 deterministic substitute 作为默认模型路径。
