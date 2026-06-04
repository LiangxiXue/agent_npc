"""Traveler state, relationship, and secret managers.

High-level wrappers around database functions for Traveler state lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.storage import database


@dataclass
class TravelerStateManager:
    """Manages initialization and mutation of a single Traveler's runtime state."""

    traveler_id: str

    def initialize(self, profile_id: str, starting_location: str, inventory: list[str] | None = None, private_notes: list[str] | None = None) -> dict[str, Any]:
        return database.upsert_traveler_state(
            traveler_id=self.traveler_id,
            profile_id=profile_id,
            current_location=starting_location,
            inventory=inventory or [],
            private_notes=private_notes or [],
            active_goal={},
        )

    def get_state(self) -> dict[str, Any]:
        return database.get_traveler_state(self.traveler_id)

    def move_to(self, location_id: str) -> dict[str, Any]:
        return database.update_traveler_location(self.traveler_id, location_id)

    def add_inventory_item(self, item: str) -> dict[str, Any]:
        state = self.get_state()
        inv = list(state["inventory"])
        if item not in inv:
            inv.append(item)
        return database.update_traveler_inventory(self.traveler_id, inv)

    def remove_inventory_item(self, item: str) -> dict[str, Any]:
        state = self.get_state()
        inv = [i for i in state["inventory"] if i != item]
        return database.update_traveler_inventory(self.traveler_id, inv)

    def add_private_note(self, note: str) -> dict[str, Any]:
        state = self.get_state()
        notes = list(state["private_notes"])
        notes.append(note)
        return database.upsert_traveler_state(
            traveler_id=self.traveler_id,
            profile_id=state["profile_id"],
            current_location=state["current_location"],
            inventory=state["inventory"],
            private_notes=notes,
            active_goal=state["active_goal"],
        )

    def set_active_goal(self, goal: dict[str, Any]) -> dict[str, Any]:
        state = self.get_state()
        return database.upsert_traveler_state(
            traveler_id=self.traveler_id,
            profile_id=state["profile_id"],
            current_location=state["current_location"],
            inventory=state["inventory"],
            private_notes=state["private_notes"],
            active_goal=goal,
        )

    @property
    def current_location(self) -> str:
        return str(self.get_state()["current_location"])

    @property
    def inventory(self) -> list[str]:
        return list(self.get_state()["inventory"])

    @property
    def private_notes(self) -> list[str]:
        return list(self.get_state()["private_notes"])


@dataclass
class TravelerRelationshipManager:
    """Manages Traveler-NPC relationship states."""

    traveler_id: str

    def initialize_for_npc(self, npc_id: str) -> dict[str, Any]:
        """Create a default relationship row for a new NPC contact."""
        return database.upsert_traveler_relationship(
            traveler_id=self.traveler_id,
            npc_id=npc_id,
        )

    def get(self, npc_id: str) -> dict[str, Any]:
        rel = database.get_traveler_relationship(self.traveler_id, npc_id)
        if rel is None:
            return self.initialize_for_npc(npc_id)
        return rel

    def get_all(self) -> dict[str, dict[str, Any]]:
        rels = database.get_all_traveler_relationships(self.traveler_id)
        return {rel["npc_id"]: rel for rel in rels}

    def update_trust(self, npc_id: str, delta: float) -> dict[str, Any]:
        current = self.get(npc_id)
        new_val = _clamp(float(current["trust"]) + delta, -1.0, 1.0)
        return database.upsert_traveler_relationship(
            traveler_id=self.traveler_id, npc_id=npc_id, trust=new_val,
        )

    def update_suspicion(self, npc_id: str, delta: float) -> dict[str, Any]:
        current = self.get(npc_id)
        new_val = _clamp(float(current["suspicion"]) + delta, 0.0, 1.0)
        return database.upsert_traveler_relationship(
            traveler_id=self.traveler_id, npc_id=npc_id, suspicion=new_val,
        )

    def update_affinity(self, npc_id: str, delta: float) -> dict[str, Any]:
        current = self.get(npc_id)
        new_val = _clamp(float(current["affinity"]) + delta, -1.0, 1.0)
        return database.upsert_traveler_relationship(
            traveler_id=self.traveler_id, npc_id=npc_id, affinity=new_val,
        )

    def update_exposure(self, npc_id: str, delta: float) -> dict[str, Any]:
        current = self.get(npc_id)
        new_val = _clamp(float(current["exposure"]) + delta, 0.0, 1.0)
        return database.upsert_traveler_relationship(
            traveler_id=self.traveler_id, npc_id=npc_id, exposure=new_val,
        )

    def set_tone(self, npc_id: str, tone: str) -> dict[str, Any]:
        return database.upsert_traveler_relationship(
            traveler_id=self.traveler_id, npc_id=npc_id, last_tone=tone,
        )

    def add_known_secret(self, npc_id: str, secret_id: str) -> dict[str, Any]:
        current = self.get(npc_id)
        secrets = list(current["known_secret_ids"])
        if secret_id not in secrets:
            secrets.append(secret_id)
        return database.upsert_traveler_relationship(
            traveler_id=self.traveler_id, npc_id=npc_id, known_secret_ids=secrets,
        )

    def snapshot_changes(self, npc_id: str, after: dict[str, Any]) -> list[dict[str, Any]]:
        """Compare current relationship state against `after`, returning a list of changes."""
        before = self.get(npc_id)
        changes = []
        for field in ["trust", "suspicion", "affinity", "leverage", "exposure", "debt", "last_tone"]:
            before_val = before.get(field, 0)
            after_val = after.get(field, 0)
            if before_val != after_val:
                changes.append({
                    "npc_id": npc_id,
                    "field": field,
                    "before": before_val,
                    "after": after_val,
                })
        return changes


@dataclass
class SecretTracker:
    """Tracks secrets and disclosures for both Traveler and NPC actors."""

    def register_secret(
        self, secret_id: str, owner_id: str, owner_type: str, label: str, content: str, risk_level: str = "medium",
    ) -> dict[str, Any]:
        return database.upsert_secret(
            secret_id=secret_id, owner_id=owner_id, owner_type=owner_type,
            label=label, content=content, risk_level=risk_level,
        )

    def get(self, secret_id: str) -> dict[str, Any] | None:
        return database.get_secret(secret_id)

    def record_disclosure(
        self, secret_id: str, disclosed_to: str, actor_type: str, round_number: int, method: str = "voluntary",
    ) -> dict[str, Any]:
        return database.record_secret_disclosure(
            secret_id=secret_id,
            disclosed_to_actor_id=disclosed_to,
            disclosed_to_actor_type=actor_type,
            round_number=round_number,
            method=method,
        )

    def get_disclosure_count(self, secret_id: str) -> int:
        secret = self.get(secret_id)
        if secret is None:
            return 0
        return int(secret.get("exposure_count", 0))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
