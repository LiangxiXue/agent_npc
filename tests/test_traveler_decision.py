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


def test_fallback_picks_highest_information_gain_move_location() -> None:
    actions = [
        {
            "action_type": "move_to",
            "args_schema": {"location_id": "string"},
            "arg_options": {"location_id": ["guard_post", "market", "tavern"]},
        }
    ]
    biases = [ActionBias("move_to", (), (), "low", 0.5)]
    exploration_context = {
        "action_scores": {
            "move_to:guard_post": 0.7,
            "move_to:market": 0.95,
            "move_to:tavern": 0.8,
        },
        "selection_policy": "Follow the highest information-gain lead.",
    }

    decision = deterministic_fallback_decision(actions, biases, exploration_context=exploration_context)

    assert decision["selected_action"]["action_type"] == "move_to"
    assert decision["selected_action"]["args"]["location_id"] == "market"


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


def test_llm_sable_route_corrects_low_score_official_detour(monkeypatch) -> None:
    actions = [
        {
            "action_type": "talk_to",
            "description": "Talk to a nearby NPC.",
            "args_schema": {"npc_id": "string", "topic": "string"},
            "arg_options": {"npc_id": ["sable"]},
            "effects": ["conversation"],
            "forbidden_effects": [],
        },
        {
            "action_type": "move_to",
            "description": "Move to another location.",
            "args_schema": {"location_id": "string"},
            "arg_options": {"location_id": ["guard_post"]},
            "effects": ["location_change"],
            "forbidden_effects": [],
        },
    ]
    observation = {
        "exploration_context": {
            "route_focus": "sable",
            "action_scores": {"talk_to:sable": 0.94, "move_to:guard_post": 0.82},
            "selection_policy": "Sable route should prioritize the highest-scored Sable action.",
        }
    }

    class Profile:
        profile_id = "ambitious_patron_scholar"

        class identity:
            public_name = "Elyan"
            public_role = "patron-scholar"
            cover_story = ""
            private_background = ""

        class motivations:
            curiosity = wealth = prestige = safety = loyalty = truth_seeking = power = 0.0

        class personality:
            cautious = bold = empathetic = suspicious = patient = manipulative = 0.0

        class social_tendencies:
            default_honesty = 0.42
            trusts_authority = trusts_scholars = trusts_merchants = willing_to_lie = willing_to_share_info = 0.0
            willing_to_deceive_for_goal = 0.0

        class exploration_style:
            primary_approach = "follow_rumors"
            avoids_public_attention = False

        private_goals = []
        secrets = []

        class boundaries:
            hard = []

    monkeypatch.setattr(
        "src.agent.traveler_decision.call_openai_compatible_json",
        lambda **_: {
            "selected_action": {"action_type": "move_to", "args": {"location_id": "guard_post"}},
            "traveler_utterance": "",
            "decision_reason": "Ask official sources before returning to Sable.",
        },
    )

    decision = decide_traveler_action(Profile(), observation, actions, use_llm=True, allow_llm_fallback=False)

    assert decision["mode"] == "llm"
    assert decision["selected_action"]["action_type"] == "talk_to"
    assert decision["selected_action"]["args"]["npc_id"] == "sable"
    assert decision["decision_adjustment"]["original_selected_action"]["action_type"] == "move_to"


def test_llm_sable_route_allows_first_time_key_npc_coverage(monkeypatch) -> None:
    actions = [
        {
            "action_type": "talk_to",
            "description": "Talk to a nearby NPC.",
            "args_schema": {"npc_id": "string", "topic": "string"},
            "arg_options": {"npc_id": ["sable"]},
            "effects": ["conversation"],
            "forbidden_effects": [],
        },
        {
            "action_type": "move_to",
            "description": "Move to another location.",
            "args_schema": {"location_id": "string"},
            "arg_options": {"location_id": ["guard_post"]},
            "effects": ["location_change"],
            "forbidden_effects": [],
        },
    ]
    observation = {
        "exploration_context": {
            "route_focus": "sable",
            "conversation_coverage": {
                "interviewed_npcs": ["sable"],
                "not_yet_interviewed_npcs": ["ron"],
            },
            "action_scores": {"talk_to:sable": 0.94, "move_to:guard_post": 0.82},
            "selection_policy": "Interview each key NPC once, then return synthesis to Sable.",
        }
    }

    class Profile:
        profile_id = "ambitious_patron_scholar"

        class identity:
            public_name = "Elyan"
            public_role = "patron-scholar"
            cover_story = ""
            private_background = ""

        class motivations:
            curiosity = wealth = prestige = safety = loyalty = truth_seeking = power = 0.0

        class personality:
            cautious = bold = empathetic = suspicious = patient = manipulative = 0.0

        class social_tendencies:
            default_honesty = 0.42
            trusts_authority = trusts_scholars = trusts_merchants = willing_to_lie = willing_to_share_info = 0.0
            willing_to_deceive_for_goal = 0.0

        class exploration_style:
            primary_approach = "follow_rumors"
            avoids_public_attention = False

        private_goals = []
        secrets = []

        class boundaries:
            hard = []

    monkeypatch.setattr(
        "src.agent.traveler_decision.call_openai_compatible_json",
        lambda **_: {
            "selected_action": {"action_type": "move_to", "args": {"location_id": "guard_post"}},
            "traveler_utterance": "",
            "decision_reason": "Interview Ron once before returning the pattern to Sable.",
        },
    )

    decision = decide_traveler_action(Profile(), observation, actions, use_llm=True, allow_llm_fallback=False)

    assert decision["mode"] == "llm"
    assert decision["selected_action"]["action_type"] == "move_to"
    assert decision["selected_action"]["args"]["location_id"] == "guard_post"
    assert "decision_adjustment" not in decision
