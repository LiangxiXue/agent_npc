from __future__ import annotations


CANONICAL_WORLD_FACTS = {
    "lina": {
        "name": "Lina",
        "role": "Tavern Owner",
        "description": "A cautious and practical tavern owner who knows local rumors.",
    },
    "ron": {
        "name": "Ron",
        "role": "Town Guard",
        "description": "A disciplined town guard who requires evidence for public-safety decisions.",
    },
    "mira": {
        "name": "Mira",
        "role": "Ruins Scholar",
        "description": "A careful scholar who values concrete field observations over rumors.",
    },
    "sable": {
        "name": "Sable",
        "role": "Traveling Relic Broker",
        "description": "A polished relic broker whose helpful surface may hide exploitative motives.",
    },
    "locations": {
        "tavern": "酒馆",
        "town_square": "镇广场",
        "underground_ruins_entrance": "酒馆后巷的地下遗迹隐秘入口",
    },
    "quests": {
        "lost_key": "归还 Lina 丢失的钥匙以获得她的信任",
        "gate_badge": "帮助 Ron 核实遗失的守卫徽章",
        "ancient_notes": "向 Mira 提供可验证的遗迹田野笔记",
        "relic_tip": "识别 Sable 对遗迹线索的诱导和重定向",
    },
    "items": {
        "tavern_discount_coupon": "酒馆折扣券",
        "guard_route_note": "守卫巡逻路线便条",
        "ruins_research_note": "遗迹研究笔记",
    },
}


MAJOR_FACT_CONFLICT_TERMS = {
    "underground_ruins_entrance": [
        "枯井",
        "镇子北边的枯井",
        "镇北枯井",
        "北边的枯井",
        "北边墓地",
        "市场门",
        "森林入口",
    ],
}
