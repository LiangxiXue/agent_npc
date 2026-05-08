from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Keep API smoke tests separate from the Streamlit demo database.
os.environ.setdefault("AGENT_NPC_DB_PATH", str(PROJECT_ROOT / "data" / "api_test_agent_state.db"))

from src.agent.llm_client import get_provider_status  # noqa: E402
from src.agent.workflow import run_agent_turn  # noqa: E402
from src.storage import database  # noqa: E402


DEFAULT_INPUT = "我把你之前一直在找的那个小东西带回来了。"


def main() -> None:
    player_input = " ".join(sys.argv[1:]).strip() or DEFAULT_INPUT

    database.reset_database()

    provider_status = get_provider_status()
    print("LLM Provider")
    print(json.dumps(provider_status, ensure_ascii=False, indent=2))
    print()

    run = run_agent_turn(player_input)
    print("Player Input")
    print(player_input)
    print()

    print("NPC Response")
    print(run.npc_response)
    print()

    print("Decision")
    print(json.dumps(run.decision, ensure_ascii=False, indent=2))
    print()

    print("Tool Calls")
    print(json.dumps(run.tool_calls, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
