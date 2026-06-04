"""Focused tests for Traveler deterministic decision information gain."""

from src.agent.traveler_actions import ActionBias
from src.agent.traveler_decision import decide_traveler_action, deterministic_fallback_decision


def test_fallback_uses_exploration_scores_to_break_profile_tie() -> None:
    actions = [
        {
            "action_type": "talk_to",
            "args_schema": {"npc_id": "string", "topic": "string"},
            "arg_options": {"npc_id": ["mira"]},
        },
        {
            "action_type": "move_to",
            "args_schema": {"location_id": "string"},
            "arg_options": {"location_id": ["guard_post"]},
        },
    ]
    biases = [
        ActionBias("talk_to", (), (), "low", 0.5),
        ActionBias("move_to", (), (), "low", 0.5),
    ]
    exploration_context = {
        "action_scores": {"talk_to:mira": 0.2, "move_to:guard_post": 0.9},
        "selection_policy": "Repeated conversations are lower priority, not forbidden.",
    }

    decision = deterministic_fallback_decision(actions, biases, exploration_context=exploration_context)

    assert decision["selected_action"]["action_type"] == "move_to"
    assert decision["selected_action"]["args"]["location_id"] == "guard_post"
    assert "information gain" in decision["decision_reason"]


def test_fallback_picks_highest_information_gain_arg_option() -> None:
    actions = [
        {
            "action_type": "talk_to",
            "args_schema": {"npc_id": "string", "topic": "string"},
            "arg_options": {"npc_id": ["lina", "mira"]},
        }
    ]
    biases = [ActionBias("talk_to", (), (), "low", 0.7)]
    exploration_context = {
        "action_scores": {"talk_to:lina": 0.1, "talk_to:mira": 0.8},
        "selection_policy": "Repeated conversations are lower priority, not forbidden.",
    }

    decision = deterministic_fallback_decision(actions, biases, exploration_context=exploration_context)

    assert decision["selected_action"]["action_type"] == "talk_to"
    assert decision["selected_action"]["args"]["npc_id"] == "mira"


def test_llm_normalization_fallback_preserves_exploration_context(monkeypatch) -> None:
    actions = [
        {
            "action_type": "talk_to",
            "args_schema": {"npc_id": "string", "topic": "string"},
            "arg_options": {"npc_id": ["mira"]},
        },
        {
            "action_type": "move_to",
            "args_schema": {"location_id": "string"},
            "arg_options": {"location_id": ["guard_post"]},
        },
    ]
    observation = {
        "exploration_context": {
            "action_scores": {"talk_to:mira": 0.1, "move_to:guard_post": 0.9},
            "selection_policy": "Repeated conversations are lower priority, not forbidden.",
        }
    }

    class Profile:
        profile_id = "test"

        class identity:
            public_name = "Test"
            public_role = "Traveler"
            cover_story = ""
            private_background = ""

        class motivations:
            curiosity = wealth = prestige = safety = loyalty = truth_seeking = power = 0.0

        class personality:
            cautious = bold = empathetic = suspicious = patient = manipulative = 0.0

        class social_tendencies:
            default_honesty = "full"
            trusts_authority = trusts_scholars = trusts_merchants = willing_to_lie = willing_to_share_info = 0.0

        class exploration_style:
            primary_approach = "direct"
            avoids_public_attention = False

        private_goals = []
        secrets = []

        class boundaries:
            hard = []

    monkeypatch.setattr("src.agent.traveler_decision.call_openai_compatible_json", lambda **_: {"decision_reason": "missing action"})

    decision = decide_traveler_action(Profile(), observation, actions, use_llm=True)

    assert decision["mode"] == "deterministic_fallback"
    assert decision["selected_action"]["action_type"] == "move_to"
