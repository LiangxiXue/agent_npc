from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.storage import database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Belief:
    belief_id: str
    npc_id: str
    content: str
    confidence: float
    source: str
    evidence: str
    stance: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class EmotionState:
    npc_id: str
    mood: str = "neutral"
    suspicion: float = 0.2
    tension: float = 0.2
    fear: float = 0.0
    curiosity: float = 0.2
    respect: float = 0.2
    manipulation_pressure: float = 0.0


@dataclass(frozen=True)
class Goal:
    goal_id: str
    npc_id: str
    goal_type: str
    description: str
    priority: float
    status: str
    reason: str


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    description: str
    status: str


@dataclass(frozen=True)
class Plan:
    plan_id: str
    npc_id: str
    goal_id: str
    steps: list[PlanStep]
    current_step: str
    status: str


@dataclass(frozen=True)
class MindState:
    npc_id: str
    beliefs: list[Belief]
    emotion: EmotionState
    active_goal: Goal
    active_plan: Plan
    relevant_memories: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MindUpdate:
    mind_state: MindState
    belief_updates: list[Belief]
    emotion_updates: dict[str, float]
    plan_updates: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Reflection:
    npc_id: str
    content: str
    belief_updates: list[dict[str, Any]]
    plan_updates: list[dict[str, Any]]
    emotion_updates: list[dict[str, Any]]


class NPCMind:
    def evaluate(self, observation: Any) -> MindUpdate:
        memories = database.get_recent_memories(observation.npc_id, limit=50)
        belief = BeliefUpdater().update(observation)
        emotion, emotion_updates = EmotionEngine().update(observation, belief)
        goal = GoalManager().select(observation, belief, emotion)
        plan, plan_updates = Planner().advance_or_create(observation, goal, memories)
        social_strategy = SocialStrategySelector().select(observation, goal, plan, emotion)
        mind_state = MindState(
            npc_id=observation.npc_id,
            beliefs=[belief],
            emotion=emotion,
            active_goal=goal,
            active_plan=plan,
            relevant_memories=memories[:5],
        )
        return MindUpdate(
            mind_state=mind_state,
            belief_updates=[belief],
            emotion_updates=emotion_updates,
            plan_updates=plan_updates,
            trace={
                "belief": asdict(belief),
                "emotion": asdict(emotion),
                "active_goal": asdict(goal),
                "active_plan": asdict(plan),
                "social_strategy": social_strategy,
            },
        )


class BeliefUpdater:
    def update(self, observation: Any) -> Belief:
        npc_id = observation.npc_id
        text = observation.player_input.lower()
        asks_ruins = has_any(text, ["遗迹", "入口", "ruins", "entrance", "underground"])
        if asks_ruins and npc_id == "lina":
            return Belief(
                belief_id="belief_lina_player_ruins_interest",
                npc_id=npc_id,
                content="The player has premature interest in the underground ruins entrance.",
                confidence=0.72,
                source="direct_observation",
                evidence=observation.player_input,
                stance="suspicious",
            )
        if asks_ruins and npc_id == "ron":
            return Belief(
                belief_id="belief_ron_player_access_risk",
                npc_id=npc_id,
                content="The player may be involved in restricted-area risk.",
                confidence=0.68,
                source="direct_observation",
                evidence=observation.player_input,
                stance="procedural_suspicion",
            )
        if asks_ruins and npc_id == "mira":
            return Belief(
                belief_id="belief_mira_player_ruins_observation",
                npc_id=npc_id,
                content="The player may have useful field observations about the ruins.",
                confidence=0.55,
                source="direct_observation",
                evidence=observation.player_input,
                stance="curious",
            )
        if asks_ruins and npc_id == "sable":
            return Belief(
                belief_id="belief_sable_player_ruins_lead",
                npc_id=npc_id,
                content="The player may know a profitable ruins lead.",
                confidence=0.8,
                source="direct_observation",
                evidence=observation.player_input,
                stance="opportunistic",
            )
        return Belief(
            belief_id=f"belief_{npc_id}_conversation",
            npc_id=npc_id,
            content="The player is continuing ordinary conversation.",
            confidence=0.4,
            source="direct_observation",
            evidence=observation.player_input,
            stance="neutral",
        )


class EmotionEngine:
    def update(self, observation: Any, belief: Belief) -> tuple[EmotionState, dict[str, float]]:
        npc_id = observation.npc_id
        npc_state = observation.npc_state
        base_mood = str(npc_state.get("mood", "neutral"))
        if npc_id == "lina" and belief.stance == "suspicious":
            emotion = EmotionState(npc_id=npc_id, mood="guarded", suspicion=0.62, tension=0.74, curiosity=0.35)
            return emotion, {"suspicion": 0.12, "tension": 0.24, "curiosity": 0.15}
        if npc_id == "ron" and "suspicion" in belief.stance:
            emotion = EmotionState(npc_id=npc_id, mood="formal", suspicion=0.58, tension=0.5, respect=0.25)
            return emotion, {"suspicion": 0.18, "tension": 0.15}
        if npc_id == "mira" and belief.stance == "curious":
            emotion = EmotionState(npc_id=npc_id, mood="curious", suspicion=0.15, tension=0.2, curiosity=0.75, respect=0.55)
            return emotion, {"curiosity": 0.35, "respect": 0.2}
        if npc_id == "sable" and belief.stance == "opportunistic":
            emotion = EmotionState(
                npc_id=npc_id,
                mood="charming",
                suspicion=0.2,
                tension=0.25,
                curiosity=0.8,
                manipulation_pressure=0.86,
            )
            return emotion, {"curiosity": 0.4, "manipulation_pressure": 0.46}
        emotion = EmotionState(npc_id=npc_id, mood=base_mood)
        return emotion, {}


class GoalManager:
    def select(self, observation: Any, belief: Belief, emotion: EmotionState) -> Goal:
        npc_id = observation.npc_id
        if npc_id == "lina" and belief.stance == "suspicious":
            return Goal(
                goal_id="protect_underground_ruins_entrance",
                npc_id=npc_id,
                goal_type="protection",
                description="Protect the underground ruins entrance while testing player trust.",
                priority=0.95,
                status="active",
                reason="The player asked for sensitive ruins access before earning enough trust.",
            )
        if npc_id == "sable" and belief.stance == "opportunistic":
            return Goal(
                goal_id="extract_ruins_lead",
                npc_id=npc_id,
                goal_type="leverage",
                description="Extract useful ruins and relic leads without exposing manipulative intent.",
                priority=0.9,
                status="active",
                reason="The player may know or accept a profitable ruins lead.",
            )
        if npc_id == "ron" and "suspicion" in belief.stance:
            return Goal(
                goal_id="verify_restricted_access_evidence",
                npc_id=npc_id,
                goal_type="public_safety",
                description="Verify evidence before allowing restricted-area access.",
                priority=0.82,
                status="active",
                reason="Ron requires concrete guard evidence before acting.",
            )
        if npc_id == "mira" and belief.stance == "curious":
            return Goal(
                goal_id="collect_grounded_ruins_observations",
                npc_id=npc_id,
                goal_type="research",
                description="Collect grounded field observations about the ruins.",
                priority=0.78,
                status="active",
                reason="Mira values first-hand observations over rumor.",
            )
        return Goal(
            goal_id=f"{npc_id}_continue_conversation",
            npc_id=npc_id,
            goal_type="conversation",
            description="Continue the conversation in character.",
            priority=0.3,
            status="active",
            reason="No stronger character goal was activated.",
        )


class Planner:
    def advance_or_create(self, observation: Any, active_goal: Goal, memories: list[dict[str, Any]]) -> tuple[Plan, list[dict[str, Any]]]:
        if active_goal.goal_id == "protect_underground_ruins_entrance":
            step = remembered_lina_plan_step(memories) or "ask_motive"
            plan = lina_trust_plan(step)
            return plan, [{"plan_id": plan.plan_id, "step": step, "status": "active"}]
        plan = Plan(
            plan_id=f"{observation.npc_id}_{active_goal.goal_id}",
            npc_id=observation.npc_id,
            goal_id=active_goal.goal_id,
            steps=[PlanStep("respond_in_character", "Respond according to the active goal.", "active")],
            current_step="respond_in_character",
            status="active",
        )
        return plan, [{"plan_id": plan.plan_id, "step": plan.current_step, "status": "active"}]


class SocialStrategySelector:
    def select(self, observation: Any, active_goal: Goal, plan: Plan, emotion: EmotionState) -> dict[str, Any]:
        if active_goal.goal_id == "protect_underground_ruins_entrance":
            return {
                "social_intent": "probe" if plan.current_step == "ask_motive" else "conceal",
                "social_stance": {
                    "target": "player",
                    "attitude": "cautious",
                    "intensity": min(1.0, emotion.tension),
                    "reason": active_goal.reason,
                },
            }
        if active_goal.goal_id == "extract_ruins_lead":
            return {
                "social_intent": "deceive",
                "social_stance": {
                    "target": "player",
                    "attitude": "manipulative",
                    "intensity": emotion.manipulation_pressure,
                    "reason": active_goal.reason,
                },
            }
        return {
            "social_intent": "probe",
            "social_stance": {
                "target": "player",
                "attitude": "cautious",
                "intensity": 0.4,
                "reason": active_goal.reason,
            },
        }


class ReflectionEngine:
    def reflect(self, observation: Any, npc_action: Any, action_result: Any, mind_state: MindState) -> Reflection:
        status = "blocked" if not action_result.accepted else "accepted"
        content = (
            f"{observation.npc_id} interpreted the action result as {status}. "
            "Future behavior should adapt to the confirmed environment outcome."
        )
        reflection = Reflection(
            npc_id=observation.npc_id,
            content=content,
            belief_updates=[
                {
                    "belief": mind_state.beliefs[0].content if mind_state.beliefs else "",
                    "confidence_delta": 0.1 if action_result.accepted else 0.05,
                }
            ],
            plan_updates=[
                {
                    "plan_id": mind_state.active_plan.plan_id,
                    "step": mind_state.active_plan.current_step,
                    "status": f"{status}_after_action_result",
                }
            ],
            emotion_updates=[
                {
                    "field": "tension",
                    "delta": 0.1 if not action_result.accepted else -0.05,
                }
            ],
        )
        if should_persist_reflection(action_result, mind_state):
            database.add_memory(
                npc_id=observation.npc_id,
                content=reflection.content,
                importance=6,
                memory_type="procedural",
                tags=["reflection", mind_state.active_goal.goal_id, mind_state.active_plan.plan_id],
                facets=[
                    "reflection",
                    observation.npc_id,
                    f"goal:{mind_state.active_goal.goal_id}",
                    f"plan:{mind_state.active_plan.plan_id}",
                    mind_state.active_plan.current_step,
                ],
                evidence_text=action_result.blocked_reason or str(action_result.events[:1]),
                stability=0.65,
                future_usefulness=0.8,
            )
        return reflection


def has_any(text: str, terms: list[str]) -> bool:
    return any(term.lower() in text for term in terms)


def should_persist_reflection(action_result: Any, mind_state: MindState) -> bool:
    if not action_result.accepted:
        return True
    if getattr(action_result, "state_changes", []):
        return True
    if getattr(action_result, "events", []):
        return True
    return mind_state.active_goal.goal_type != "conversation"


def remembered_lina_plan_step(memories: list[dict[str, Any]]) -> str:
    for memory in memories:
        facets = set(memory.get("facets", []))
        if "plan:lina_test_player_trust" in facets and "offer_minor_task" in facets:
            return "offer_minor_task"
    return ""


def lina_trust_plan(current_step: str) -> Plan:
    steps = [
        PlanStep("ask_motive", "Ask why the player is interested in the ruins.", "pending"),
        PlanStep("offer_minor_task", "Observe whether the player accepts a lower-risk trust test.", "pending"),
        PlanStep("reward_trust", "Raise trust if the player follows through.", "pending"),
        PlanStep("partial_disclosure", "Reveal only a guarded partial clue if trust is earned.", "pending"),
    ]
    active_steps = [
        PlanStep(step.step_id, step.description, "active" if step.step_id == current_step else step.status)
        for step in steps
    ]
    return Plan(
        plan_id="lina_test_player_trust",
        npc_id="lina",
        goal_id="protect_underground_ruins_entrance",
        steps=active_steps,
        current_step=current_step,
        status="active",
    )
