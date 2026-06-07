"""Soft information-gain planner for Traveler exploration."""

from __future__ import annotations

from typing import Any


def build_exploration_context(
    traveler_id: str,
    observation: dict[str, Any],
    available_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build soft exploration priorities for the Traveler decision layer.

    Repeating the same conversation is never blocked here. The planner only
    lowers its information-gain score when the recent trace has no new evidence.
    """
    recent_events = observation.get("recent_events", [])
    if not isinstance(recent_events, list):
        recent_events = []

    conversation_threads = _conversation_threads(traveler_id, recent_events)
    conversation_coverage = _conversation_coverage(observation, recent_events)
    route_focus = _route_focus(observation)
    leads = _minimal_leads(observation, recent_events, route_focus, conversation_coverage)
    current_location = _current_location(observation)
    action_scores = _score_available_actions(
        available_actions,
        conversation_threads,
        leads,
        recent_events,
        current_location,
        route_focus,
    )

    return {
        "traveler_id": traveler_id,
        "route_focus": route_focus,
        "conversation_threads": conversation_threads,
        "conversation_coverage": conversation_coverage,
        "leads": leads,
        "action_scores": action_scores,
        "selection_policy": (
            "Repeated same NPC/topic conversations without new evidence are lower priority, "
            "not forbidden; repeat conversation remains allowed when new evidence appears. "
            "Use conversation_coverage as the factual source for which key NPCs have already been interviewed."
        ),
    }


def _conversation_threads(traveler_id: str, recent_events: list[Any]) -> list[dict[str, Any]]:
    threads_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, event in enumerate(recent_events):
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "traveler_talked_to_npc":
            continue
        if event.get("source_id") not in (None, "", traveler_id, "traveler"):
            continue

        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        npc_id = str(payload.get("npc_id") or _extract_after(event.get("content", ""), "talked to")).strip()
        topic = str(payload.get("topic") or _extract_topic(event.get("content", "")) or "local rumors").strip()
        if not npc_id:
            continue

        key = (npc_id.lower(), topic.lower())
        threads_by_key[key] = {
            "npc_id": npc_id.lower(),
            "topic": topic.lower(),
            "last_event_index": index,
            "status": "waiting_for_external_evidence",
            "new_evidence_count": 0,
        }

    for thread in threads_by_key.values():
        evidence = [
            event
            for event in recent_events[thread["last_event_index"] + 1:]
            if _is_evidence_related_to_thread(event, thread["npc_id"], thread["topic"])
        ]
        if evidence:
            thread["status"] = "open_with_new_evidence"
            thread["new_evidence_count"] = len(evidence)

    return sorted(threads_by_key.values(), key=lambda item: (item["npc_id"], item["topic"]))


def _conversation_coverage(observation: dict[str, Any], recent_events: list[Any]) -> dict[str, Any]:
    key_npcs = _key_npc_ids(observation)
    interviewed = set(_talked_npc_ids(recent_events))

    relationships = observation.get("relationships")
    if isinstance(relationships, dict):
        for npc_id, rel in relationships.items():
            if not isinstance(rel, dict):
                continue
            if _relationship_indicates_contact(rel):
                interviewed.add(str(npc_id).lower())

    interviewed_npcs = sorted(npc_id for npc_id in key_npcs if npc_id in interviewed)
    not_yet_interviewed = sorted(npc_id for npc_id in key_npcs if npc_id not in interviewed)
    return {
        "interviewed_npcs": interviewed_npcs,
        "not_yet_interviewed_npcs": not_yet_interviewed,
        "all_key_npcs_interviewed": not not_yet_interviewed,
        "guidance": "Do not claim all key NPCs have been interviewed until not_yet_interviewed_npcs is empty.",
    }


def _key_npc_ids(observation: dict[str, Any]) -> list[str]:
    for field in ("relationships", "npc_states"):
        value = observation.get(field)
        if isinstance(value, dict) and value:
            return sorted(str(npc_id).lower() for npc_id in value)
    return []


def _talked_npc_ids(recent_events: list[Any]) -> list[str]:
    npc_ids: list[str] = []
    for event in recent_events:
        if not isinstance(event, dict) or event.get("event_type") != "traveler_talked_to_npc":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        npc_id = str(payload.get("npc_id") or _extract_after(event.get("content", ""), "talked to")).strip()
        if npc_id:
            npc_ids.append(npc_id.lower())
    return npc_ids


def _relationship_indicates_contact(relationship: dict[str, Any]) -> bool:
    for field in ("trust", "suspicion", "affinity", "leverage", "exposure", "debt"):
        try:
            if abs(float(relationship.get(field, 0.0))) > 0.0001:
                return True
        except (TypeError, ValueError):
            continue
    return str(relationship.get("last_tone", "neutral")).lower() not in {"", "neutral"}


def _route_focus(observation: dict[str, Any]) -> str:
    traveler_state = observation.get("traveler_state")
    if not isinstance(traveler_state, dict):
        return "balanced"
    notes = traveler_state.get("private_notes")
    if not isinstance(notes, list):
        return "balanced"
    text = " ".join(str(note).lower() for note in notes)
    if "sable" in text and ("informal" in text or "unofficial" in text or "network" in text):
        return "sable"
    return "balanced"


def _minimal_leads(
    observation: dict[str, Any],
    recent_events: list[Any],
    route_focus: str = "balanced",
    conversation_coverage: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    current_location = _current_location(observation)
    has_field_evidence = any(_is_evidence_event(event) for event in recent_events)
    leads = [
        {
            "lead_id": "ask_ron_about_guard_ledger",
            "action_type": "move_to",
            "target": "guard_post",
            "reason": "Mira thread needs external procedural evidence.",
        },
        {
            "lead_id": "question_sable_about_rumors",
            "action_type": "move_to",
            "target": "market",
            "reason": "Ruins rumors need adversarial cross-checking.",
        },
        {
            "lead_id": "inspect_tavern_back_alley",
            "action_type": "move_to",
            "target": "tavern",
            "reason": "Guardian route needs physical evidence.",
        },
    ]
    if has_field_evidence and current_location != "archive":
        leads.append(
            {
                "lead_id": "return_to_mira_with_field_notes",
                "action_type": "move_to",
                "target": "archive",
                "reason": "New field evidence should be interpreted by Mira.",
            }
        )
    if route_focus == "sable" and current_location != "market":
        leads.append(
            {
                "lead_id": "return_to_sable_with_leads",
                "action_type": "move_to",
                "target": "market",
                "reason": "Private goals favor returning unofficial leads to Sable's network.",
            }
        )
    if route_focus == "sable" and current_location != "archive" and _sable_route_needs_mira_consult(conversation_coverage):
        leads.append(
            {
                "lead_id": "consult_mira_discreetly",
                "action_type": "move_to",
                "target": "archive",
                "reason": "Sable route still needs Mira's interpretation before the final synthesis returns to informal channels.",
            }
        )
    if current_location:
        leads = [lead for lead in leads if lead["target"] != current_location]
    return leads


def _sable_route_needs_mira_consult(conversation_coverage: dict[str, Any] | None) -> bool:
    if not isinstance(conversation_coverage, dict):
        return False
    interviewed = {
        str(npc_id).lower()
        for npc_id in conversation_coverage.get("interviewed_npcs", [])
        if str(npc_id).strip()
    }
    pending = {
        str(npc_id).lower()
        for npc_id in conversation_coverage.get("not_yet_interviewed_npcs", [])
        if str(npc_id).strip()
    }
    return "mira" in pending and {"sable", "ron", "lina"}.issubset(interviewed)


def _score_available_actions(
    available_actions: list[dict[str, Any]],
    conversation_threads: list[dict[str, Any]],
    leads: list[dict[str, Any]],
    recent_events: list[Any],
    current_location: str,
    route_focus: str = "balanced",
) -> dict[str, float]:
    scores: dict[str, float] = {}
    lead_scores = {
        f"{lead['action_type']}:{lead['target']}": _lead_score(lead, recent_events)
        for lead in leads
        if isinstance(lead.get("action_type"), str) and isinstance(lead.get("target"), str)
    }
    local_followups = _local_followup_scores(current_location, recent_events, route_focus)
    thread_by_npc = {thread["npc_id"]: thread for thread in conversation_threads}

    for action in available_actions:
        action_type = str(action.get("action_type", ""))
        options = action.get("arg_options") if isinstance(action.get("arg_options"), dict) else {}

        if action_type == "move_to":
            for location_id in _string_options(options.get("location_id")):
                key = f"move_to:{location_id}"
                scores[key] = round(lead_scores.get(key, 0.45), 3)
        elif action_type in {"talk_to", "ask_for_help", "share_information"}:
            for npc_id in _string_options(options.get("npc_id")):
                thread = thread_by_npc.get(npc_id.lower())
                key = f"{action_type}:{npc_id}"
                scores[key] = round(
                    max(
                        _conversation_score(thread, recent_events),
                        local_followups.get(key, 0.0),
                    ),
                    3,
                )
        else:
            scores[action_type] = 0.35

    return scores


def _current_location(observation: dict[str, Any]) -> str:
    traveler_state = observation.get("traveler_state")
    if not isinstance(traveler_state, dict):
        return ""
    return str(traveler_state.get("current_location", ""))


def _local_followup_scores(current_location: str, recent_events: list[Any], route_focus: str = "balanced") -> dict[str, float]:
    if current_location == "market" and route_focus == "sable":
        return {
            "talk_to:sable": 0.94,
            "ask_for_help:sable": 0.90,
            "share_information:sable": 0.92,
        }
    if current_location == "guard_post" and not _has_recent_talk_with(recent_events, "ron"):
        return {
            "talk_to:ron": 0.91,
            "ask_for_help:ron": 0.88,
            "share_information:ron": 0.82,
        }
    if current_location == "market" and not _has_recent_talk_with(recent_events, "sable"):
        return {
            "talk_to:sable": 0.9,
            "ask_for_help:sable": 0.86,
            "share_information:sable": 0.82,
        }
    return {}


def _has_recent_talk_with(recent_events: list[Any], npc_id: str) -> bool:
    expected = npc_id.lower()
    for event in recent_events[-4:]:
        if not isinstance(event, dict) or event.get("event_type") != "traveler_talked_to_npc":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if str(payload.get("npc_id", "")).lower() == expected:
            return True
    return False


def _lead_score(lead: dict[str, Any], recent_events: list[Any]) -> float:
    base_scores = {
        "ask_ron_about_guard_ledger": 0.82,
        "question_sable_about_rumors": 0.78,
        "inspect_tavern_back_alley": 0.68,
        "return_to_mira_with_field_notes": 0.86,
        "return_to_sable_with_leads": 0.94,
        "consult_mira_discreetly": 0.96,
    }
    score = base_scores.get(str(lead.get("lead_id", "")), 0.45)
    if lead.get("lead_id") != "return_to_mira_with_field_notes" and any(_is_evidence_event(event) for event in recent_events):
        score = max(0.35, score - 0.25)
    return round(score, 3)


def _conversation_score(thread: dict[str, Any] | None, recent_events: list[Any]) -> float:
    if thread is None:
        return 0.72 if any(_is_evidence_event(event) for event in recent_events) else 0.58
    if thread["status"] == "open_with_new_evidence":
        return 0.88
    return 0.28


def _is_evidence_related_to_thread(event: Any, npc_id: str, topic: str) -> bool:
    if not _is_evidence_event(event):
        return False
    haystack = _event_text(event)
    return npc_id.lower() in haystack or topic.lower() in haystack or "field_notes" in haystack


def _is_evidence_event(event: Any) -> bool:
    if not isinstance(event, dict):
        return False
    event_type = str(event.get("event_type", "")).lower()
    if "evidence" in event_type or "investigated" in event_type or "clue" in event_type:
        return True
    return any(token in _event_text(event) for token in ("evidence", "clue", "field notes", "field_notes", "inscription"))


def _event_text(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    parts = [str(event.get("content", ""))]
    payload = event.get("payload")
    if isinstance(payload, dict):
        parts.extend(str(value) for value in payload.values())
    return " ".join(parts).lower()


def _string_options(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _extract_topic(content: Any) -> str:
    text = str(content)
    if "'" in text:
        parts = text.split("'")
        if len(parts) >= 3:
            return parts[1]
    if "about" in text:
        return text.rsplit("about", 1)[-1].strip(" .")
    return ""


def _extract_after(content: Any, marker: str) -> str:
    text = str(content).lower()
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].strip().split(" ", 1)[0].strip(" .:'\"")
