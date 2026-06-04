"""Timeline export — JSON and Markdown output for simulation runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.traveler_profile import TravelerProfile


def export_simulation_result(
    result: dict[str, Any],
    profile: TravelerProfile,
    output_dir: str | Path,
    run_id: str | None = None,
) -> tuple[Path, Path]:
    """Export simulation result to JSON and Markdown files.

    Returns:
        Tuple of (json_path, markdown_path).
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    pid = profile.profile_id
    rid = run_id or f"{ts}-{pid}"

    json_path = directory / f"{rid}.json"
    md_path = directory / f"{rid}.md"

    _write_json(result, profile, json_path, rid)
    _write_markdown(result, profile, md_path, rid)

    return json_path, md_path


def _write_json(result: dict[str, Any], profile: TravelerProfile, path: Path, run_id: str) -> None:
    payload = {
        "run_id": run_id,
        "profile_id": profile.profile_id,
        "profile_summary": _profile_summary(profile),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_markdown(result: dict[str, Any], profile: TravelerProfile, path: Path, run_id: str) -> None:
    lines: list[str] = []
    lines.append(f"# Living World Simulation Report")
    lines.append(f"")
    lines.append(f"**Run ID**: `{run_id}`")
    lines.append(f"**Profile**: `{profile.profile_id}`")
    lines.append(f"**Traveler**: {profile.identity.public_name} — {profile.identity.public_role}")
    lines.append(f"")

    # Profile summary
    lines.append("## Traveler Profile")
    lines.append(f"")
    lines.append(f"- **Identity**: {profile.identity.public_name}, {profile.identity.public_role}")
    lines.append(f"- **Cover Story**: {profile.identity.cover_story}")
    lines.append(f"- **Background**: {profile.identity.private_background}")
    lines.append(f"- **Primary Motivation**: {profile.primary_motivation} ({getattr(profile.motivations, profile.primary_motivation):.2f})")
    lines.append(f"- **Dominant Personality**: {profile.dominant_personality_trait} ({getattr(profile.personality, profile.dominant_personality_trait):.2f})")
    lines.append(f"- **Exploration Style**: {profile.exploration_style.primary_approach}")
    lines.append(f"- **Secrets**: {len(profile.secrets)}")
    lines.append(f"- **Hard Boundaries**: {len(profile.boundaries.hard)}")
    lines.append(f"")

    # Timeline
    lines.append("## Timeline")
    lines.append(f"")

    rounds = result.get("rounds", [])
    for rd in rounds:
        rn = rd["round_number"]
        lines.append(f"### Round {rn}")
        lines.append(f"")

        timings = rd.get("timings", {})
        if timings:
            lines.append(
                "- **Timing**: "
                f"total={_format_ms(timings.get('total_ms'))}; "
                f"ambient={_format_ms(timings.get('ambient_routines_ms'))}, "
                f"traveler={_format_ms(timings.get('traveler_tick_ms'))}, "
                f"npc={_format_ms(timings.get('npc_ticks_ms'))}, "
                f"arc={_format_ms(timings.get('arc_resolution_ms'))}"
            )

        traveler = rd.get("traveler_tick", {})
        action = traveler.get("proposed_action", {})
        action_type = action.get("action_type", "unknown")
        decision = traveler.get("decision", {})
        reason = decision.get("decision_reason", "no reason recorded")

        lines.append(f"- **Traveler**: `{action_type}` — {reason}")

        traveler_timings = traveler.get("timings", {})
        if traveler_timings:
            lines.append(
                "  - Traveler internals: "
                f"observe={_format_ms(traveler_timings.get('observe_ms'))}, "
                f"retrieve memory={_format_ms(traveler_timings.get('retrieve_memory_ms'))}, "
                f"build action surface={_format_ms(traveler_timings.get('build_action_surface_ms'))}, "
                f"decide={_format_ms(traveler_timings.get('decide_ms'))}, "
                f"validate={_format_ms(traveler_timings.get('validate_ms'))}, "
                f"act={_format_ms(traveler_timings.get('act_ms'))}, "
                f"reflect={_format_ms(traveler_timings.get('reflect_ms'))}, "
                f"trace log={_format_ms(traveler_timings.get('trace_log_ms'))}"
            )

        # Relationship changes
        rel_changes = traveler.get("relationship_changes", [])
        for rc in rel_changes:
            before = rc.get("before", 0)
            after = rc.get("after", 0)
            lines.append(f"  - {rc['npc_id']}.{rc['field']}: {before:.2f} → {after:.2f}")

        # NPC ticks
        npc_ticks = rd.get("npc_ticks", [])
        for nt in npc_ticks:
            pa = nt.get("proposed_action", {})
            nt_action = pa.get("action_type", "none")
            lines.append(f"- **NPC {nt.get('npc_id', '?')}**: `{nt_action}` (outcome={nt.get('outcome', 'unknown')})")

        # Arc
        arc = rd.get("arc_update", {})
        if arc:
            lines.append(f"- **Arc**: phase={arc.get('phase')}, tension={arc.get('tension')}, outcome={arc.get('outcome', 'unresolved')}")

        lines.append(f"")

    # Final outcome
    lines.append("## Final Outcome")
    lines.append(f"")
    lines.append(f"- **Arc Phase**: {result.get('final_arc_phase', 'unknown')}")
    lines.append(f"- **Arc Outcome**: {result.get('final_arc_outcome', 'unresolved')}")
    lines.append(f"- **Tension**: {result.get('final_tension', 0)}")
    lines.append(f"- **Traveler Location**: {result.get('final_traveler_location', 'unknown')}")
    lines.append(f"")

    # Final relationships
    lines.append("## Final Relationships")
    lines.append(f"")
    lines.append(f"| NPC    | Trust | Suspicion | Affinity | Last Tone |")
    lines.append(f"|--------|-------|-----------|----------|-----------|")
    relationships = result.get("final_relationships", {})
    for npc_id, rel in relationships.items():
        lines.append(
            f"| {npc_id:<6} | {rel.get('trust', 0):+.2f} | {rel.get('suspicion', 0):.2f} | "
            f"{rel.get('affinity', 0):+.2f} | {rel.get('last_tone', 'neutral')} |"
        )
    lines.append(f"")

    # Architecture note
    lines.append("## Architecture Notes")
    lines.append(f"")
    lines.append("- This is a **multi-agent system**: Traveler, NPCs, and ArcDirector are all ActorAgent implementations.")
    lines.append("- **LLM participates in action decisions** and narrative synthesis, but does not own canonical world facts.")
    lines.append("- **World evolution** is driven by tool execution, quest state machines, memory systems, and the scheduler.")
    lines.append("- All state changes have **programmatic trace/evidence**.")

    path.write_text("\n".join(lines), encoding="utf-8")


def _profile_summary(profile: TravelerProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "public_name": profile.identity.public_name,
        "public_role": profile.identity.public_role,
        "primary_motivation": profile.primary_motivation,
        "dominant_personality": profile.dominant_personality_trait,
        "exploration_style": profile.exploration_style.primary_approach,
        "secret_count": len(profile.secrets),
        "goal_count": len(profile.private_goals),
    }


def _format_ms(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.3f} ms"
    return "n/a"
