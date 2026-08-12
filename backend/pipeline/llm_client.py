"""
Thin wrapper around the Gemini API (google-genai SDK).
Kept as a single client shared by extraction (stage 2) and enrichment
(stage 6) so swapping providers later is a one-file change.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash-lite"


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        self._client = genai.Client(api_key=self.api_key)

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
        """Call the model and parse its response as JSON.

        Uses Gemini's native JSON mode (response_mime_type="application/json")
        rather than prompting "return only JSON" — the field set is dynamic
        per category schema, so we enforce JSON-shaped output at the API
        level instead of a fixed response_schema.

        Raises ValueError if the model didn't return valid JSON — callers
        should treat that as an extraction failure, not silently swallow it.
        """
        response = self._client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        content = response.text

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM did not return valid JSON: {e}\nRaw content: {content}")
