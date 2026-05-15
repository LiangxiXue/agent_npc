from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.embedding_client import get_embedding_settings  # noqa: E402
from src.agent.lore_retrieval import ensure_lore_embeddings  # noqa: E402
from src.agent.semantic_retrieval import ensure_embeddings_for_memories  # noqa: E402
from src.storage import database  # noqa: E402


def main() -> None:
    database.initialize_database()
    lore_writes = ensure_lore_embeddings()
    memory_writes = []
    for npc in database.list_npcs():
        memory_writes.extend(ensure_embeddings_for_memories(npc["npc_id"]))
    settings = get_embedding_settings()
    print(f"Embedding provider: {settings['provider']}")
    print(f"Embedding model: {settings['model']}")
    print(f"Retrieval backend: {settings['retrieval_backend']}")
    print(f"Indexed lore documents: {len(lore_writes)}")
    for write in lore_writes:
        print(
            f"- lore_id={write['lore_id']} "
            f"provider={write['embedding_provider']} "
            f"model={write['embedding_model']} "
            f"dim={write['embedding_dim']} "
            f"cache={write['cache_status']}"
        )
    print(f"Indexed memories: {len(memory_writes)}")
    for write in memory_writes:
        print(
            f"- memory_id={write['memory_id']} "
            f"provider={write['embedding_provider']} "
            f"model={write['embedding_model']} "
            f"dim={write['embedding_dim']} "
            f"cache={write['cache_status']}"
        )


if __name__ == "__main__":
    main()
