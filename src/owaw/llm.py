"""LLM client over LiteLLM (OpenAI-compatible) with JSON-object guarantee."""
from __future__ import annotations

import json
import os
import re

from owaw.config import GenerationConfig

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)


def _extract_json(text: str) -> dict:
    s = text.strip()
    m = _FENCE_RE.match(s)
    if m:
        s = m.group(1).strip()
    return json.loads(s)


class LLM:
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    @classmethod
    def from_config(cls, gen: GenerationConfig) -> "LLM":
        from openai import OpenAI  # lazy import

        api_key = os.environ.get(gen.api_key_env, "")
        client = OpenAI(base_url=gen.base_url, api_key=api_key)
        return cls(client=client, model=gen.model)

    def _complete(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""

    def chat_json(self, prompt: str) -> dict:
        text = self._complete(prompt)
        try:
            return _extract_json(text)
        except (json.JSONDecodeError, ValueError):
            repair = (
                prompt
                + "\n\nYour previous answer was not valid JSON. "
                + "Reply with ONLY a single valid JSON object, no prose, no code fence."
            )
            text = self._complete(repair)
            try:
                return _extract_json(text)
            except (json.JSONDecodeError, ValueError) as e:
                raise ValueError(f"LLM returned invalid JSON after retry: {e}") from e
