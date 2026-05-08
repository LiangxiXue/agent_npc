from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = PROJECT_ROOT / ".env"
ENV_KEYS = {
    "AGENT_NPC_LLM_PROVIDER",
    "AGENT_NPC_LLM_API_KEY",
    "AGENT_NPC_LLM_MODEL",
    "AGENT_NPC_LLM_BASE_URL",
    "AGENT_NPC_LLM_TIMEOUT",
    "AGENT_NPC_LLM_RETRIES",
}


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    base_url: str
    api_key: str | None
    timeout_seconds: int
    retries: int

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"

    @property
    def is_configured(self) -> bool:
        return self.is_mock or bool(self.api_key)


def get_llm_settings() -> LLMSettings:
    load_local_env_file()
    return LLMSettings(
        provider=os.environ.get("AGENT_NPC_LLM_PROVIDER", "mock").strip().lower(),
        model=os.environ.get("AGENT_NPC_LLM_MODEL", "gpt-4o-mini"),
        base_url=os.environ.get("AGENT_NPC_LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.environ.get("AGENT_NPC_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"),
        timeout_seconds=int(os.environ.get("AGENT_NPC_LLM_TIMEOUT", "60")),
        retries=int(os.environ.get("AGENT_NPC_LLM_RETRIES", "1")),
    )


def load_local_env_file(path: Path = ENV_FILE_PATH) -> None:
    """Load simple KEY=VALUE settings from .env without adding a dependency."""
    if os.environ.get("AGENT_NPC_SKIP_ENV_FILE") == "1":
        return
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in ENV_KEYS:
            os.environ[key] = value


def get_provider_status() -> dict[str, Any]:
    settings = get_llm_settings()
    return {
        "provider": settings.provider,
        "model": settings.model,
        "base_url": settings.base_url,
        "configured": settings.is_configured,
        "uses_api_key": bool(settings.api_key),
        "timeout_seconds": settings.timeout_seconds,
        "retries": settings.retries,
        "env_file": {
            "path": str(ENV_FILE_PATH),
            "exists": ENV_FILE_PATH.exists(),
            "skipped": os.environ.get("AGENT_NPC_SKIP_ENV_FILE") == "1",
        },
    }


def call_openai_compatible_json(
    system_prompt: str,
    user_payload: dict[str, Any],
    settings: LLMSettings | None = None,
) -> dict[str, Any]:
    """Call an OpenAI-compatible chat completion API and parse a JSON object."""
    active_settings = settings or get_llm_settings()
    if not active_settings.api_key:
        raise RuntimeError("AGENT_NPC_LLM_API_KEY or OPENAI_API_KEY is required for non-mock LLM provider.")

    endpoint = active_settings.base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": active_settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    http_request = request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {active_settings.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    last_timeout: BaseException | None = None
    attempts = max(active_settings.retries, 0) + 1
    for attempt in range(1, attempts + 1):
        try:
            with request.urlopen(http_request, timeout=active_settings.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            break
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP Error {exc.code}: {error_body}") from exc
        except (TimeoutError, socket.timeout) as exc:
            last_timeout = exc
            if attempt == attempts:
                raise RuntimeError(
                    f"LLM request timed out after {active_settings.timeout_seconds}s "
                    f"({attempts} attempt(s)): {exc}"
                ) from exc
            time.sleep(0.5 * attempt)

    if last_timeout is not None and "raw" not in locals():
        raise RuntimeError(f"LLM request timed out: {last_timeout}")

    payload = json.loads(raw)
    content = payload["choices"][0]["message"]["content"]
    return json.loads(content)
