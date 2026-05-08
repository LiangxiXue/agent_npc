from __future__ import annotations


CANONICAL_WORLD_FACTS = {
    "lina": {
        "name": "Lina",
        "role": "Tavern Owner",
        "description": "A cautious and practical tavern owner who knows local rumors.",
    },
    "locations": {
        "tavern": "酒馆",
        "town_square": "镇广场",
        "underground_ruins_entrance": "酒馆后巷的地下遗迹隐秘入口",
    },
    "quests": {
        "lost_key": "归还 Lina 丢失的钥匙以获得她的信任",
    },
    "items": {
        "tavern_discount_coupon": "酒馆折扣券",
    },
}


MAJOR_FACT_CONFLICT_TERMS = {
    "underground_ruins_entrance": [
        "枯井",
        "镇子北边的枯井",
        "镇北枯井",
        "北边的枯井",
    ],
}
