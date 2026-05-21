import json
import ssl
import unittest
from urllib import error
from unittest.mock import patch

from src.agent.llm_client import LLMSettings, call_openai_compatible_json


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class LLMClientTest(unittest.TestCase):
    def test_retries_url_error_before_success(self) -> None:
        settings = LLMSettings(
            provider="openai_compatible",
            model="test-model",
            base_url="https://api.example.test",
            api_key="test-key",
            timeout_seconds=1,
            retries=1,
        )
        success = _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"npc_response": "好的，我会留意。"}, ensure_ascii=False)
                        }
                    }
                ]
            }
        )

        with patch(
            "src.agent.llm_client.request.urlopen",
            side_effect=[
                error.URLError(ssl.SSLError("UNEXPECTED_EOF_WHILE_READING")),
                success,
            ],
        ) as urlopen:
            response = call_openai_compatible_json(
                system_prompt="Return JSON.",
                user_payload={"input": "hello"},
                settings=settings,
            )

        self.assertEqual(response, {"npc_response": "好的，我会留意。"})
        self.assertEqual(urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
