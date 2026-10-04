from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "",
).strip()

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "deepseek/deepseek-v4.1-flash",
).strip()

OPENROUTER_APP_URL = os.getenv(
    "OPENROUTER_APP_URL",
    "http://localhost:4200",
).strip()

OPENROUTER_APP_NAME = os.getenv(
    "OPENROUTER_APP_NAME",
    "Handle It NL",
).strip()


def api_key_configured() -> bool:
    return bool(OPENROUTER_API_KEY)


def _headers() -> dict[str, str]:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not configured. "
            "Copy backend/.env.example to backend/.env "
            "and add your key."
        )

    headers = {
        "Authorization": (
            f"Bearer {OPENROUTER_API_KEY}"
        ),
        "Content-Type": "application/json",
    }

    if OPENROUTER_APP_URL:
        headers["HTTP-Referer"] = (
            OPENROUTER_APP_URL
        )

    if OPENROUTER_APP_NAME:
        headers["X-Title"] = (
            OPENROUTER_APP_NAME
        )

    return headers


async def chat_completion(
    client: httpx.AsyncClient,
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1800,
    response_format: dict[str, Any] | None = None,
    seed: int | None = 42,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    if seed is not None:
        payload["seed"] = seed

    if response_format is not None:
        payload["response_format"] = (
            response_format
        )

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    response = await client.post(
        OPENROUTER_API_URL,
        headers=_headers(),
        json=payload,
    )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text[:1200]

        raise RuntimeError(
            "OpenRouter request failed with HTTP "
            f"{response.status_code}: {detail}"
        ) from exc

    data = response.json()
    choices = data.get("choices") or []

    if not choices:
        raise RuntimeError(
            "OpenRouter returned no choices: "
            f"{data}"
        )

    return (
        choices[0].get("message")
        or {}
    )
