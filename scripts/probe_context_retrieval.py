from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.context import build_context_inputs  # noqa: E402
from src.agent.embedding_client import get_embedding_settings  # noqa: E402
from src.storage import database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe the explicit context layers used by an NPC turn."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="我想打听一下地下遗迹的入口。",
        help="Player input to retrieve context for.",
    )
    parser.add_argument("--npc", default="lina", help="NPC id, for example lina, ron, or mira.")
    parser.add_argument(
        "--mode",
        default="hybrid",
        choices=["typed", "hybrid", "semantic", "legacy", "off"],
        help="Long-term memory retrieval mode.",
    )
    args = parser.parse_args()

    database.initialize_database()
    context = build_context_inputs(
        player_input=args.query,
        npc_id=args.npc,
        memory_retrieval_mode=args.mode,
    )
    settings = get_embedding_settings()
    print(f"Embedding provider: {settings['provider']}")
    print(f"Embedding model: {settings['model']}")
    print(f"Embedding configured: {settings['configured']}")
    print(f"Retrieval backend: {settings['retrieval_backend']}")
    print()
    print(f"Query: {args.query}")
    print(f"NPC: {args.npc}")
    print()

    print(f"retrieved_lore: {len(context['retrieved_lore'])}")
    for item in context["retrieved_lore"]:
        fallback = item.get("query_embedding_fallback_reason")
        fallback_text = f" fallback={fallback}" if fallback else ""
        print(
            f"- {item['lore_id']} score={item['retrieval_score']} "
            f"semantic={item['semantic_score']} provider={item.get('query_embedding_provider')}"
            f"{fallback_text}"
        )
        print(f"  title={item['title']}")
        print(f"  excerpt={item['excerpt']}")

    print()
    print(f"retrieved_memories: {len(context['retrieved_memories'])}")
    for item in context["retrieved_memories"]:
        print(
            f"- memory_id={item['id']} type={item.get('memory_type')} "
            f"score={item.get('retrieval_score')} semantic={item.get('semantic_score')}"
        )
        print(f"  content={item['content']}")

    print()
    print("state_snapshot:")
    print(context["state_snapshot"])
    print()
    print(f"recent_context: {len(context['recent_context'])}")


if __name__ == "__main__":
    main()
