"""Tests for Traveler exploration planning context."""

from src.agent.exploration_planner import build_exploration_context


def _actions() -> list[dict]:
    return [
        {
            "action_type": "talk_to",
            "args_schema": {
                "npc_id": "string",
                "topic": "string",
                "tone": "string",
                "honesty_level": "string",
                "disclosure": "string",
            },
            "arg_options": {"npc_id": ["mira"]},
        },
        {
            "action_type": "move_to",
            "args_schema": {"location_id": "string"},
            "arg_options": {"location_id": ["guard_post", "tavern"]},
        },
        {"action_type": "wait_and_observe", "args_schema": {}},
    ]


def test_repeated_mira_topic_without_new_evidence_prioritizes_guard_post() -> None:
    observation = {
        "recent_events": [
            {
                "event_type": "traveler_talked_to_npc",
                "source_id": "traveler",
                "content": "Traveler talked to mira about 'ruins'.",
                "payload": {"npc_id": "mira", "topic": "ruins"},
            }
        ],
        "traveler_state": {"current_location": "archive"},
    }

    context = build_exploration_context("traveler", observation, _actions())

    assert context["traveler_id"] == "traveler"
    thread = context["conversation_threads"][0]
    assert thread["npc_id"] == "mira"
    assert thread["topic"] == "ruins"
    assert thread["status"] == "waiting_for_external_evidence"
    assert context["action_scores"]["move_to:guard_post"] > context["action_scores"]["talk_to:mira"]
    assert "lower priority, not forbidden" in context["selection_policy"]


def test_new_mira_evidence_keeps_repeat_conversation_high_value() -> None:
    observation = {
        "recent_events": [
            {
                "event_type": "traveler_talked_to_npc",
                "source_id": "traveler",
                "content": "Traveler talked to mira about 'ruins'.",
                "payload": {"npc_id": "mira", "topic": "ruins"},
            },
            {
                "event_type": "traveler_investigated",
                "source_id": "traveler",
                "content": "Fresh evidence mentions Mira's field notes and a ruins inscription.",
                "payload": {"target_id": "mira_field_notes", "evidence_id": "inscription_note"},
            },
        ],
        "traveler_state": {"current_location": "archive"},
    }

    context = build_exploration_context("traveler", observation, _actions())

    thread = context["conversation_threads"][0]
    assert thread["status"] == "open_with_new_evidence"
    assert context["action_scores"]["talk_to:mira"] >= context["action_scores"]["move_to:guard_post"]
