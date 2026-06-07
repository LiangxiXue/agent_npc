"""Tests for traveler profile loading, validation, and defaults."""

import os
import tempfile
import unittest
from pathlib import Path

# Ensure deterministic env before imports
os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
os.environ["AGENT_NPC_EMBEDDING_PROVIDER"] = "mock_hash"

from src.agent.traveler_profile import (  # noqa: E402
    Boundaries,
    ExplorationStyle,
    Identity,
    Motivations,
    Personality,
    PrivateGoal,
    Secret,
    SocialTendencies,
    TravelerProfile,
    list_available_profiles,
    load_all_profiles,
    load_profile,
)


class TravelerProfileLoaderTest(unittest.TestCase):
    """Test YAML loading, validation, and TravelerProfile construction."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.profiles_dir = Path(self.tmpdir)

    def _write_profile(self, profile_id: str, content: str) -> Path:
        path = self.profiles_dir / f"{profile_id}.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    # ── loading ──────────────────────────────────────────────────────

    def test_loads_valid_truth_seeking_scholar_profile(self) -> None:
        """The bundled truth_seeking_scholar profile must load without error."""
        profile = load_profile("truth_seeking_scholar")
        self.assertEqual(profile.profile_id, "truth_seeking_scholar")
        self.assertEqual(profile.identity.public_name, "Arin the Cartographer")
        self.assertAlmostEqual(profile.motivations.curiosity, 0.95)
        self.assertAlmostEqual(profile.personality.cautious, 0.60)
        self.assertEqual(len(profile.secrets), 1)
        self.assertEqual(len(profile.private_goals), 2)
        self.assertTrue(len(profile.boundaries.hard) >= 1)

    def test_loads_valid_suspicious_survivor_profile(self) -> None:
        profile = load_profile("suspicious_survivor")
        self.assertEqual(profile.profile_id, "suspicious_survivor")
        self.assertAlmostEqual(profile.motivations.safety, 0.95)
        self.assertAlmostEqual(profile.personality.suspicious, 0.90)
        self.assertEqual(profile.exploration_style.primary_approach, "avoid_attention")

    def test_loads_valid_opportunistic_relic_hunter_profile(self) -> None:
        profile = load_profile("opportunistic_relic_hunter")
        self.assertEqual(profile.profile_id, "opportunistic_relic_hunter")
        self.assertAlmostEqual(profile.motivations.wealth, 0.95)
        self.assertAlmostEqual(profile.personality.manipulative, 0.85)
        self.assertAlmostEqual(profile.social_tendencies.willing_to_lie, 0.90)

    def test_loads_ambitious_patron_scholar_profile(self) -> None:
        profile = load_profile("ambitious_patron_scholar")
        self.assertEqual(profile.profile_id, "ambitious_patron_scholar")
        self.assertIn("patron", profile.identity.public_role.lower())
        self.assertNotIn("merchant", profile.identity.public_role.lower())
        self.assertEqual(profile.starting_location, "market")
        self.assertGreater(profile.motivations.prestige, profile.motivations.wealth)
        self.assertGreater(profile.personality.manipulative, profile.personality.empathetic)
        self.assertTrue(any("Sable" in note for note in profile.private_notes))
        self.assertTrue(any("exclusive" in goal.description.lower() for goal in profile.private_goals))

    def test_list_available_profiles_finds_all_three(self) -> None:
        profiles = list_available_profiles()
        self.assertIn("truth_seeking_scholar", profiles)
        self.assertIn("suspicious_survivor", profiles)
        self.assertIn("opportunistic_relic_hunter", profiles)

    def test_load_all_profiles_returns_dict(self) -> None:
        all_profiles = load_all_profiles()
        self.assertGreaterEqual(len(all_profiles), 3)
        for pid in ("truth_seeking_scholar", "suspicious_survivor", "opportunistic_relic_hunter"):
            self.assertIn(pid, all_profiles)
            self.assertIsInstance(all_profiles[pid], TravelerProfile)

    def test_list_available_profiles_with_custom_dir(self) -> None:
        self._write_profile("test_a", _minimal_yaml("test_a"))
        self._write_profile("test_b", _minimal_yaml("test_b"))
        profiles = list_available_profiles(profiles_dir=self.profiles_dir)
        self.assertEqual(sorted(profiles), ["test_a", "test_b"])

    def test_skips_underscore_prefixed_files(self) -> None:
        self._write_profile("test_a", _minimal_yaml("test_a"))
        self._write_profile("_template", _minimal_yaml("_template"))
        profiles = list_available_profiles(profiles_dir=self.profiles_dir)
        self.assertEqual(profiles, ["test_a"])

    # ── defaults ─────────────────────────────────────────────────────

    def test_fills_defaults_for_optional_fields(self) -> None:
        self._write_profile("minimal", _minimal_yaml("minimal"))
        profile = load_profile("minimal", profiles_dir=self.profiles_dir)
        self.assertEqual(profile.starting_location, "town_square")
        self.assertEqual(profile.starting_inventory, ())
        self.assertEqual(profile.private_notes, ())
        self.assertEqual(profile.secrets, ())
        self.assertEqual(profile.identity.cover_story, "")
        self.assertEqual(profile.identity.private_background, "")

    def test_default_motivation_values(self) -> None:
        self._write_profile("defaults", _minimal_yaml("defaults"))
        profile = load_profile("defaults", profiles_dir=self.profiles_dir)
        self.assertAlmostEqual(profile.motivations.power, 0.5)
        self.assertAlmostEqual(profile.personality.manipulative, 0.5)

    # ── profile properties ───────────────────────────────────────────

    def test_primary_motivation_returns_highest(self) -> None:
        profile = load_profile("truth_seeking_scholar")
        self.assertEqual(profile.primary_motivation, "curiosity")

    def test_dominant_personality_trait_returns_highest(self) -> None:
        profile = load_profile("suspicious_survivor")
        self.assertEqual(profile.dominant_personality_trait, "suspicious")

    # ── validation errors ────────────────────────────────────────────

    def test_raises_on_missing_profile(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_profile("nonexistent_profile_xyz")

    def test_raises_on_invalid_profile_id_characters(self) -> None:
        self._write_profile("Bad-Name!", _minimal_yaml("Bad-Name!"))
        with self.assertRaises(ValueError):
            load_profile("Bad-Name!", profiles_dir=self.profiles_dir)

    def test_raises_on_missing_required_top_level_field(self) -> None:
        yaml_content = """\
profile_id: missing_boundaries
version: "1.0"
identity:
  public_name: Test
  public_role: Tester
motivations:
  curiosity: 0.5
personality:
  cautious: 0.5
social_tendencies:
  default_honesty: 0.5
exploration_style:
  primary_approach: investigation_first
private_goals:
  - goal_id: g1
    description: test
    priority: 0.5
"""
        self._write_profile("missing_boundaries", yaml_content)
        with self.assertRaises(ValueError) as ctx:
            load_profile("missing_boundaries", profiles_dir=self.profiles_dir)
        self.assertIn("boundaries", str(ctx.exception))

    def test_raises_when_no_hard_boundaries(self) -> None:
        yaml_content = """\
profile_id: no_hard
version: "1.0"
identity:
  public_name: Test
  public_role: Tester
motivations:
  curiosity: 0.5
personality:
  cautious: 0.5
social_tendencies:
  default_honesty: 0.5
exploration_style:
  primary_approach: investigation_first
private_goals:
  - goal_id: g1
    description: test
    priority: 0.5
boundaries:
  hard: []
  soft: []
"""
        self._write_profile("no_hard", yaml_content)
        with self.assertRaises(ValueError) as ctx:
            load_profile("no_hard", profiles_dir=self.profiles_dir)
        self.assertIn("hard boundary", str(ctx.exception))

    def test_raises_when_no_private_goals(self) -> None:
        yaml_content = """\
profile_id: no_goals
version: "1.0"
identity:
  public_name: Test
  public_role: Tester
motivations:
  curiosity: 0.5
personality:
  cautious: 0.5
social_tendencies:
  default_honesty: 0.5
exploration_style:
  primary_approach: investigation_first
private_goals: []
boundaries:
  hard:
    - "no harm"
"""
        self._write_profile("no_goals", yaml_content)
        with self.assertRaises(ValueError) as ctx:
            load_profile("no_goals", profiles_dir=self.profiles_dir)
        self.assertIn("private_goal", str(ctx.exception))

    def test_raises_on_motivation_out_of_range(self) -> None:
        yaml_content = _minimal_yaml("bad_motivation").replace("curiosity: 0.5", "curiosity: 1.5")
        self._write_profile("bad_motivation", yaml_content)
        with self.assertRaises(ValueError) as ctx:
            load_profile("bad_motivation", profiles_dir=self.profiles_dir)
        self.assertIn("curiosity", str(ctx.exception))

    def test_raises_on_personality_out_of_range(self) -> None:
        yaml_content = _minimal_yaml("bad_personality").replace("cautious: 0.5", "cautious: -0.1")
        self._write_profile("bad_personality", yaml_content)
        with self.assertRaises(ValueError):
            load_profile("bad_personality", profiles_dir=self.profiles_dir)

    def test_raises_on_goal_priority_out_of_range(self) -> None:
        yaml_content = _minimal_yaml("bad_goal_priority").replace("priority: 0.5", "priority: 2.0")
        self._write_profile("bad_goal_priority", yaml_content)
        with self.assertRaises(ValueError) as ctx:
            load_profile("bad_goal_priority", profiles_dir=self.profiles_dir)
        self.assertIn("priority", str(ctx.exception))

    def test_raises_on_invalid_primary_approach(self) -> None:
        yaml_content = _minimal_yaml("bad_approach").replace(
            "primary_approach: investigation_first",
            "primary_approach: totally_chaotic",
        )
        self._write_profile("bad_approach", yaml_content)
        with self.assertRaises(ValueError) as ctx:
            load_profile("bad_approach", profiles_dir=self.profiles_dir)
        self.assertIn("primary_approach", str(ctx.exception))

    def test_raises_on_invalid_risk_level(self) -> None:
        yaml_content = """\
profile_id: bad_risk
version: "1.0"
identity:
  public_name: Test
  public_role: Tester
motivations:
  curiosity: 0.5
personality:
  cautious: 0.5
social_tendencies:
  default_honesty: 0.5
exploration_style:
  primary_approach: investigation_first
private_goals:
  - goal_id: g1
    description: test
    priority: 0.5
boundaries:
  hard:
    - "no harm"
secrets:
  - secret_id: s1
    label: Test Secret
    content: Something hidden
    risk_level: apocalypse
"""
        self._write_profile("bad_risk", yaml_content)
        with self.assertRaises(ValueError) as ctx:
            load_profile("bad_risk", profiles_dir=self.profiles_dir)
        self.assertIn("risk_level", str(ctx.exception))

    def test_raises_on_secret_missing_label(self) -> None:
        yaml_content = """\
profile_id: bad_secret
version: "1.0"
identity:
  public_name: Test
  public_role: Tester
motivations:
  curiosity: 0.5
personality:
  cautious: 0.5
social_tendencies:
  default_honesty: 0.5
exploration_style:
  primary_approach: investigation_first
private_goals:
  - goal_id: g1
    description: test
    priority: 0.5
boundaries:
  hard:
    - "no harm"
secrets:
  - secret_id: s1
    content: Something hidden
"""
        self._write_profile("bad_secret", yaml_content)
        with self.assertRaises(ValueError) as ctx:
            load_profile("bad_secret", profiles_dir=self.profiles_dir)
        self.assertIn("label", str(ctx.exception))


def _minimal_yaml(profile_id: str) -> str:
    return f"""\
profile_id: {profile_id}
version: "1.0"
identity:
  public_name: Test
  public_role: Tester
motivations:
  curiosity: 0.5
personality:
  cautious: 0.5
social_tendencies:
  default_honesty: 0.5
exploration_style:
  primary_approach: investigation_first
private_goals:
  - goal_id: g1
    description: test goal
    priority: 0.5
boundaries:
  hard:
    - "do not harm"
"""
