"""Tests for Living World Runtime — Actor adapters and Scheduler."""

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"
os.environ["AGENT_NPC_RETRIEVAL_BACKEND"] = "sqlite_cosine"

TEST_DB_PATH = str(Path(__file__).resolve().parents[1] / "data" / "test_living_world_runtime.db")
os.environ["AGENT_NPC_DB_PATH"] = TEST_DB_PATH

from src.agent.living_world_runtime import (  # noqa: E402
    ArcDirectorActor,
    LivingWorldScheduler,
    NpcActorAdapter,
    TravelerActor,
)
from src.agent.timeline_export import export_simulation_result  # noqa: E402
from src.agent.traveler_profile import load_profile  # noqa: E402
from src.storage import database  # noqa: E402


class ActorAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()

    def test_traveler_actor_initializes_state_and_relationships(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        actor = TravelerActor("test_actor", profile, use_llm=False)
        actor.initialize()

        state = database.get_traveler_state("test_actor")
        self.assertEqual(state["traveler_id"], "test_actor")
        self.assertEqual(state["profile_id"], "truth_seeking_scholar")

        rels = database.get_all_traveler_relationships("test_actor")
        self.assertGreaterEqual(len(rels), 4)

    def test_traveler_actor_tick_returns_result(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        actor = TravelerActor("test_actor2", profile, use_llm=False)
        actor.initialize()

        world_state = {
            "round_number": 1,
            "npc_states": {npc["npc_id"]: npc for npc in database.list_npcs()},
            "scene_objects": database.list_scene_objects(),
            "arc_state": database.get_world_arc_state("ruins_chapter_1"),
            "world_events_since_last_round": [],
        }
        result = actor.tick(world_state)
        self.assertEqual(result["traveler_id"], "test_actor2")
        self.assertIn("decision", result)

    def test_npc_adapter_tick_handles_no_inbox(self) -> None:
        adapter = NpcActorAdapter("lina")
        # Lina should exist after reset
        result = adapter.tick({})
        # With no inbox items, tick should be no_op
        self.assertIn("outcome", result)

    def test_npc_adapter_marks_empty_selected_action_as_skipped(self) -> None:
        adapter = NpcActorAdapter("lina")
        fake_result = type("FakeTick", (), {})()
        fake_result.npc_id = "lina"
        fake_result.outcome = "safe_message"
        fake_result.trigger_event = {"id": 1}
        fake_result.proposed_action = {"action_type": "", "args": {}, "raw_selected_action": None}
        fake_result.validation = {
            "status": "rejected_by_available_actions",
            "reason": "selected action  is not in available_actions",
        }
        fake_result.action_result = {
            "accepted": False,
            "blocked_reason": "rejected_by_available_actions",
        }
        fake_result.plan_update = {}
        fake_result.proactive_message = {"content": "Lina 暂时只留下含糊的提醒，没有改变任何世界状态。"}
        fake_result.reflection = {}
        fake_result.tick_log_id = 1

        with patch("src.agent.living_world_runtime.run_autonomous_tick", return_value=fake_result):
            result = adapter.tick({})

        self.assertEqual(result["outcome"], "skipped_no_valid_action")
        self.assertEqual(result["proposed_action"]["action_type"], "skip")
        self.assertIsNone(result["proactive_message"])

    def test_arc_director_tick_updates_arc_state(self) -> None:
        director = ArcDirectorActor()
        result = director.tick({"round_number": 1}, [], [])
        self.assertEqual(result["arc_id"], "ruins_chapter_1")
        self.assertIn("phase", result)

    def test_arc_director_does_not_resolve_from_first_round_routine_noise(self) -> None:
        director = ArcDirectorActor()
        routine_events = [
            {"payload": {"arc_signal": "guardian"}},
            {"payload": {"arc_signal": "research"}},
            {"payload": {"arc_signal": "sable"}},
            {"payload": {"arc_signal": "chaos"}},
        ]

        result = director.tick({"round_number": 1}, routine_events, [])

        self.assertNotEqual(result["phase"], "resolved")
        self.assertEqual(result["outcome"], "")

    def test_arc_director_accumulates_scores_across_rounds_until_resolved(self) -> None:
        director = ArcDirectorActor()
        world_state = {"round_number": 1}
        event = {"payload": {"arc_signal": "research"}}

        first = director.tick(world_state, [event, event], [])
        second = director.tick({"round_number": 2}, [event, event, event], [])
        third = director.tick({"round_number": 3}, [event, event, event], [])

        self.assertEqual(first["phase"], "evidence_gathering")
        self.assertEqual(second["phase"], "npc_conflict")
        self.assertEqual(third["phase"], "resolved")
        self.assertNotEqual(third["outcome"], "")
        self.assertGreaterEqual(third["cumulative_total_signals"], 8)

    def test_arc_director_does_not_reapply_resolved_outcome(self) -> None:
        director = ArcDirectorActor()
        event = {"payload": {"arc_signal": "research"}}

        director.tick({"round_number": 1}, [event, event], [])
        director.tick({"round_number": 2}, [event, event, event], [])
        resolved = director.tick({"round_number": 3}, [event, event, event], [])
        repeated = director.tick({"round_number": 4}, [], [])

        self.assertEqual(repeated["phase"], "resolved")
        self.assertEqual(repeated["outcome"], resolved["outcome"])
        self.assertEqual(repeated["tension"], resolved["tension"])

    def test_traveler_get_direct_targets(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        actor = TravelerActor("test_actor3", profile, use_llm=False)
        actor.initialize()

        result = {
            "proposed_action": {"action_type": "talk_to", "args": {"npc_id": "mira"}},
        }
        targets = actor.get_direct_targets(result)
        self.assertIn("mira", targets)

    def test_traveler_get_direct_targets_empty_for_non_npc_action(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        actor = TravelerActor("test_actor4", profile, use_llm=False)
        result = {
            "proposed_action": {"action_type": "move_to", "args": {"location_id": "archive"}},
        }
        targets = actor.get_direct_targets(result)
        self.assertEqual(len(targets), 0)


class SchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        database.reset_database()

    def test_scheduler_initializes_and_runs_minimal_simulation(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("scheduler_test", profile, use_llm=False)
        traveler.initialize()

        npc_adapters = {
            "lina": NpcActorAdapter("lina"),
            "ron": NpcActorAdapter("ron"),
            "mira": NpcActorAdapter("mira"),
            "sable": NpcActorAdapter("sable"),
        }
        director = ArcDirectorActor()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters=npc_adapters,
            arc_director=director,
            max_npc_ticks_per_round=2,
        )

        result = scheduler.run(rounds=3)
        self.assertEqual(result["total_rounds"], 3)
        self.assertIn("final_arc_outcome", result)
        self.assertIn("final_relationships", result)
        self.assertEqual(len(result["rounds"]), 3)

    def test_scheduler_does_not_resolve_arc_during_first_npc_ticks(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("early_arc", profile, use_llm=False)
        traveler.initialize()

        npc_adapters = {
            "lina": NpcActorAdapter("lina"),
            "ron": NpcActorAdapter("ron"),
            "mira": NpcActorAdapter("mira"),
            "sable": NpcActorAdapter("sable"),
        }
        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters=npc_adapters,
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=2,
            npc_routines_every_round=True,
        )

        result = scheduler.run(rounds=1)

        self.assertNotEqual(result["rounds"][0]["arc_update"]["phase"], "resolved")
        self.assertEqual(result["final_arc_outcome"], "")

    def test_scheduler_can_add_low_priority_routine_ticks_for_idle_npcs(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("idle_probe", profile, use_llm=False)
        traveler.initialize()

        npc_adapters = {
            "lina": NpcActorAdapter("lina"),
            "ron": NpcActorAdapter("ron"),
            "mira": NpcActorAdapter("mira"),
            "sable": NpcActorAdapter("sable"),
        }
        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters=npc_adapters,
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=4,
            npc_routines_every_round=False,
            idle_npc_probe_enabled=True,
        )

        result = scheduler.run(rounds=1)

        ticked_npcs = {
            tick["npc_id"]
            for tick in result["rounds"][0]["npc_ticks"]
        }
        self.assertIn("sable", ticked_npcs)

    def test_scheduler_can_run_until_outcome(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("outcome_probe", profile, use_llm=False)
        traveler.initialize()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters={
                "lina": NpcActorAdapter("lina"),
                "ron": NpcActorAdapter("ron"),
                "mira": NpcActorAdapter("mira"),
                "sable": NpcActorAdapter("sable"),
            },
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=4,
            npc_routines_every_round=True,
            idle_npc_probe_enabled=True,
        )

        result = scheduler.run_until_outcome(max_rounds=20)

        self.assertLessEqual(result["total_rounds"], 20)
        self.assertEqual(result["final_arc_phase"], "resolved")
        self.assertNotEqual(result["final_arc_outcome"], "")
        self.assertIn("timings", result)
        self.assertIn("total_ms", result["timings"])

    def test_idle_npc_probes_do_not_create_arc_chaos(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("idle_arc_probe", profile, use_llm=False)
        traveler.initialize()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters={
                "lina": NpcActorAdapter("lina"),
                "ron": NpcActorAdapter("ron"),
                "mira": NpcActorAdapter("mira"),
                "sable": NpcActorAdapter("sable"),
            },
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=4,
            npc_routines_every_round=False,
            idle_npc_probe_enabled=True,
        )

        result = scheduler.run(rounds=1)

        traveler_chaos = sum(
            1
            for event in result["rounds"][0]["traveler_tick"]["created_events"]
            if event.get("payload", {}).get("arc_signal") == "chaos"
        )
        non_idle_npc_triggers = sum(
            1
            for tick in result["rounds"][0]["npc_ticks"]
            if tick.get("trigger_event_id") and tick.get("trigger_event_type") != "npc_idle_routine_probe"
        )
        self.assertEqual(
            result["rounds"][0]["arc_update"]["scores"]["chaos"],
            traveler_chaos + non_idle_npc_triggers,
        )

    def test_idle_npc_probes_respect_tick_budget(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("idle_budget_probe", profile, use_llm=False)
        traveler.initialize()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters={
                "lina": NpcActorAdapter("lina"),
                "ron": NpcActorAdapter("ron"),
                "mira": NpcActorAdapter("mira"),
                "sable": NpcActorAdapter("sable"),
            },
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=2,
            npc_routines_every_round=False,
            idle_npc_probe_enabled=True,
        )

        result = scheduler.run(rounds=1)

        self.assertLessEqual(len(result["rounds"][0]["npc_ticks"]), 2)

    def test_idle_npc_probes_skip_tick_disabled_npcs(self) -> None:
        database.upsert_npc_runtime_state("sable", "active", False)
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("idle_disabled_probe", profile, use_llm=False)
        traveler.initialize()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters={
                "lina": NpcActorAdapter("lina"),
                "ron": NpcActorAdapter("ron"),
                "mira": NpcActorAdapter("mira"),
                "sable": NpcActorAdapter("sable"),
            },
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=4,
            npc_routines_every_round=False,
            idle_npc_probe_enabled=True,
        )

        result = scheduler.run(rounds=1)
        ticked_npcs = {tick["npc_id"] for tick in result["rounds"][0]["npc_ticks"]}

        self.assertNotIn("sable", ticked_npcs)
        self.assertEqual(database.get_npc_event_inbox("sable", include_seen=False), [])

    def test_scheduler_collects_round_logs(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("sched_rounds", profile, use_llm=False)
        traveler.initialize()

        npc_adapters = {"lina": NpcActorAdapter("lina")}
        director = ArcDirectorActor()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters=npc_adapters,
            arc_director=director,
            max_npc_ticks_per_round=1,
            npc_routines_every_round=True,
        )

        result = scheduler.run(rounds=2)
        self.assertEqual(len(result["rounds"]), 2)
        for rd in result["rounds"]:
            self.assertIn("round_number", rd)
            self.assertIn("traveler_tick", rd)
            self.assertIn("arc_update", rd)
            self.assertIn("timings", rd)
            self.assertIn("ambient_routines_ms", rd["timings"])
            self.assertIn("traveler_tick_ms", rd["timings"])
            self.assertIn("npc_ticks_ms", rd["timings"])
            self.assertIn("arc_resolution_ms", rd["timings"])
            self.assertIn("total_ms", rd["timings"])
            self.assertIn("timings", rd["traveler_tick"])
            self.assertIn("observe_ms", rd["traveler_tick"]["timings"])

    def test_scheduler_round_events_do_not_duplicate_traveler_events(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("dedupe_rounds", profile, use_llm=False)
        traveler.initialize()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters={},
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=0,
            npc_routines_every_round=False,
        )

        result = scheduler.run(rounds=2)
        round_two_recent_events = result["rounds"][1]["traveler_tick"]["observation"]["recent_events"]
        event_ids = [event["id"] for event in round_two_recent_events if "id" in event]
        self.assertEqual(len(event_ids), len(set(event_ids)))

    def test_traveler_events_preserve_arc_signal_for_scheduler_scoring(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("traveler_arc_signal", profile, use_llm=False)
        traveler.initialize()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters={},
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=0,
            npc_routines_every_round=False,
        )

        result = scheduler.run(rounds=1)

        created_events = result["rounds"][0]["traveler_tick"]["created_events"]
        self.assertTrue(created_events)
        self.assertTrue(
            any(
                isinstance(event.get("payload"), dict)
                and event["payload"].get("arc_signal")
                for event in created_events
            )
        )

    def test_timeline_export_renders_round_and_traveler_timings(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        traveler = TravelerActor("timed_export", profile, use_llm=False)
        traveler.initialize()

        scheduler = LivingWorldScheduler(
            traveler=traveler,
            npc_adapters={},
            arc_director=ArcDirectorActor(),
            max_npc_ticks_per_round=0,
            npc_routines_every_round=False,
        )

        result = scheduler.run(rounds=1)

        with tempfile.TemporaryDirectory() as tmpdir:
            _, md_path = export_simulation_result(
                result=result,
                profile=profile,
                output_dir=tmpdir,
                run_id="timed-export-test",
            )
            markdown = md_path.read_text(encoding="utf-8")

        self.assertIn("**Timing**", markdown)
        self.assertIn("Traveler internals", markdown)
        self.assertIn("observe", markdown)
        self.assertIn("trace log", markdown)

    def test_timeline_export_explains_exploration_routing_and_arc_progress(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        result = {
            "rounds": [
                {
                    "round_number": 1,
                    "traveler_tick": {
                        "proposed_action": {
                            "action_type": "move_to",
                            "args": {"location_id": "guard_post"},
                        },
                        "decision": {
                            "decision_reason": "Follow higher information-gain lead.",
                        },
                        "reflection": {
                            "exploration_context": {
                                "leads": [
                                    {
                                        "lead_id": "ask_ron_about_guard_ledger",
                                        "reason": "Need external evidence.",
                                    }
                                ]
                            }
                        },
                    },
                    "npc_ticks": [
                        {
                            "npc_id": "mira",
                            "proposed_action": {
                                "action_type": "suggest_next_investigation",
                            },
                            "validation": {
                                "status": "allowed",
                                "reason": "NPC can advance a known lead.",
                            },
                            "outcome": "allowed",
                        }
                    ],
                    "arc_update": {
                        "phase": "npc_conflict",
                        "tension": 2,
                        "outcome": "",
                        "cumulative_total_signals": 6,
                    },
                }
            ],
            "final_arc_phase": "npc_conflict",
            "final_arc_outcome": "",
            "final_tension": 2,
            "final_traveler_location": "guard_post",
            "final_relationships": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            _, md_path = export_simulation_result(
                result=result,
                profile=profile,
                output_dir=tmpdir,
                run_id="exploration-routing-export-test",
            )
            markdown = md_path.read_text(encoding="utf-8")

        self.assertIn("Exploration leads", markdown)
        self.assertIn("ask_ron_about_guard_ledger", markdown)
        self.assertIn("cumulative signals=6", markdown)
        self.assertIn("NPC mira", markdown)
        self.assertIn("NPC can advance a known lead.", markdown)
