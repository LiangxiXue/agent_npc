"""Traveler profile loader and validator.

Loads YAML profiles from data/travelers/, validates schema,
and produces immutable TravelerProfile objects for the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ── profile data classes ────────────────────────────────────────────────

@dataclass(frozen=True)
class Identity:
    public_name: str
    public_role: str
    cover_story: str = ""
    private_background: str = ""


@dataclass(frozen=True)
class Motivations:
    curiosity: float = 0.5
    wealth: float = 0.5
    prestige: float = 0.5
    safety: float = 0.5
    loyalty: float = 0.5
    truth_seeking: float = 0.5
    power: float = 0.5


@dataclass(frozen=True)
class Personality:
    cautious: float = 0.5
    bold: float = 0.5
    empathetic: float = 0.5
    suspicious: float = 0.5
    patient: float = 0.5
    manipulative: float = 0.5


@dataclass(frozen=True)
class SocialTendencies:
    default_honesty: float = 0.5
    trusts_authority: float = 0.5
    trusts_scholars: float = 0.5
    trusts_merchants: float = 0.5
    willing_to_lie: float = 0.5
    willing_to_share_info: float = 0.5
    willing_to_deceive_for_goal: float = 0.5


@dataclass(frozen=True)
class ExplorationStyle:
    primary_approach: str = "investigation_first"
    secondary_approaches: tuple[str, ...] = ()
    prefers_direct_questions: bool = True
    revisits_locations: bool = False
    avoids_public_attention: bool = False


@dataclass(frozen=True)
class Secret:
    secret_id: str
    label: str
    content: str
    disclosure_policy: str = ""
    exposure_risk: str = ""
    risk_level: str = "medium"


@dataclass(frozen=True)
class PrivateGoal:
    goal_id: str
    description: str
    priority: float = 0.5
    success_condition: str = ""


@dataclass(frozen=True)
class Boundaries:
    hard: tuple[str, ...] = ()
    soft: tuple[str, ...] = ()


@dataclass(frozen=True)
class TravelerProfile:
    """Immutable, validated traveler profile loaded from YAML."""
    profile_id: str
    version: str
    identity: Identity
    motivations: Motivations
    personality: Personality
    social_tendencies: SocialTendencies
    exploration_style: ExplorationStyle
    boundaries: Boundaries
    private_goals: tuple[PrivateGoal, ...]
    secrets: tuple[Secret, ...] = ()
    starting_location: str = "town_square"
    starting_inventory: tuple[str, ...] = ()
    private_notes: tuple[str, ...] = ()

    @property
    def primary_motivation(self) -> str:
        """Return the name of the highest-scored motivation."""
        scores = {
            "curiosity": self.motivations.curiosity,
            "wealth": self.motivations.wealth,
            "prestige": self.motivations.prestige,
            "safety": self.motivations.safety,
            "loyalty": self.motivations.loyalty,
            "truth_seeking": self.motivations.truth_seeking,
            "power": self.motivations.power,
        }
        return max(scores, key=lambda k: scores[k])  # type: ignore[no-any-return]

    @property
    def dominant_personality_trait(self) -> str:
        """Return the name of the most pronounced personality trait."""
        scores = {
            "cautious": self.personality.cautious,
            "bold": self.personality.bold,
            "empathetic": self.personality.empathetic,
            "suspicious": self.personality.suspicious,
            "patient": self.personality.patient,
            "manipulative": self.personality.manipulative,
        }
        return max(scores, key=lambda k: scores[k])  # type: ignore[no-any-return]


# ── loader ──────────────────────────────────────────────────────────────

def load_profile(profile_id: str, profiles_dir: str | Path | None = None) -> TravelerProfile:
    """Load and validate a single traveler profile by id.

    Args:
        profile_id: The profile identifier (matches the YAML filename without .yaml).
        profiles_dir: Optional override for the profiles directory.

    Returns:
        A validated TravelerProfile.

    Raises:
        FileNotFoundError: If the profile YAML does not exist.
        ValueError: If the profile fails validation.
    """
    directory = Path(profiles_dir) if profiles_dir else _default_profiles_dir()
    file_path = directory / f"{profile_id}.yaml"
    if not file_path.exists():
        raise FileNotFoundError(f"Traveler profile not found: {file_path}")
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Profile {profile_id} must be a YAML mapping, got {type(raw).__name__}")
    return _parse_profile(raw)


def list_available_profiles(profiles_dir: str | Path | None = None) -> list[str]:
    """List all available profile ids in the profiles directory."""
    directory = Path(profiles_dir) if profiles_dir else _default_profiles_dir()
    if not directory.exists():
        return []
    return sorted(
        p.stem for p in directory.glob("*.yaml")
        if p.is_file() and not p.name.startswith("_")
    )


def load_all_profiles(profiles_dir: str | Path | None = None) -> dict[str, TravelerProfile]:
    """Load all available profiles, keyed by profile_id."""
    return {
        pid: load_profile(pid, profiles_dir)
        for pid in list_available_profiles(profiles_dir)
    }


# ── validation ──────────────────────────────────────────────────────────

VALID_PRIMARY_APPROACHES = {
    "investigation_first",
    "follow_rumors",
    "revisit_clues",
    "find_allies_first",
    "avoid_attention",
}

VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}

REQUIRED_TOP_FIELDS = {
    "profile_id",
    "version",
    "identity",
    "motivations",
    "personality",
    "social_tendencies",
    "exploration_style",
    "private_goals",
    "boundaries",
}

MOTIVATION_KEYS = {"curiosity", "wealth", "prestige", "safety", "loyalty", "truth_seeking", "power"}
PERSONALITY_KEYS = {"cautious", "bold", "empathetic", "suspicious", "patient", "manipulative"}
SOCIAL_KEYS = {
    "default_honesty",
    "trusts_authority",
    "trusts_scholars",
    "trusts_merchants",
    "willing_to_lie",
    "willing_to_share_info",
    "willing_to_deceive_for_goal",
}
IDENTITY_KEYS = {"public_name", "public_role", "cover_story", "private_background"}
EXPLORATION_KEYS = {
    "primary_approach",
    "secondary_approaches",
    "prefers_direct_questions",
    "revisits_locations",
    "avoids_public_attention",
}
GOAL_REQUIRED_KEYS = {"goal_id", "description", "priority"}
SECRET_KEYS = {"secret_id", "label", "content", "disclosure_policy", "exposure_risk", "risk_level"}


def _default_profiles_dir() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "data" / "travelers"


def _parse_profile(raw: dict[str, Any]) -> TravelerProfile:
    profile_id = _require_str(raw, "profile_id")
    _validate_profile_id(profile_id)

    missing = REQUIRED_TOP_FIELDS - set(raw.keys())
    if missing:
        raise ValueError(f"Profile '{profile_id}': missing required top-level fields: {sorted(missing)}")

    identity = _parse_identity(raw["identity"], profile_id)
    motivations = _parse_motivations(raw["motivations"], profile_id)
    personality = _parse_personality(raw["personality"], profile_id)
    social = _parse_social(raw["social_tendencies"], profile_id)
    exploration = _parse_exploration(raw["exploration_style"], profile_id)
    boundaries = _parse_boundaries(raw["boundaries"], profile_id)
    goals = _parse_goals(raw["private_goals"], profile_id)
    secrets = _parse_secrets(raw.get("secrets", []), profile_id)

    return TravelerProfile(
        profile_id=profile_id,
        version=_require_str(raw, "version"),
        identity=identity,
        motivations=motivations,
        personality=personality,
        social_tendencies=social,
        exploration_style=exploration,
        boundaries=boundaries,
        private_goals=goals,
        secrets=secrets,
        starting_location=str(raw.get("starting_location", "town_square")),
        starting_inventory=tuple(_require_str_list(raw, "starting_inventory")),
        private_notes=tuple(_require_str_list(raw, "private_notes")),
    )


def _parse_identity(raw: Any, profile_id: str) -> Identity:
    if not isinstance(raw, dict):
        raise ValueError(f"Profile '{profile_id}': identity must be a mapping")
    return Identity(
        public_name=_require_str(raw, "public_name"),
        public_role=_require_str(raw, "public_role"),
        cover_story=str(raw.get("cover_story", "")),
        private_background=str(raw.get("private_background", "")),
    )


def _parse_motivations(raw: Any, profile_id: str) -> Motivations:
    if not isinstance(raw, dict):
        raise ValueError(f"Profile '{profile_id}': motivations must be a mapping")
    _validate_float_range(raw, MOTIVATION_KEYS, profile_id, "motivations")
    return Motivations(
        curiosity=float(raw.get("curiosity", 0.5)),
        wealth=float(raw.get("wealth", 0.5)),
        prestige=float(raw.get("prestige", 0.5)),
        safety=float(raw.get("safety", 0.5)),
        loyalty=float(raw.get("loyalty", 0.5)),
        truth_seeking=float(raw.get("truth_seeking", 0.5)),
        power=float(raw.get("power", 0.5)),
    )


def _parse_personality(raw: Any, profile_id: str) -> Personality:
    if not isinstance(raw, dict):
        raise ValueError(f"Profile '{profile_id}': personality must be a mapping")
    _validate_float_range(raw, PERSONALITY_KEYS, profile_id, "personality")
    return Personality(
        cautious=float(raw.get("cautious", 0.5)),
        bold=float(raw.get("bold", 0.5)),
        empathetic=float(raw.get("empathetic", 0.5)),
        suspicious=float(raw.get("suspicious", 0.5)),
        patient=float(raw.get("patient", 0.5)),
        manipulative=float(raw.get("manipulative", 0.5)),
    )


def _parse_social(raw: Any, profile_id: str) -> SocialTendencies:
    if not isinstance(raw, dict):
        raise ValueError(f"Profile '{profile_id}': social_tendencies must be a mapping")
    _validate_float_range(raw, SOCIAL_KEYS, profile_id, "social_tendencies")
    return SocialTendencies(
        default_honesty=float(raw.get("default_honesty", 0.5)),
        trusts_authority=float(raw.get("trusts_authority", 0.5)),
        trusts_scholars=float(raw.get("trusts_scholars", 0.5)),
        trusts_merchants=float(raw.get("trusts_merchants", 0.5)),
        willing_to_lie=float(raw.get("willing_to_lie", 0.5)),
        willing_to_share_info=float(raw.get("willing_to_share_info", 0.5)),
        willing_to_deceive_for_goal=float(raw.get("willing_to_deceive_for_goal", 0.5)),
    )


def _parse_exploration(raw: Any, profile_id: str) -> ExplorationStyle:
    if not isinstance(raw, dict):
        raise ValueError(f"Profile '{profile_id}': exploration_style must be a mapping")
    primary = str(raw.get("primary_approach", "investigation_first"))
    if primary not in VALID_PRIMARY_APPROACHES:
        raise ValueError(
            f"Profile '{profile_id}': primary_approach '{primary}' is not valid. "
            f"Must be one of: {sorted(VALID_PRIMARY_APPROACHES)}"
        )
    secondary = raw.get("secondary_approaches", [])
    if not isinstance(secondary, list):
        secondary = []
    for approach in secondary:
        if str(approach) not in VALID_PRIMARY_APPROACHES:
            raise ValueError(
                f"Profile '{profile_id}': secondary_approach '{approach}' is not valid."
            )
    return ExplorationStyle(
        primary_approach=primary,
        secondary_approaches=tuple(str(a) for a in secondary),
        prefers_direct_questions=bool(raw.get("prefers_direct_questions", True)),
        revisits_locations=bool(raw.get("revisits_locations", False)),
        avoids_public_attention=bool(raw.get("avoids_public_attention", False)),
    )


def _parse_boundaries(raw: Any, profile_id: str) -> Boundaries:
    if not isinstance(raw, dict):
        raise ValueError(f"Profile '{profile_id}': boundaries must be a mapping")
    hard = raw.get("hard", [])
    soft = raw.get("soft", [])
    if not isinstance(hard, list):
        hard = []
    if not isinstance(soft, list):
        soft = []
    hard_strs = tuple(str(item) for item in hard)
    if not hard_strs:
        raise ValueError(f"Profile '{profile_id}': at least one hard boundary is required")
    return Boundaries(
        hard=hard_strs,
        soft=tuple(str(item) for item in soft),
    )


def _parse_goals(raw: Any, profile_id: str) -> tuple[PrivateGoal, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"Profile '{profile_id}': private_goals must be a list")
    if len(raw) == 0:
        raise ValueError(f"Profile '{profile_id}': at least one private_goal is required")
    goals = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Profile '{profile_id}': private_goals[{i}] must be a mapping")
        missing = GOAL_REQUIRED_KEYS - set(item.keys())
        if missing:
            raise ValueError(
                f"Profile '{profile_id}': private_goals[{i}] missing required fields: {sorted(missing)}"
            )
        priority = float(item["priority"])
        if not (0.0 <= priority <= 1.0):
            raise ValueError(
                f"Profile '{profile_id}': private_goals[{i}].priority must be in [0.0, 1.0], got {priority}"
            )
        goals.append(PrivateGoal(
            goal_id=_require_str(item, "goal_id"),
            description=_require_str(item, "description"),
            priority=priority,
            success_condition=str(item.get("success_condition", "")),
        ))
    return tuple(goals)


def _parse_secrets(raw: Any, profile_id: str) -> tuple[Secret, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"Profile '{profile_id}': secrets must be a list")
    secrets = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Profile '{profile_id}': secrets[{i}] must be a mapping")
        missing = {"secret_id", "label", "content"} - set(item.keys())
        if missing:
            raise ValueError(
                f"Profile '{profile_id}': secrets[{i}] missing required fields: {sorted(missing)}"
            )
        risk = str(item.get("risk_level", "medium"))
        if risk not in VALID_RISK_LEVELS:
            raise ValueError(
                f"Profile '{profile_id}': secrets[{i}].risk_level '{risk}' not valid. "
                f"Must be one of: {sorted(VALID_RISK_LEVELS)}"
            )
        secrets.append(Secret(
            secret_id=_require_str(item, "secret_id"),
            label=_require_str(item, "label"),
            content=_require_str(item, "content"),
            disclosure_policy=str(item.get("disclosure_policy", "")),
            exposure_risk=str(item.get("exposure_risk", "")),
            risk_level=risk,
        ))
    return tuple(secrets)


# ── validation helpers ──────────────────────────────────────────────────

def _validate_profile_id(profile_id: str) -> None:
    if not profile_id or not isinstance(profile_id, str):
        raise ValueError("profile_id must be a non-empty string")
    # Only allow [a-z0-9_]
    for ch in profile_id:
        if ch not in "abcdefghijklmnopqrstuvwxyz0123456789_":
            raise ValueError(
                f"profile_id '{profile_id}' contains invalid character '{ch}'. "
                f"Only lowercase letters, digits, and underscores are allowed."
            )


def _validate_float_range(
    raw: dict[str, Any],
    expected_keys: set[str],
    profile_id: str,
    section: str,
) -> None:
    for key in expected_keys:
        if key in raw:
            value = float(raw[key])
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"Profile '{profile_id}': {section}.{key} must be in [0.0, 1.0], got {value}"
                )


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key, "")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{key}' must be a non-empty string, got {value!r}")
    return value.strip()


def _require_str_list(raw: dict[str, Any], key: str) -> list[str]:
    value = raw.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
