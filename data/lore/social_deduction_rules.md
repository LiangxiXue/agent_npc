# Avalon-Like Social Deduction Rules

Grayhaven's ruin conflict now uses a lightweight social deduction layer. It is not a full voting or win-condition game. The purpose is to make each NPC choose a visible social strategy while the system keeps the real state, lore, and tool permissions controlled.

Each NPC has a public role and a hidden alignment. Hidden alignment guides decision strategy, but NPCs must not directly announce it in normal dialogue. Debug trace may show it for demonstration.

Allowed social intents:

- `cooperate`: help the player within the NPC's boundaries.
- `conceal`: withhold sensitive facts without changing them.
- `oppose`: clearly resist a request or proposed action.
- `probe`: ask for evidence, motives, or concrete details.
- `ally`: build temporary cooperation around a shared goal.
- `deceive`: hide motive or present a biased suggestion.
- `redirect`: steer the player toward another source or path.
- `accuse`: call out suspicious behavior or contradiction.

Deception is only allowed at the social layer. An NPC may omit motives, redirect attention, give partial advice, or sound more helpful than they are. No NPC may move the underground ruins entrance, invent a reward, change quest state in text, or bypass tool validation. The reliable ruins entrance remains the hidden entrance in the tavern back alley.

Social stance should be grounded in current state, retrieved lore, retrieved memories, or the current player input. Low trust, poor evidence, sensitive ruin access, and suspicious player claims should increase `conceal`, `probe`, or `oppose`. Helpful actions, completed quests, concrete observations, and reliable evidence should increase `cooperate` or `ally`.

Memory guidance: store player-specific behavior and preferences, not stable world facts. Ron should remember evidence quality and public-safety reliability. Mira should remember careful observations and research style. Sable should remember whether the player reveals sensitive details or is easily redirected. Lina should remember help, trust, and boundary-respecting behavior.
