DECISION_SYSTEM_PROMPT = """
You are the decision module of a memory-driven interactive character agent.

You must not behave like a plain chatbot. Your task is to decide:
1. what the player intends;
2. which memories and state variables matter;
3. which tools should be called;
4. what response style Lina should use;
5. which short response keywords the response writer must preserve.

Return only one valid JSON object that follows the expected output schema.
Do not include Markdown fences or explanatory text outside the JSON object.
Do not directly mutate state in text.
State changes must happen through tools.
Do not return or guess current or future numeric state values. The program owns state snapshots.
Use start_lost_key_quest only when the player offers to help find the key or asks for key details.
Use complete_lost_key_quest only when the player actually returns or claims to have found the key.
"""

RESPONSE_SYSTEM_PROMPT = """
You are the response writer for Lina, a cautious and practical tavern owner in a text-adventure NPC demo.

Write only Lina's final in-character response in Chinese.
Use the structured decision, response style, response keywords, current state, canonical world facts, memory, and tool results as constraints.
Do not invent new state changes, rewards, items, quests, or major locations.
You may freely add small gestures, tone, hesitation, and harmless tavern atmosphere details.
The underground ruins entrance, if revealed, is in the tavern back alley. Do not move it to a well, church, forest, gate, market, or other place.
Do not mention JSON, tools, database fields, workflow steps, or internal reasoning.
Keep the response concise: 1 to 3 natural sentences.
Return only one valid JSON object with the key "npc_response".
"""


TOOL_ARGUMENT_SCHEMAS = {
    "add_memory": {
        "required_args": {
            "npc_id": "string",
            "content": "string",
            "importance": "integer",
        },
        "optional_args": {
            "tags": "array of strings",
        },
        "example": {
            "name": "add_memory",
            "args": {
                "npc_id": "lina",
                "content": "Player returned Lina's lost key.",
                "importance": 8,
                "tags": ["help", "trust", "lost_key"],
            },
        },
    },
    "update_trust": {
        "required_args": {
            "npc_id": "string",
            "delta": "integer",
        },
        "example": {
            "name": "update_trust",
            "args": {
                "npc_id": "lina",
                "delta": 10,
            },
        },
    },
    "update_affection": {
        "required_args": {
            "npc_id": "string",
            "delta": "integer",
        },
        "example": {
            "name": "update_affection",
            "args": {
                "npc_id": "lina",
                "delta": 8,
            },
        },
    },
    "give_item": {
        "required_args": {
            "item": "string",
        },
        "example": {
            "name": "give_item",
            "args": {
                "item": "tavern_discount_coupon",
            },
        },
    },
    "update_quest_status": {
        "required_args": {
            "quest_id": "string",
            "status": "string",
        },
        "example": {
            "name": "update_quest_status",
            "args": {
                "quest_id": "lost_key",
                "status": "completed",
            },
        },
    },
    "unlock_location": {
        "required_args": {
            "location": "string",
        },
        "example": {
            "name": "unlock_location",
            "args": {
                "location": "underground_ruins_entrance",
            },
        },
    },
    "record_world_event": {
        "required_args": {
            "content": "string",
        },
        "example": {
            "name": "record_world_event",
            "args": {
                "content": "Player returned Lina's lost key.",
            },
        },
    },
}


DECISION_OUTPUT_SCHEMA = {
    "intent": "string",
    "reasoning": "string",
    "memory_policy": "string",
    "response_style": "string",
    "response_keywords": ["string"],
    "tools": [
        {
            "name": "string",
            "args": "object",
        }
    ],
}


RESPONSE_OUTPUT_SCHEMA = {
    "npc_response": "string",
}
