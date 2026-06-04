"""Major event detection — programmatic rules for marking significant events.

LLM does NOT participate in major event detection. All rules are deterministic.
"""

from __future__ import annotations

from typing import Any


SEVERITY_VALUES = {"minor": 1, "notable": 2, "major": 3, "critical": 4}


def detect_major_events(
    round_num: int,
    traveler_tick: dict[str, Any] | None = None,
    npc_ticks: list[dict[str, Any]] | None = None,
    ambient_events: list[dict[str, Any]] | None = None,
    arc_update: dict[str, Any] | None = None,
    min_severity: str = "notable",
) -> list[dict[str, Any]]:
    """Scan all round data and return a list of major events.

    Args:
        round_num: Current round number.
        traveler_tick: Result from the Traveler's tick.
        npc_ticks: Results from NPC autonomous ticks.
        ambient_events: Ambient world events from NPC routines.
        arc_update: Arc director update result.
        min_severity: Minimum severity to include ("minor", "notable", "major", "critical").

    Returns:
        List of major events, each with {round, severity, rule_id, description, details}.
    """
    events: list[dict[str, Any]] = []
    threshold = SEVERITY_VALUES.get(min_severity, 2)

    # ── Rule: Relationship shifts ──────────────────────────────────
    if traveler_tick:
        rel_changes = traveler_tick.get("relationship_changes", [])
        for change in rel_changes:
            npc_id = change.get("npc_id", "unknown")
            field = change.get("field", "")
            before = float(change.get("before", 0))
            after = float(change.get("after", 0))
            delta = abs(after - before)

            if delta >= 0.5 and field in ("trust", "affinity"):
                severity = "major" if (before > 0) != (after > 0) else "notable"
                direction = "increased" if after > before else "decreased"
                events.append({
                    "round": round_num,
                    "severity": severity,
                    "rule_id": "relationship_flip" if severity == "major" else "relationship_shift",
                    "description": f"Relationship {field} with {npc_id} {direction} by {delta:.2f} ({before:.2f} → {after:.2f}).",
                    "details": change,
                })
            elif delta >= 0.3:
                events.append({
                    "round": round_num,
                    "severity": "notable",
                    "rule_id": "relationship_shift",
                    "description": f"Relationship {field} with {npc_id} changed by {delta:.2f}.",
                    "details": change,
                })

        # ── Rule: Deception detected ───────────────────────────────
        deception = traveler_tick.get("deception_metadata")
        if isinstance(deception, dict) and deception:
            if deception.get("detected"):
                events.append({
                    "round": round_num,
                    "severity": "major",
                    "rule_id": "deception_detected",
                    "description": f"Deception detected: {deception.get('deception_type')} against {deception.get('target_npc_id')}.",
                    "details": deception,
                })

        # ── Rule: Secret disclosed ─────────────────────────────────
        disclosure = traveler_tick.get("disclosure_metadata")
        if isinstance(disclosure, dict) and disclosure:
            events.append({
                "round": round_num,
                "severity": "major",
                "rule_id": "secret_disclosed",
                "description": f"Secret '{disclosure.get('secret_id')}' disclosed to {disclosure.get('disclosed_to')} ({disclosure.get('disclosure_level')}).",
                "details": disclosure,
            })

    # ── Rule: NPC escalation ───────────────────────────────────────
    if npc_ticks:
        for tick in npc_ticks:
            proposed = tick.get("proposed_action", {})
            action_type = proposed.get("action_type", "")
            if action_type == "escalate_lockdown":
                events.append({
                    "round": round_num,
                    "severity": "major",
                    "rule_id": "npc_lockdown",
                    "description": f"NPC {tick.get('npc_id')} escalated lockdown — chaotic signal.",
                    "details": {"npc_id": tick.get("npc_id")},
                })
            elif action_type in ("patrol_sensitive_route", "secure_tavern_back_alley"):
                events.append({
                    "round": round_num,
                    "severity": "notable",
                    "rule_id": "npc_security_action",
                    "description": f"NPC {tick.get('npc_id')} took security action: {action_type}.",
                    "details": {"npc_id": tick.get("npc_id"), "action_type": action_type},
                })

    # ── Rule: Arc phase / outcome changes ──────────────────────────
    if arc_update:
        phase = arc_update.get("phase", "")
        outcome = arc_update.get("outcome", "")
        if phase == "resolved":
            events.append({
                "round": round_num,
                "severity": "critical",
                "rule_id": "arc_outcome_reached",
                "description": f"Arc resolved with outcome: {outcome}. Advantage: {arc_update.get('advantage')}.",
                "details": arc_update,
            })
        elif phase == "npc_conflict":
            events.append({
                "round": round_num,
                "severity": "major",
                "rule_id": "arc_phase_changed",
                "description": f"Arc phase advanced to 'npc_conflict' (tension={arc_update.get('tension')}).",
                "details": arc_update,
            })
        elif phase == "evidence_gathering":
            events.append({
                "round": round_num,
                "severity": "notable",
                "rule_id": "arc_phase_changed",
                "description": f"Arc phase advanced to 'evidence_gathering'.",
                "details": arc_update,
            })

    # ── Filter by severity threshold ───────────────────────────────
    return [e for e in events if SEVERITY_VALUES.get(e["severity"], 0) >= threshold]
