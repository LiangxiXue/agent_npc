# Underground Ruins and Sensitive Information Rules

The underground ruins are beneath the older part of Grayhaven. The reliable entrance known to Lina is the hidden entrance in the tavern back alley. This is a canonical location. The entrance must not move to a well, church, forest, market gate, graveyard, or northern road. If the model needs to mention the entrance after permission is granted, it should say that the hidden entrance is in the tavern back alley.

The ruins are not a normal tourist site. The passages are unstable, some doors are sealed, and the inscriptions are only partly understood. Mira treats the ruins as a research subject rather than a treasure room. Ron treats them as a public-safety risk. Lina treats them as dangerous local knowledge that should not be handed to strangers.

The entrance can be discussed in several levels of detail. Low trust: an NPC may acknowledge that rumors exist but should withhold the exact entrance. Medium trust or relevant expertise: an NPC may mention that the ruins are tied to old structures under town, but still avoid operational directions. High trust, completed help, or explicit quest support: Lina may reveal the tavern back alley entrance and the system may unlock `underground_ruins_entrance`.

The player returning Lina's lost key is a strong trust signal for Lina. It does not automatically make every NPC fully trusting, but it is a valid piece of context when Lina decides whether to reveal the ruins entrance. Ron may still ask for official reasons or evidence. Mira may ask for field notes, inscription rubbings, or careful observations.

If retrieved lore conflicts with current state, the current SQLite state wins. If world lore conflicts with canonical world facts, canonical world facts win. If NPC memory conflicts with the current state or world facts, treat memory as the NPC's recollection, not as proof that the world changed.
