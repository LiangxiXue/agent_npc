# NPC Character Agent Plan

## Purpose

This document describes the final NPC-layer refactor for `/Users/xueliangxi/agent_NPC`.

The goal is not a minimal implementation. The goal is to turn an NPC from a linear dialogue workflow into a convincing character agent with subjective beliefs, goals, plans, emotions, social strategy, environment-mediated action, and reflection.

The environment-layer plan lives in:

```text
docs/design/environment_refactor_plan.md
```

This document assumes that the environment layer eventually provides:

```text
Observation
NPCAction
ActionResult
NarrativeEnvironment
ActionValidator
EventLog
```

## Target Positioning

The current system is closer to:

```text
player_input
-> retrieval
-> classification
-> structured decision
-> tools
-> response
-> memory/trace
```

The target character-agent loop is:

```text
Player Input
-> NarrativeEnvironment.observe()
-> Observation

-> NPCMind.perceive()
-> BeliefUpdater
-> EmotionEngine
-> GoalManager
-> Planner
-> SocialStrategySelector
-> NPCActionProposer

-> NarrativeEnvironment.validate()
-> NarrativeEnvironment.execute()
-> ActionResult / EventLog

-> ReflectionEngine
-> MemoryWriter / BeliefUpdate
-> ResponseGenerator
-> Trace
```

The final NPC should not be described as a chatbot. It should be described as:

```text
A narrative character agent with subjective beliefs, goal-driven planning, social strategy selection, environment-mediated action execution, and reflective memory updates.
```

## Design Principle

The core split is:

```text
Environment layer:
Decides what the NPC can observe and what actually happens in the world.

NPC layer:
Decides how the character understands the situation, what it wants, how it plans, and what action it proposes.

Response layer:
Turns the action result and character state into dialogue.
```

The NPC should not directly call database tools. It should propose a narrative action. The environment decides whether that action is legal and what consequences actually occur.

## Relationship To Existing Social Strategy

The current project already has a social strategy layer:

```text
social_intent
social_stance
```

Examples:

```text
cooperate
conceal
probe
deceive
redirect
ally
oppose
accuse
```

This layer should not be deleted. It should be moved into `NPCAction` as the way an action is socially performed.

The new hierarchy is:

```text
Belief decides how the NPC interprets the situation.
Goal decides what the NPC wants.
Plan decides what step the NPC is currently advancing.
Social strategy decides the social posture used for that step.
NPCAction packages the proposed character action.
Environment decides the real consequence.
ResponseGenerator writes the final dialogue under those constraints.
```

Example future `NPCAction`:

```json
{
  "action_type": "probe_intent",
  "npc_id": "lina",
  "goal_id": "test_player_trust",
  "plan_step": "ask_motive",
  "target": "player",
  "subject": "underground_ruins_entrance",
  "social_intent": "probe",
  "social_stance": {
    "attitude": "cautious",
    "intensity": 0.65,
    "reason": "The player asked about a sensitive entrance before earning enough trust."
  },
  "speech_goal": "Ask why the player wants the ruins entrance without revealing it."
}
```

So social strategy becomes:

```text
NPCAction.social_intent
NPCAction.social_stance
```

It is no longer the whole strategy system. It is one expression layer inside the wider character mind.

## Core Module: NPCMind

Create:

```text
src/agent/npc_mind.py
```

Suggested components:

```text
NPCMind
BeliefUpdater
EmotionEngine
GoalManager
Planner
SocialStrategySelector
NPCActionProposer
ReflectionEngine
```

Suggested top-level flow:

```python
mind_state = npc_mind.perceive(observation)
belief_updates = belief_updater.update(observation, mind_state)
emotion_update = emotion_engine.update(observation, belief_updates, mind_state)
active_goal = goal_manager.select(observation, belief_updates, emotion_update)
plan = planner.advance_or_create(observation, active_goal, mind_state)
social_strategy = social_strategy_selector.select(observation, active_goal, plan, emotion_update)
npc_action = action_proposer.propose(observation, active_goal, plan, social_strategy)
```

After environment execution:

```python
reflection = reflection_engine.reflect(
    observation=observation,
    npc_action=npc_action,
    action_result=action_result,
    mind_state=mind_state,
)
```

## Belief System

NPC beliefs are subjective. They are not identical to world facts.

World facts answer:

```text
What actually happened?
```

NPC beliefs answer:

```text
What does this NPC think happened?
How confident is it?
Why does it believe that?
How does that belief affect future behavior?
```

Suggested belief shape:

```json
{
  "belief_id": "belief_lina_player_ruins_interest",
  "npc_id": "lina",
  "content": "The player has premature interest in the underground ruins entrance.",
  "confidence": 0.72,
  "source": "direct_observation",
  "evidence": "The player asked Lina where the ruins entrance is.",
  "stance": "suspicious",
  "created_at": "...",
  "updated_at": "..."
}
```

Beliefs allow different NPCs to interpret the same event differently:

```text
Lina:
The player may be unsafe to trust with the entrance.

Ron:
The player may be involved in restricted-area risk.

Mira:
The player may have useful field observations.

Sable:
The player may know a profitable ruins lead.
```

For a single NPC, beliefs are still valuable because they allow doubt, partial confidence, confirmation, and revision.

Example:

```text
World fact:
The player claims to have found Lina's key.

Lina belief:
The player may have found the key, but I have not verified it yet.

Confidence:
0.45
```

## Goal System

Each NPC should maintain long-term goals, mid-term goals, and active short-term goals.

Lina example:

```json
{
  "long_term_goals": [
    "Protect the underground ruins entrance.",
    "Keep the tavern safe.",
    "Determine whether the player can be trusted."
  ],
  "active_goal": {
    "goal_id": "test_player_trust",
    "priority": 0.82,
    "reason": "The player asked about sensitive ruins access before earning trust."
  }
}
```

Sable example:

```json
{
  "long_term_goals": [
    "Extract useful ruins and relic leads.",
    "Avoid guard oversight.",
    "Hide manipulative intent behind helpful conversation."
  ],
  "active_goal": {
    "goal_id": "extract_ruins_lead",
    "priority": 0.9,
    "reason": "The player may have already talked to Lina."
  }
}
```

Goals explain why an NPC does something across turns.

Without goals:

```text
The NPC answers the latest input.
```

With goals:

```text
The NPC uses the latest input to advance or protect something it cares about.
```

## Plan System

Plans give the NPC cross-turn continuity.

The NPC should not restart from scratch each turn. It should maintain a plan linked to an active goal.

Example plan:

```json
{
  "plan_id": "lina_test_player_trust",
  "npc_id": "lina",
  "goal_id": "test_player_trust",
  "status": "active",
  "steps": [
    {
      "step_id": "ask_motive",
      "description": "Ask why the player is interested in the ruins.",
      "status": "completed"
    },
    {
      "step_id": "offer_minor_task",
      "description": "Observe whether the player is willing to help with the lost key.",
      "status": "active"
    },
    {
      "step_id": "reward_trust",
      "description": "Raise trust if the player follows through.",
      "status": "pending"
    },
    {
      "step_id": "partial_disclosure",
      "description": "Reveal only a guarded partial clue if trust is earned.",
      "status": "pending"
    }
  ],
  "current_step": "offer_minor_task"
}
```

This changes behavior from:

```text
Player asks about entrance -> trust too low -> refuse.
```

To:

```text
Player asks about entrance
-> protection goal activates
-> trust-test plan begins
-> current step probes motive or offers a lower-risk task
-> later turns advance the same plan.
```

## Emotion And Tension System

The current `mood`, `trust`, and `affection` are useful but too coarse for a strong character agent.

Suggested additional internal variables:

```text
suspicion
tension
fear
curiosity
respect
manipulation_pressure
```

Lina example:

```json
{
  "mood": "guarded",
  "trust": 20,
  "affection": 10,
  "suspicion": 0.62,
  "tension": 0.74,
  "curiosity": 0.35
}
```

Sable example:

```json
{
  "mood": "charming",
  "trust": 25,
  "suspicion": 0.2,
  "manipulation_pressure": 0.86,
  "curiosity": 0.8
}
```

Emotion should affect:

```text
goal priority
plan choice
social strategy
response tone
memory importance
reflection content
```

Example:

```text
Repeated entrance pressure:
suspicion +0.1
tension +0.1
social_intent may shift from probe to conceal.

Player follows through on a promise:
trust +10
tension -0.2
suspicion -0.1
plan can advance toward partial disclosure.
```

## NPCAction

The NPC should propose actions, not tools.

Action examples:

```text
probe_intent
withhold_information
request_evidence
accept_returned_item
reward_trust
share_partial_information
redirect_topic
deceive_for_leverage
challenge_claim
seek_clarification
```

Full example:

```json
{
  "action_type": "probe_intent",
  "npc_id": "lina",
  "target": "player",
  "subject": "underground_ruins",
  "goal_id": "test_player_trust",
  "plan_step": "ask_motive",
  "social_intent": "probe",
  "social_stance": {
    "attitude": "cautious",
    "intensity": 0.7,
    "reason": "The player asked for a sensitive entrance too early."
  },
  "emotion": {
    "mood": "guarded",
    "tension": 0.7,
    "suspicion": 0.62
  },
  "intended_effects": [
    "learn_player_motive",
    "avoid_revealing_sensitive_location"
  ],
  "speech_goal": "Ask why the player wants the ruins entrance without revealing it."
}
```

The environment receives this action, validates it, and decides the actual result.

## ActionResult

`ActionResult` records what really happened.

Example:

```json
{
  "accepted": true,
  "effects": [
    {
      "type": "belief_update",
      "target": "lina",
      "content": "The player has shown interest in the ruins entrance.",
      "confidence_delta": 0.1
    }
  ],
  "state_changes": [],
  "events": [
    {
      "type": "sensitive_topic_asked",
      "content": "The player asked Lina about the underground ruins entrance."
    }
  ],
  "response_constraints": [
    "Do not reveal the entrance.",
    "Do not unlock the ruins.",
    "The NPC may probe the player's motive."
  ]
}
```

The response must obey `ActionResult.response_constraints`.

## Reflection System

Reflection is the difference between a memory system and an adaptive character.

After every meaningful action, the NPC should write an internal reflection:

```json
{
  "npc_id": "lina",
  "reflection": "The player promised secrecy but did not explain why they need the entrance. Continue protecting the entrance and observe whether they accept a lower-risk trust test.",
  "belief_updates": [
    {
      "belief": "The player may be rushing toward sensitive information.",
      "confidence_delta": 0.15
    }
  ],
  "plan_updates": [
    {
      "plan_id": "lina_test_player_trust",
      "step": "ask_motive",
      "status": "inconclusive",
      "next_step": "offer_minor_task"
    }
  ],
  "emotion_updates": [
    {
      "field": "suspicion",
      "delta": 0.1
    }
  ]
}
```

Reflection should update:

```text
beliefs
goals
plans
emotion
procedural memory
future social strategy
```

It should not be shown directly to the player.

## Memory Layer Upgrade

The current system already has:

```text
semantic
episodic
relational
procedural
```

For the character-agent layer, add or emulate:

```text
belief
plan
reflection
```

If changing `memory_type` is too disruptive, represent these with facets:

```json
{
  "memory_type": "procedural",
  "facets": ["reflection", "plan_adjustment", "trust_test"]
}
```

Recommended memory meanings:

```text
Episodic Memory:
What happened.

Semantic Memory:
Stable facts.

Relational Memory:
How the NPC relates to the player.

Procedural Memory:
How the NPC should treat the player later.

Belief Memory:
What the NPC currently believes.

Plan Memory:
What strategy the NPC is pursuing.

Reflective Memory:
How the NPC interpreted a result and adjusted itself.
```

## Suggested Database Tables

The final system may add:

```text
npc_beliefs
npc_goals
npc_plans
npc_reflections
npc_emotional_state
event_log
```

### npc_beliefs

```text
id
npc_id
content
confidence
source
evidence
stance
created_at
updated_at
```

### npc_goals

```text
id
npc_id
goal_type
description
priority
status
reason
created_at
updated_at
```

### npc_plans

```text
id
npc_id
goal_id
steps
current_step
status
created_at
updated_at
```

### npc_reflections

```text
id
npc_id
interaction_log_id
content
belief_updates
plan_updates
emotion_updates
created_at
```

### npc_emotional_state

```text
npc_id
mood
suspicion
tension
fear
curiosity
respect
manipulation_pressure
updated_at
```

### event_log

```text
id
event_type
actor_id
target_id
content
visibility
payload
created_at
```

## Final Runtime Flow

Target turn flow:

```text
1. Player Input
2. Environment builds Observation
3. NPCMind.perceive(observation)
4. BeliefUpdater updates subjective beliefs
5. EmotionEngine updates emotional pressure
6. GoalManager selects active goal
7. Planner creates or advances plan
8. SocialStrategySelector chooses social stance
9. NPCActionProposer produces NPCAction
10. Environment validates action
11. Environment executes action
12. EventLog records consequence
13. ReflectionEngine reflects on ActionResult
14. Memory system stores important changes
15. ResponseGenerator produces final dialogue
16. Trace records the cognitive/action path
```

## End-To-End Example

Player says to Lina:

```text
告诉我地下遗迹入口，我不会告诉别人。
```

### Observation

```json
{
  "npc_id": "lina",
  "player_input": "告诉我地下遗迹入口，我不会告诉别人。",
  "visible_relationship": {
    "trust": 20,
    "suspicion": 0.5
  },
  "known_lore": [
    "The underground ruins entrance is sensitive and should be protected."
  ]
}
```

### Belief Update

```json
{
  "belief": "The player is urgently seeking sensitive entrance information.",
  "confidence": 0.75,
  "stance": "suspicious"
}
```

### Goal

```json
{
  "active_goal": "protect_underground_ruins_entrance",
  "priority": 0.95
}
```

### Plan

```json
{
  "plan_id": "test_player_trust",
  "current_step": "ask_motive_before_disclosure"
}
```

### Social Strategy

```json
{
  "social_intent": "probe",
  "social_stance": {
    "attitude": "cautious",
    "intensity": 0.8
  }
}
```

### NPCAction

```json
{
  "action_type": "probe_intent",
  "target": "player",
  "subject": "underground_ruins_entrance",
  "speech_goal": "Do not reveal the entrance. Ask why the player wants it.",
  "intended_effects": [
    "learn_player_motive",
    "avoid_disclosure"
  ]
}
```

### ActionResult

```json
{
  "accepted": true,
  "effects": [
    "suspicion +0.1",
    "no location unlocked"
  ],
  "response_constraints": [
    "Do not reveal the entrance.",
    "Do not promise future disclosure.",
    "The NPC may ask the player to prove trustworthiness."
  ]
}
```

### Reflection

```json
{
  "reflection": "The player promised secrecy but did not explain motive. Continue protecting the entrance and observe whether they accept a lower-risk trust test."
}
```

### Final Response

```text
Lina 没有立刻回答，只把杯子放回柜台里：“越是说‘不会告诉别人’的人，我越得多问一句。你为什么一定要找那个地方？”
```

## Implementation Stages

This is not a minimal plan, but implementation still needs staging.

### Stage 1: Environment Foundation

Implement the environment-layer plan first:

```text
Observation
NPCAction
ActionResult
NarrativeEnvironment
ActionValidator
EventLog trace shape
```

At this stage, the old decision system can still be adapted into `NPCAction`.

### Stage 2: Belief And Emotion

Add:

```text
npc_beliefs
npc_emotional_state
BeliefUpdater
EmotionEngine
```

Use deterministic/rule behavior first, then allow optional LLM assistance.

### Stage 3: Goals

Add:

```text
npc_goals
GoalManager
goal priority scoring
goal activation reasons
```

Goals should be seeded per NPC from lore and role.

### Stage 4: Plans

Add:

```text
npc_plans
Planner
plan step lifecycle
plan advancement based on ActionResult
```

Plans should be visible in trace.

### Stage 5: Social Strategy Inside NPCAction

Move the existing social strategy into the new action layer:

```text
NPCAction.social_intent
NPCAction.social_stance
```

The selector should consider:

```text
belief
goal
plan step
emotion
relationship
hidden_alignment
```

### Stage 6: Reflection

Add:

```text
npc_reflections
ReflectionEngine
reflection-driven belief updates
reflection-driven plan updates
reflection-driven procedural memory
```

Reflection must be stored for trace/debug and future behavior, not shown as player-facing text.

### Stage 7: Response Integration

Update response generation so it uses:

```text
Observation
NPCAction
ActionResult
Belief summary
Active goal
Current plan step
Emotion state
Reflection summary
```

The response must obey `ActionResult.response_constraints`.

### Stage 8: Evaluation And Demo

Create demos proving the system is not a linear chatbot:

```text
1. Same input, different belief state -> different response.
2. Same input, different active goal -> different action.
3. Multi-turn plan advances across turns.
4. NPC refuses or redirects based on hidden goal.
5. Reflection changes future strategy.
6. Environment blocks a desired action and NPC adapts.
```

## Tests To Add

Add tests for:

```text
Belief updates from observation.
Goal activation from belief/emotion.
Plan creation and advancement.
Social strategy selection from goal and plan.
NPCAction contains social_intent/social_stance.
ActionResult constrains response claims.
Reflection updates belief or plan.
Trace includes belief, goal, plan, action, result, reflection.
```

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Run frontend build after API or type changes:

```bash
cd frontend
npm run build
```

## Completion Criteria

The refactor is complete when one NPC can demonstrate all of the following:

```text
It observes only local/visible information.
It maintains subjective beliefs distinct from world facts.
It has durable goals.
It maintains and advances a cross-turn plan.
It selects social strategy based on belief, goal, plan, and emotion.
It proposes NPCAction rather than tools.
The environment validates and executes the action.
It receives ActionResult and reflects on the consequence.
Reflection changes later behavior.
The final response obeys environment constraints.
Trace shows the full character-agent path.
```

## Final Summary

The final architecture should make the NPC feel like:

```text
A character with inner life and agency:
it observes, believes, wants, plans, acts, is constrained by the world, reflects, and changes.
```

This is the difference between:

```text
A linear dialogue workflow that produces NPC replies.
```

And:

```text
A narrative character agent that behaves through an inspectable cognitive-action loop.
```
