"""Living World Runtime — single Traveler profile demo.

Usage:
    python scripts/run_traveler_world_demo.py --profile truth_seeking_scholar --rounds 12 --mock
    python scripts/run_traveler_world_demo.py --profile suspicious_survivor --rounds 8 --mock --export-dir data/traces/traveler_runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.living_world_runtime import (  # noqa: E402
    ArcDirectorActor,
    LivingWorldScheduler,
    NpcActorAdapter,
    TravelerActor,
)
from src.agent.major_events import detect_major_events  # noqa: E402
from src.agent.timeline_export import export_simulation_result  # noqa: E402
from src.agent.llm_client import get_provider_status  # noqa: E402
from src.agent.traveler_profile import load_profile, list_available_profiles  # noqa: E402
from src.storage import database  # noqa: E402


def build_npc_adapters(use_mock: bool) -> dict[str, NpcActorAdapter]:
    autonomous_tick_mode = "deterministic_fallback" if use_mock else "llm_constrained"
    return {
        npc_id: NpcActorAdapter(npc_id, autonomous_tick_mode=autonomous_tick_mode)
        for npc_id in ["lina", "ron", "mira", "sable"]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Living World simulation with a Traveler profile.")
    parser.add_argument("--profile", default="truth_seeking_scholar", help="Traveler profile ID.")
    parser.add_argument("--rounds", type=int, default=12, help="Number of simulation rounds.")
    parser.add_argument("--mock", action="store_true", help="Use deterministic fallback (no LLM).")
    parser.add_argument("--export-dir", default="data/traces/traveler_runs", help="Export directory.")
    parser.add_argument("--list-profiles", action="store_true", help="List available profiles and exit.")
    parser.add_argument("--max-npc-ticks", type=int, default=2, help="Maximum NPC autonomous ticks per round.")
    parser.add_argument("--idle-npc-probe", action="store_true", help="Tick idle NPCs with low-priority probes.")
    parser.add_argument("--stop-on-outcome", action="store_true", help="Stop early once the arc has an outcome.")
    args = parser.parse_args()

    if args.list_profiles:
        print("Available profiles:")
        for pid in list_available_profiles():
            print(f"  - {pid}")
        return

    # Initialize
    database.reset_database()
    profile = load_profile(args.profile)
    use_llm = not args.mock
    if use_llm:
        status = get_provider_status()
        if status["provider"] != "openai_compatible" or not status["uses_api_key"]:
            raise SystemExit(
                "LLM mode requires AGENT_NPC_LLM_PROVIDER=openai_compatible and "
                "AGENT_NPC_LLM_API_KEY or OPENAI_API_KEY. Use --mock for the offline deterministic demo."
            )

    print(f"Profile: {profile.profile_id} — {profile.identity.public_name}")
    if use_llm:
        print(f"Round budget: {args.rounds} | LLM: {status['model']} @ {status['base_url']}")
    else:
        print(f"Round budget: {args.rounds} | LLM: disabled for Traveler and NPCs (--mock offline deterministic)")
    if args.stop_on_outcome:
        print("Stop condition: first resolved arc outcome or round budget, whichever comes first")
    print(f"Primary Motivation: {profile.primary_motivation}")
    print(f"Dominant Personality: {profile.dominant_personality_trait}")
    print("-" * 50)

    # Build actors
    traveler = TravelerActor(
        "traveler_main",
        profile,
        use_llm=use_llm,
        allow_llm_fallback=args.mock,
    )
    traveler.initialize()

    npc_adapters = build_npc_adapters(use_mock=args.mock)
    director = ArcDirectorActor()

    scheduler = LivingWorldScheduler(
        traveler=traveler,
        npc_adapters=npc_adapters,
        arc_director=director,
        max_npc_ticks_per_round=args.max_npc_ticks,
        npc_routines_every_round=True,
        idle_npc_probe_enabled=args.idle_npc_probe,
    )

    # Run simulation
    if args.stop_on_outcome:
        print(f"\nRunning until arc outcome or {args.rounds} rounds...")
    else:
        print(f"\nRunning {args.rounds} rounds...")
    if args.stop_on_outcome:
        result = scheduler.run_until_outcome(max_rounds=args.rounds)
    else:
        result = scheduler.run(rounds=args.rounds)

    # Detect major events across all rounds
    all_major_events = []
    for rd in result["rounds"]:
        events = detect_major_events(
            round_num=rd["round_number"],
            traveler_tick=rd.get("traveler_tick"),
            npc_ticks=rd.get("npc_ticks", []),
            ambient_events=rd.get("ambient_events", []),
            arc_update=rd.get("arc_update"),
            min_severity="notable",
        )
        all_major_events.extend(events)

    result["major_events"] = all_major_events

    # Summary
    print(f"\nSimulation complete.")
    print(f"Final Arc Phase: {result['final_arc_phase']}")
    print(f"Final Arc Outcome: {result['final_arc_outcome']}")
    print(f"Final Traveler Location: {result['final_traveler_location']}")
    print(f"Major Events: {len(all_major_events)}")
    print(f"\nFinal Relationships:")
    for npc_id, rel in result["final_relationships"].items():
        print(f"  {npc_id}: trust={rel['trust']:+.2f} suspicion={rel['suspicion']:.2f} affinity={rel['affinity']:+.2f} tone={rel['last_tone']}")

    # Export
    json_path, md_path = export_simulation_result(
        result=result,
        profile=profile,
        output_dir=args.export_dir,
    )
    print(f"\nExported:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
