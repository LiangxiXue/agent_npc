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
    leads = _minimal_leads(observation, recent_events)
    action_scores = _score_available_actions(available_actions, conversation_threads, leads, recent_events)

    return {
        "traveler_id": traveler_id,
        "conversation_threads": conversation_threads,
        "leads": leads,
        "action_scores": action_scores,
        "selection_policy": (
            "Repeated same NPC/topic conversations without new evidence are lower priority, "
            "not forbidden; repeat conversation remains allowed when new evidence appears."
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


def _minimal_leads(observation: dict[str, Any], recent_events: list[Any]) -> list[dict[str, Any]]:
    current_location = str(
        observation.get("traveler_state", {}).get("current_location", "")
        if isinstance(observation.get("traveler_state"), dict)
        else ""
    )
    leads = [
        {
            "lead_id": "check_guard_post",
            "target_action_key": "move_to:guard_post",
            "location_id": "guard_post",
            "reason": "Guard records can provide external evidence before repeating a stalled topic.",
            "score": 0.82,
        },
        {
            "lead_id": "check_tavern",
            "target_action_key": "move_to:tavern",
            "location_id": "tavern",
            "reason": "Tavern rumors can provide ambient evidence for ruins conversations.",
            "score": 0.62,
        },
    ]
    if current_location:
        leads = [lead for lead in leads if lead["location_id"] != current_location]
    if any(_is_evidence_event(event) for event in recent_events):
        for lead in leads:
            lead["score"] = round(max(0.35, float(lead["score"]) - 0.25), 3)
    return leads


def _score_available_actions(
    available_actions: list[dict[str, Any]],
    conversation_threads: list[dict[str, Any]],
    leads: list[dict[str, Any]],
    recent_events: list[Any],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    lead_scores = {lead["target_action_key"]: float(lead["score"]) for lead in leads}
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
                scores[key] = round(_conversation_score(thread, recent_events), 3)
        else:
            scores[action_type] = 0.35

    return scores


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
