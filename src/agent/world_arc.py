from __future__ import annotations

from typing import Any

from src.storage import database


ARC_ID = "ruins_chapter_1"
ARC_PHASES = ["rumor", "evidence_gathering", "npc_conflict", "resolved"]
ARC_OUTCOMES = {"guardian_advantage", "research_advantage", "sable_advantage", "chaotic_lockdown"}
ARC_ADVANTAGES = {"none", "guardian", "research", "sable", "chaos"}


def resolve_arc_outcome(scores: dict[str, int] | None = None) -> dict[str, Any]:
    score_map = scores or collect_arc_scores()
    if int(score_map.get("chaos", 0)) >= 3:
        outcome = "chaotic_lockdown"
        advantage = "chaos"
    else:
        advantage = max(["guardian", "research", "sable"], key=lambda key: int(score_map.get(key, 0)))
        outcome = {
            "guardian": "guardian_advantage",
            "research": "research_advantage",
            "sable": "sable_advantage",
        }[advantage]
    return {
        "arc_id": ARC_ID,
        "arc_outcome": outcome,
        "advantage": advantage,
        "scores": score_map,
    }


def collect_arc_scores(limit: int = 100) -> dict[str, int]:
    scores = {"guardian": 0, "research": 0, "sable": 0, "chaos": 0}
    for event in database.get_world_events(limit=limit):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        signal = str(payload.get("arc_signal", ""))
        if signal in scores:
            scores[signal] += 1
        if "conflict" in str(event.get("event_type", "")) or "contradict" in str(event.get("content", "")).lower():
            scores["chaos"] += 1
    return scores


def next_phase_for_outcome(outcome: str) -> str:
    if outcome in ARC_OUTCOMES:
        return "resolved"
    state = database.get_world_arc_state(ARC_ID)
    phase = str(state["phase"])
    if phase == "rumor":
        return "evidence_gathering"
    if phase == "evidence_gathering":
        return "npc_conflict"
    return phase


def apply_arc_outcome(outcome: str, reason: str = "", confidence: float = 0.0) -> dict[str, Any]:
    if outcome not in ARC_OUTCOMES:
        raise ValueError(f"Unsupported arc outcome: {outcome}")
    advantage = {
        "guardian_advantage": "guardian",
        "research_advantage": "research",
        "sable_advantage": "sable",
        "chaotic_lockdown": "chaos",
    }[outcome]
    current = database.get_world_arc_state(ARC_ID)
    tension_delta = 2 if outcome == "chaotic_lockdown" else 1
    return database.update_world_arc_state(
        arc_id=ARC_ID,
        phase="resolved",
        tension=min(10, int(current["tension"]) + tension_delta),
        advantage=advantage,
        outcome=outcome,
        metadata={
            **current.get("metadata", {}),
            "last_resolution_reason": reason,
            "last_resolution_confidence": confidence,
        },
    )


def advance_arc_after_player_action() -> dict[str, Any]:
    current = database.get_world_arc_state(ARC_ID)
    if current["phase"] == "rumor":
        return database.update_world_arc_state(ARC_ID, phase="evidence_gathering", tension=int(current["tension"]) + 1)
    return current
