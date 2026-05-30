import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import display_translation


class DisplayTranslationTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["AGENT_NPC_SKIP_ENV_FILE"] = "1"
        os.environ.pop("AGENT_NPC_LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"

    def test_translation_is_disabled_without_openai_compatible_llm(self) -> None:
        result = display_translation.translate_debug_text(
            "Player returned Lina's lost key.",
            source="memory:test",
        )

        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["reason"], "openai_compatible_llm_not_configured")

    def test_chinese_text_is_skipped(self) -> None:
        result = display_translation.translate_debug_text(
            "玩家说自己感到孤独。",
            source="memory:test",
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "not_english")
        self.assertEqual(result["translated_text"], "玩家说自己感到孤独。")

    def test_translation_uses_existing_llm_and_cache(self) -> None:
        os.environ["AGENT_NPC_LLM_PROVIDER"] = "openai_compatible"
        os.environ["AGENT_NPC_LLM_API_KEY"] = "test-key"
        os.environ["AGENT_NPC_LLM_MODEL"] = "test-model"

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "translation_cache.json"
            with patch.object(display_translation, "TRANSLATION_CACHE_PATH", cache_path), patch(
                "src.agent.display_translation.call_openai_compatible_json",
                return_value={"translation_zh": "玩家归还了 Lina 丢失的钥匙。"},
            ) as call:
                first = display_translation.translate_debug_text(
                    "Player returned Lina's lost key.",
                    source="memory:test",
                )
                second = display_translation.translate_debug_text(
                    "Player returned Lina's lost key.",
                    source="memory:test",
                )

        self.assertEqual(first["status"], "translated")
        self.assertEqual(second["status"], "cached")
        self.assertEqual(second["translated_text"], "玩家归还了 Lina 丢失的钥匙。")
        self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
