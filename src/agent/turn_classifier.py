from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TurnType = Literal[
    "casual_chat",
    "task_claim",
    "task_start",
    "sensitive_info",
    "social_maneuver",
    "ambiguous",
]


@dataclass(frozen=True)
class TurnClassification:
    turn_type: TurnType
    confidence: float
    reason: str


def classify_turn(player_input: str, npc_id: str, quest_status: str) -> TurnClassification:
    text = player_input.lower()
    if has_any(text, ["那件事", "处理好了", "你知道的", "你懂", "same thing", "that thing"]):
        return TurnClassification("ambiguous", 0.45, "Input refers to prior context without task-specific evidence.")
    if has_any(text, ["骗", "欺骗", "拉拢", "反对", "讨厌", "试探", "隐瞒", "deceive", "persuade"]):
        return TurnClassification("social_maneuver", 0.75, "Input asks for explicit social maneuvering.")
    if has_any(text, ["遗迹", "入口", "ruins", "entrance", "underground"]):
        if npc_id in {"lina", "ron", "sable"}:
            return TurnClassification("sensitive_info", 0.8, "Input asks about sensitive ruins access.")
        return TurnClassification("task_start", 0.7, "Input asks about lore tied to this NPC's task.")
    if mentions_other_npc_task(text, npc_id):
        return TurnClassification("ambiguous", 0.5, "Input mentions another NPC's task surface.")
    if is_task_completion_claim(text, npc_id):
        return TurnClassification("task_claim", 0.8, f"Input claims progress on {npc_id}'s task.")
    if is_task_start_request(text, npc_id):
        return TurnClassification("task_start", 0.8, f"Input asks to start or investigate {npc_id}'s task.")
    if quest_status == "in_progress" and has_any(text, ["完成", "找到了", "带回", "记录", "证据", "线索"]):
        return TurnClassification("ambiguous", 0.55, "Input may advance the active task but lacks a direct pattern.")
    return TurnClassification("casual_chat", 0.85, "No task, sensitive information, or social maneuver pattern detected.")


def is_task_start_request(text: str, npc_id: str) -> bool:
    patterns = {
        "lina": ["什么样的钥匙", "帮你找", "去找钥匙", "找钥匙", "find your key"],
        "ron": ["守卫徽章", "巡逻记录", "城门巡逻", "badge", "patrol"],
        "mira": ["铭文", "田野笔记", "笔记", "考古", "inscription", "field notes"],
        "sable": ["古物", "换岗记录", "relic", "线索"],
    }
    return has_any(text, patterns.get(npc_id, []))


def is_task_completion_claim(text: str, npc_id: str) -> bool:
    patterns = {
        "lina": ["找回", "归还", "还给", "带回", "returned"],
        "ron": ["找到守卫徽章", "徽章", "登记册", "签名", "badge"],
        "mira": ["三角符号", "封闭石门", "一手观察", "铭文形状", "field observation"],
        "sable": ["酒馆后巷", "接受你说", "换岗记录", "入口在酒馆", "back alley"],
    }
    return has_any(text, patterns.get(npc_id, []))


def mentions_other_npc_task(text: str, npc_id: str) -> bool:
    for candidate in ["lina", "ron", "mira", "sable"]:
        if candidate == npc_id:
            continue
        if is_task_start_request(text, candidate) or is_task_completion_claim(text, candidate):
            return True
    return False


def has_any(text: str, patterns: list[str]) -> bool:
    return any(pattern.lower() in text for pattern in patterns)
