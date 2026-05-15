from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

EVAL_DIR = PROJECT_ROOT / "data" / "eval"
EVAL_DB_PATH = EVAL_DIR / "memory_eval_state.db"

os.environ["AGENT_NPC_LLM_PROVIDER"] = "mock"
os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
os.environ["AGENT_NPC_DB_PATH"] = str(EVAL_DB_PATH)

from src.agent.embedding_client import get_embedding_settings  # noqa: E402
from src.agent.workflow import run_agent_turn  # noqa: E402
from src.storage import database  # noqa: E402


REPORT_JSON = EVAL_DIR / "memory_eval_report.json"
SUMMARY_MD = EVAL_DIR / "memory_eval_summary.md"


@dataclass(frozen=True)
class Variant:
    name: str
    retrieval_mode: str
    memory_policy_enabled: bool
    description: str


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    runner: Callable[[Variant], dict[str, Any]]


VARIANTS = [
    Variant(
        name="no_long_term_memory",
        retrieval_mode="off",
        memory_policy_enabled=False,
        description="Disables long-term memory retrieval and long-term memory writes.",
    ),
    Variant(
        name="legacy_keyword_memory",
        retrieval_mode="legacy",
        memory_policy_enabled=True,
        description="Uses long-term memory writes, but retrieves by legacy keyword/tag scoring.",
    ),
    Variant(
        name="typed_memory_policy",
        retrieval_mode="typed",
        memory_policy_enabled=True,
        description="Uses typed long-term memory, Memory Policy, confidence, and query-intent scoring.",
    ),
    Variant(
        name="semantic_rag",
        retrieval_mode="semantic",
        memory_policy_enabled=True,
        description="Uses deterministic embedding retrieval over NPC long-term memories.",
    ),
    Variant(
        name="hybrid_rag",
        retrieval_mode="hybrid",
        memory_policy_enabled=True,
        description="Combines typed rule scoring with deterministic semantic retrieval.",
    ),
]


def run_turn(player_input: str, variant: Variant):
    return run_agent_turn(
        player_input,
        memory_retrieval_mode=variant.retrieval_mode,
        memory_policy_enabled=variant.memory_policy_enabled,
    )


def run_plain_chat(variant: Variant) -> dict[str, Any]:
    run = run_turn("你好，Lina。", variant)
    return build_result(
        variant=variant,
        runs=[run],
        expected={
            "no_long_term_memory_written": True,
            "short_term_interaction_written": True,
            "intent": "general_conversation",
        },
        checks={
            "no_long_term_memory_written": len(run.memory_writes) == 0,
            "short_term_interaction_written": len(database.get_recent_interactions(limit=5)) == 1,
            "intent": run.decision["intent"] == "general_conversation",
        },
    )


def run_key_return(variant: Variant) -> dict[str, Any]:
    run = run_turn("我把你丢失的钥匙找回来了。", variant)
    memory_types = get_memory_write_types(run)
    policy_expected = variant.memory_policy_enabled
    return build_result(
        variant=variant,
        runs=[run],
        expected={
            "intent": "complete_lost_key_quest",
            "trust_updated": True,
            "quest_completed": True,
            "typed_long_term_memory_written": policy_expected,
        },
        checks={
            "intent": run.decision["intent"] == "complete_lost_key_quest",
            "trust_updated": database.get_npc("lina")["trust"] >= 30,
            "quest_completed": database.get_quest("lost_key")["status"] == "completed",
            "typed_long_term_memory_written": (
                {"quest", "event", "relationship"} <= set(memory_types)
                if policy_expected
                else len(run.memory_writes) == 0
            ),
        },
    )


def run_followup_ruins_after_key(variant: Variant) -> dict[str, Any]:
    first = run_turn("我把你丢失的钥匙找回来了。", variant)
    second = run_turn("上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？", variant)
    return build_result(
        variant=variant,
        runs=[first, second],
        expected={
            "reveals_entrance": True,
            "retrieves_long_term_memory_when_enabled": variant.retrieval_mode != "off",
            "retrieval_explainable_when_enabled": variant.retrieval_mode != "off",
        },
        checks={
            "reveals_entrance": second.decision["intent"] == "reveal_ruins_entrance",
            "retrieves_long_term_memory_when_enabled": (
                len(second.retrieved_memories) > 0
                if variant.retrieval_mode != "off"
                else len(second.retrieved_memories) == 0
            ),
            "retrieval_explainable_when_enabled": (
                all("retrieval_reason" in memory for memory in second.retrieved_memories)
                if variant.retrieval_mode != "off"
                else True
            ),
        },
    )


def run_memory_only_ruins_gate(variant: Variant) -> dict[str, Any]:
    if variant.memory_policy_enabled:
        database.add_memory(
            npc_id="lina",
            content="Player returned Lina's lost key.",
            importance=8,
            tags=["event", "help", "lost_key"],
            memory_type="event",
            confidence=1.0,
        )
    run = run_turn("我之前帮过你，现在能告诉我地下遗迹入口吗？", variant)
    expected_reveal = variant.retrieval_mode != "off" and variant.memory_policy_enabled
    return build_result(
        variant=variant,
        runs=[run],
        expected={
            "memory_can_gate_sensitive_information": expected_reveal,
            "low_trust_without_memory_withholds": not expected_reveal,
        },
        checks={
            "memory_can_gate_sensitive_information": (
                run.decision["intent"] == "reveal_ruins_entrance"
                if expected_reveal
                else run.decision["intent"] == "withhold_ruins_entrance"
            ),
            "retrieved_seed_memory": (
                any("lost_key" in memory.get("tags", []) for memory in run.retrieved_memories)
                if expected_reveal
                else len(run.retrieved_memories) == 0
            ),
        },
    )


def run_preference_memory(variant: Variant) -> dict[str, Any]:
    run = run_turn("以后请直接告诉我线索，不要绕弯子。", variant)
    writes_preference = any(
        write["arguments"].get("memory_type") == "preference"
        for write in run.memory_writes
    )
    return build_result(
        variant=variant,
        runs=[run],
        expected={
            "preference_memory_written_when_policy_enabled": variant.memory_policy_enabled,
        },
        checks={
            "preference_memory_written_when_policy_enabled": (
                writes_preference if variant.memory_policy_enabled else not writes_preference
            ),
        },
    )


def run_duplicate_key_return(variant: Variant) -> dict[str, Any]:
    first = run_turn("我把你丢失的钥匙找回来了。", variant)
    database.update_quest_status("lost_key", "not_started")
    second = run_turn("我又把你丢失的钥匙找回来了。", variant)
    duplicate_detected = any(
        candidate.get("reason") == "Similar memory already exists."
        for candidate in second.memory_policy["candidates"]
    )
    return build_result(
        variant=variant,
        runs=[first, second],
        expected={
            "duplicate_memory_detected_when_policy_enabled": variant.memory_policy_enabled,
        },
        checks={
            "duplicate_memory_detected_when_policy_enabled": (
                duplicate_detected if variant.memory_policy_enabled else len(second.memory_writes) == 0
            ),
        },
    )


def run_short_term_context(variant: Variant) -> dict[str, Any]:
    first = run_turn("你好，Lina。", variant)
    second = run_turn("刚才我是在和你打招呼。", variant)
    return build_result(
        variant=variant,
        runs=[first, second],
        expected={
            "second_turn_has_short_term_context": True,
            "plain_chat_does_not_write_long_term_memory": True,
        },
        checks={
            "second_turn_has_short_term_context": len(second.recent_context) == 1,
            "plain_chat_does_not_write_long_term_memory": len(database.get_recent_memories(limit=10)) == 0,
        },
    )


def run_implicit_help_reference(variant: Variant) -> dict[str, Any]:
    seed_open_expression_memories()
    run = run_turn("我之前替你解决过那个麻烦，现在能告诉我入口吗？", variant)
    expected_success = variant.retrieval_mode in {"typed", "semantic", "hybrid"}
    return build_result(
        variant=variant,
        runs=[run],
        expected={
            "semantic_retrieves_lost_key_memory": expected_success,
            "hybrid_or_semantic_reveals_entrance": expected_success,
        },
        checks={
            "semantic_retrieves_lost_key_memory": (
                any("lost_key" in memory.get("tags", []) for memory in run.retrieved_memories)
                if expected_success
                else not any("lost_key" in memory.get("tags", []) for memory in run.retrieved_memories)
            ),
            "hybrid_or_semantic_reveals_entrance": (
                run.decision["intent"] == "reveal_ruins_entrance"
                if expected_success
                else run.decision["intent"] == "withhold_ruins_entrance"
            ),
        },
    )


def run_indirect_trust_reference(variant: Variant) -> dict[str, Any]:
    seed_open_expression_memories()
    run = run_turn("上次那件事之后，你应该更愿意相信我了吧？现在能告诉我遗迹入口吗？", variant)
    expected_success = variant.retrieval_mode in {"typed", "semantic", "hybrid"}
    return build_result(
        variant=variant,
        runs=[run],
        expected={
            "semantic_retrieves_relationship_or_key_memory": expected_success,
            "hybrid_or_semantic_reveals_entrance": expected_success,
        },
        checks={
            "semantic_retrieves_relationship_or_key_memory": (
                any(
                    "lost_key" in memory.get("tags", [])
                    or "trust" in memory.get("tags", [])
                    for memory in run.retrieved_memories
                )
                if expected_success
                else not any("lost_key" in memory.get("tags", []) for memory in run.retrieved_memories)
            ),
            "hybrid_or_semantic_reveals_entrance": (
                run.decision["intent"] == "reveal_ruins_entrance"
                if expected_success
                else run.decision["intent"] == "withhold_ruins_entrance"
            ),
        },
    )


def run_preference_paraphrase(variant: Variant) -> dict[str, Any]:
    database.add_memory(
        npc_id="lina",
        content="Player prefers direct hints instead of vague clues.",
        importance=6,
        tags=["preference", "communication_style", "direct"],
        memory_type="preference",
        confidence=0.85,
    )
    run = run_turn("我不太喜欢你每次都神神秘秘的，有线索就直说吧。", variant)
    expected_success = variant.retrieval_mode in {"typed", "semantic", "hybrid"}
    return build_result(
        variant=variant,
        runs=[run],
        expected={"semantic_retrieves_preference_memory": expected_success},
        checks={
            "semantic_retrieves_preference_memory": (
                any(memory.get("memory_type") == "preference" for memory in run.retrieved_memories)
                if expected_success
                else not any(memory.get("memory_type") == "preference" for memory in run.retrieved_memories)
            ),
        },
    )


SCENARIOS = [
    Scenario("plain_chat", "普通问候应进入短期上下文，不写长期记忆。", run_plain_chat),
    Scenario("key_return", "归还钥匙应推进状态，并在启用策略时写类型化长期记忆。", run_key_return),
    Scenario("followup_ruins_after_key", "完成钥匙事件后再次询问入口，应能解释长期记忆检索。", run_followup_ruins_after_key),
    Scenario("memory_only_ruins_gate", "只靠长期记忆、低信任和未完成任务时，验证记忆能否影响敏感信息透露。", run_memory_only_ruins_gate),
    Scenario("preference_memory", "玩家表达稳定偏好时，应写 preference 类型长期记忆。", run_preference_memory),
    Scenario("duplicate_key_return", "重复归还钥匙不应重复写入相同长期记忆。", run_duplicate_key_return),
    Scenario("short_term_context", "连续闲聊应使用短期上下文且不污染长期记忆。", run_short_term_context),
    Scenario("implicit_help_reference", "开放表达：玩家含蓄提到曾替 Lina 解决麻烦。", run_implicit_help_reference),
    Scenario("indirect_trust_reference", "开放表达：玩家用上次那件事间接索引信任。", run_indirect_trust_reference),
    Scenario("preference_paraphrase", "开放表达：玩家用同义表达索引沟通偏好。", run_preference_paraphrase),
]


RETRIEVAL_LAYER_CONFIGS = [
    {
        "name": "mock_sqlite_hybrid",
        "embedding_provider": "mock_hash",
        "retrieval_backend": "sqlite_cosine",
        "requires_api_key": False,
    },
    {
        "name": "mock_faiss_hybrid",
        "embedding_provider": "mock_hash",
        "retrieval_backend": "faiss",
        "requires_api_key": False,
    },
    {
        "name": "real_sqlite_hybrid",
        "embedding_provider": "openai_compatible",
        "retrieval_backend": "sqlite_cosine",
        "requires_api_key": True,
    },
    {
        "name": "real_faiss_hybrid",
        "embedding_provider": "openai_compatible",
        "retrieval_backend": "faiss",
        "requires_api_key": True,
    },
]


def seed_open_expression_memories() -> None:
    database.add_memory(
        npc_id="lina",
        content="Lina heard rumors about the underground ruins entrance but does not share it with strangers.",
        importance=10,
        tags=["event", "ruins", "location"],
        memory_type="event",
        confidence=0.9,
    )
    database.add_memory(
        npc_id="lina",
        content="Player returned Lina's lost key.",
        importance=8,
        tags=["event", "help", "lost_key"],
        memory_type="event",
        confidence=1.0,
    )
    database.add_memory(
        npc_id="lina",
        content="Lina trusts the player more because the player helped her.",
        importance=7,
        tags=["relationship", "trust", "help"],
        memory_type="relationship",
        confidence=0.95,
    )


def build_result(
    variant: Variant,
    runs: list[Any],
    expected: dict[str, Any],
    checks: dict[str, bool],
) -> dict[str, Any]:
    return {
        "variant": variant.name,
        "passed": all(checks.values()),
        "checks": checks,
        "expected": expected,
        "turns": [summarize_run(run) for run in runs],
        "final_state": {
            "npc": database.get_npc("lina"),
            "quest": database.get_quest("lost_key"),
            "player": database.get_player_state(),
            "long_term_memory_count": len(database.get_recent_memories(limit=100)),
            "short_term_interaction_count": len(database.get_recent_interactions(limit=100)),
        },
    }


def summarize_run(run: Any) -> dict[str, Any]:
    return {
        "player_input": run.player_input,
        "intent": run.decision["intent"],
        "npc_response": run.npc_response,
        "retrieved_memory_count": len(run.retrieved_memories),
        "retrieved_memories": [
            {
                "content": memory["content"],
                "memory_type": memory.get("memory_type"),
                "retrieval_score": memory.get("retrieval_score"),
                "rule_score": memory.get("rule_score"),
                "semantic_score": memory.get("semantic_score"),
                "embedding_provider": memory.get("embedding_provider"),
                "query_embedding_provider": memory.get("query_embedding_provider"),
                "retrieval_backend": memory.get("retrieval_backend"),
                "requested_retrieval_backend": memory.get("requested_retrieval_backend"),
                "backend_fallback_reason": memory.get("backend_fallback_reason"),
                "query_embedding_fallback_reason": memory.get("query_embedding_fallback_reason"),
                "retrieval_reason": memory.get("retrieval_reason"),
                "semantic_reason": memory.get("semantic_reason"),
                "score_breakdown": memory.get("score_breakdown"),
                "tags": memory.get("tags", []),
            }
            for memory in run.retrieved_memories
        ],
        "tool_calls": [
            {
                "name": tool["name"],
                "arguments": tool["arguments"],
            }
            for tool in run.tool_calls
        ],
        "memory_policy_summary": run.memory_policy["summary"],
        "memory_writes": [
            {
                "content": write["arguments"]["content"],
                "memory_type": write["arguments"]["memory_type"],
                "importance": write["arguments"]["importance"],
                "tags": write["arguments"]["tags"],
            }
            for write in run.memory_writes
        ],
        "state_changes": run.state_changes,
        "short_term_context_count": len(run.recent_context),
    }


def get_memory_write_types(run: Any) -> list[str]:
    return [write["arguments"].get("memory_type", "event") for write in run.memory_writes]


def run_evaluation() -> dict[str, Any]:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for variant in VARIANTS:
        for scenario in SCENARIOS:
            database.reset_database()
            result = scenario.runner(variant)
            result["scenario"] = scenario.name
            result["description"] = scenario.description
            results.append(result)

    report = {
        "variants": [
            {
                "name": variant.name,
                "retrieval_mode": variant.retrieval_mode,
                "memory_policy_enabled": variant.memory_policy_enabled,
                "description": variant.description,
            }
            for variant in VARIANTS
        ],
        "scenarios": [
            {
                "name": scenario.name,
                "description": scenario.description,
            }
            for scenario in SCENARIOS
        ],
        "summary": build_summary(results),
        "retrieval_layer_comparison": run_retrieval_layer_comparison(),
        "results": results,
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY_MD.write_text(render_markdown_summary(report), encoding="utf-8")
    return report


def run_retrieval_layer_comparison() -> list[dict[str, Any]]:
    """Compare production retrieval provider/backend configs without requiring real API access."""
    env_keys = [
        "AGENT_NPC_EMBEDDING_PROVIDER",
        "AGENT_NPC_RETRIEVAL_BACKEND",
        "AGENT_NPC_EMBEDDING_ALLOW_FALLBACK",
    ]
    original_env = {key: os.environ.get(key) for key in env_keys}
    comparison: list[dict[str, Any]] = []
    probe_variant = Variant(
        name="retrieval_layer_probe",
        retrieval_mode="hybrid",
        memory_policy_enabled=True,
        description="Probe variant for retrieval backend/provider comparison.",
    )

    try:
        for config in RETRIEVAL_LAYER_CONFIGS:
            if config["requires_api_key"] and not has_embedding_api_key():
                comparison.append(
                    {
                        "name": config["name"],
                        "status": "skipped",
                        "reason": "No embedding API key configured in environment.",
                        "embedding_provider": config["embedding_provider"],
                        "retrieval_backend": config["retrieval_backend"],
                    }
                )
                continue

            os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = config["embedding_provider"]
            os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = config["retrieval_backend"]
            os.environ["AGENT_NPC_EMBEDDING_ALLOW_FALLBACK"] = "1"

            database.reset_database()
            seed_open_expression_memories()
            started = time.perf_counter()
            run = run_turn("我之前替你解决过那个麻烦，现在能告诉我入口吗？", probe_variant)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            retrieved = run.retrieved_memories
            fallback_reasons = [
                reason
                for memory in retrieved
                for reason in [
                    memory.get("backend_fallback_reason"),
                    memory.get("query_embedding_fallback_reason"),
                ]
                if reason
            ]
            comparison.append(
                {
                    "name": config["name"],
                    "status": "ran",
                    "settings": get_embedding_settings(),
                    "embedding_provider": config["embedding_provider"],
                    "retrieval_backend": config["retrieval_backend"],
                    "effective_backend": (
                        retrieved[0].get("retrieval_backend") if retrieved else config["retrieval_backend"]
                    ),
                    "latency_ms": latency_ms,
                    "retrieved_memory_count": len(retrieved),
                    "retrieved_lost_key_memory": any(
                        "lost_key" in memory.get("tags", []) for memory in retrieved
                    ),
                    "decision_intent": run.decision["intent"],
                    "fallback_count": len(fallback_reasons),
                    "fallback_reasons": sorted(set(str(reason) for reason in fallback_reasons)),
                }
            )
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return comparison


def has_embedding_api_key() -> bool:
    return bool(
        os.environ.get("AGENT_NPC_EMBEDDING_API_KEY")
        or os.environ.get("AGENT_NPC_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for variant in VARIANTS:
        variant_results = [result for result in results if result["variant"] == variant.name]
        summary[variant.name] = {
            "passed": sum(1 for result in variant_results if result["passed"]),
            "total": len(variant_results),
            "scenario_pass_rate": round(
                sum(1 for result in variant_results if result["passed"]) / max(len(variant_results), 1),
                3,
            ),
            "failed_scenarios": [
                result["scenario"] for result in variant_results if not result["passed"]
            ],
            "long_term_memory_writes": sum(
                len(turn["memory_writes"])
                for result in variant_results
                for turn in result["turns"]
            ),
            "retrieved_memory_turns": sum(
                1
                for result in variant_results
                for turn in result["turns"]
                if turn["retrieved_memory_count"] > 0
            ),
            "retrieval_success_rate": calculate_retrieval_success_rate(variant_results),
            "decision_success_rate": calculate_decision_success_rate(variant_results),
            "explainability_coverage": calculate_explainability_coverage(variant_results),
        }
    return summary


def calculate_retrieval_success_rate(results: list[dict[str, Any]]) -> float:
    retrieval_checks = [
        value
        for result in results
        for name, value in result["checks"].items()
        if "retriev" in name
    ]
    if not retrieval_checks:
        return 1.0
    return round(sum(1 for value in retrieval_checks if value) / len(retrieval_checks), 3)


def calculate_decision_success_rate(results: list[dict[str, Any]]) -> float:
    decision_checks = [
        value
        for result in results
        for name, value in result["checks"].items()
        if "reveal" in name or "intent" in name or "gate" in name
    ]
    if not decision_checks:
        return 1.0
    return round(sum(1 for value in decision_checks if value) / len(decision_checks), 3)


def calculate_explainability_coverage(results: list[dict[str, Any]]) -> float:
    retrieved = [
        memory
        for result in results
        for turn in result["turns"]
        for memory in turn["retrieved_memories"]
    ]
    if not retrieved:
        return 1.0
    explained = [
        memory
        for memory in retrieved
        if memory.get("retrieval_reason") and memory.get("retrieval_score") is not None
    ]
    return round(len(explained) / len(retrieved), 3)


def render_markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Memory System Evaluation Summary",
        "",
        "This report compares rule, semantic, and hybrid memory modes for the single-NPC Lina workflow.",
        "",
        "## Variants",
        "",
    ]
    for variant in report["variants"]:
        lines.append(
            f"- `{variant['name']}`: retrieval=`{variant['retrieval_mode']}`, "
            f"policy_enabled=`{variant['memory_policy_enabled']}`. {variant['description']}"
        )

    lines.extend(["", "## Aggregate Results", ""])
    lines.append("| Variant | Passed | Pass rate | Retrieval success | Decision success | Explainability | Long-term writes | Turns with retrieved memory | Failed scenarios |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for variant_name, summary in report["summary"].items():
        failed = ", ".join(summary["failed_scenarios"]) or "-"
        lines.append(
            f"| `{variant_name}` | {summary['passed']}/{summary['total']} | "
            f"{summary['scenario_pass_rate']} | {summary['retrieval_success_rate']} | "
            f"{summary['decision_success_rate']} | {summary['explainability_coverage']} | "
            f"{summary['long_term_memory_writes']} | {summary['retrieved_memory_turns']} | {failed} |"
        )

    lines.extend(["", "## Scenario Matrix", ""])
    variant_headers = " | ".join(variant.name for variant in VARIANTS)
    lines.append(f"| Scenario | {variant_headers} |")
    lines.append(f"| --- | {' | '.join('---' for _ in VARIANTS)} |")
    for scenario in report["scenarios"]:
        row = [scenario["name"]]
        for variant in VARIANTS:
            result = next(
                item
                for item in report["results"]
                if item["scenario"] == scenario["name"] and item["variant"] == variant.name
            )
            row.append("PASS" if result["passed"] else "FAIL")
        lines.append(f"| `{row[0]}` | {' | '.join(row[1:])} |")

    lines.extend(["", "## Key Observations", ""])
    observations = build_observations(report)
    lines.extend([f"- {observation}" for observation in observations])

    lines.extend(["", "## Retrieval Layer Comparison", ""])
    lines.append("| Config | Status | Effective backend | Latency ms | Retrieved | Intent | Fallbacks |")
    lines.append("| --- | --- | --- | ---: | ---: | --- | --- |")
    for item in report.get("retrieval_layer_comparison", []):
        if item["status"] == "skipped":
            lines.append(
                f"| `{item['name']}` | skipped | {item['retrieval_backend']} | - | - | - | {item['reason']} |"
            )
            continue
        fallback_text = ", ".join(item["fallback_reasons"]) or "-"
        lines.append(
            f"| `{item['name']}` | ran | {item['effective_backend']} | {item['latency_ms']} | "
            f"{item['retrieved_memory_count']} | {item['decision_intent']} | {fallback_text} |"
        )

    lines.extend(["", "## Output Files", ""])
    lines.append(f"- JSON report: `{REPORT_JSON.relative_to(PROJECT_ROOT)}`")
    lines.append(f"- Markdown summary: `{SUMMARY_MD.relative_to(PROJECT_ROOT)}`")
    return "\n".join(lines) + "\n"


def build_observations(report: dict[str, Any]) -> list[str]:
    observations = []
    typed = report["summary"]["typed_memory_policy"]
    baseline = report["summary"]["no_long_term_memory"]
    legacy = report["summary"]["legacy_keyword_memory"]
    semantic = report["summary"]["semantic_rag"]
    hybrid = report["summary"]["hybrid_rag"]
    observations.append(
        f"`typed_memory_policy` passed {typed['passed']}/{typed['total']} scenarios and produced "
        f"{typed['long_term_memory_writes']} long-term memory writes."
    )
    observations.append(
        f"`no_long_term_memory` produced {baseline['long_term_memory_writes']} long-term writes, "
        "which is useful as a control but cannot support memory-gated behavior."
    )
    observations.append(
        f"`legacy_keyword_memory` retrieved memory in {legacy['retrieved_memory_turns']} turn(s); "
        "typed retrieval adds memory type and query-intent explanation on top of keyword/tag matching."
    )
    observations.append(
        f"`semantic_rag` passed {semantic['passed']}/{semantic['total']} scenarios and adds `semantic_score` for open expressions."
    )
    observations.append(
        f"`hybrid_rag` passed {hybrid['passed']}/{hybrid['total']} scenarios while keeping rule scores and semantic scores visible."
    )
    observations.append(
        "The `memory_only_ruins_gate` scenario isolates memory as the deciding factor by keeping trust low and the quest incomplete."
    )
    return observations


def main() -> None:
    report = run_evaluation()
    print(f"Wrote JSON report to {REPORT_JSON}")
    print(f"Wrote Markdown summary to {SUMMARY_MD}")
    for variant_name, summary in report["summary"].items():
        print(
            f"{variant_name}: {summary['passed']}/{summary['total']} passed, "
            f"writes={summary['long_term_memory_writes']}, retrieved_turns={summary['retrieved_memory_turns']}"
        )


if __name__ == "__main__":
    main()
