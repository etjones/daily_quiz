"""Optional model backends. The system works with none of these configured.

Models are used at only three formalised touchpoints, each with a fixed prompt in prompts/:
  1. transcribe_box     (VLM)  read one handwritten answer box; never judges correctness
  2. dictation_sentence (LLM)  write a sentence for a spelling word; cached forever
  3. report_narrative   (LLM)  turn the report data structure into a short note

Default endpoint is an OpenAI-compatible server, e.g. LM Studio at http://localhost:1234/v1.
Override with DQ_LLM_URL / DQ_LLM_MODEL / DQ_LLM_KEY.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path


def prompts_dir() -> Path:
    env = os.environ.get("DQ_PROMPTS")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(name: str) -> str:
    return (prompts_dir() / f"{name}.md").read_text()


class NotConfigured(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(m.group(0))


@dataclass
class OpenAICompat:
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "OpenAICompat":
        return cls(
            base_url=os.environ.get("DQ_LLM_URL", "http://localhost:1234/v1"),
            model=os.environ.get("DQ_LLM_MODEL", ""),
            api_key=os.environ.get("DQ_LLM_KEY", "lm-studio"),
        )

    def _post(self, messages: list[dict], max_tokens: int = 300) -> str:
        body = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.load(resp)
        return data["choices"][0]["message"]["content"]

    # -- VLM ---------------------------------------------------------------
    def transcribe_box(self, png: bytes, kind: str) -> dict:
        prompt = load_prompt("transcribe_box").replace("{kind}", kind)
        b64 = base64.b64encode(png).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}]
        out = _extract_json(self._post(messages))
        return {
            "text": str(out.get("text", "")).strip(),
            "blank": bool(out.get("blank", False)),
            "uncertain": bool(out.get("uncertain", False)),
            "confidence": float(out.get("confidence", 0.0) or 0.0),
        }

    # -- text LLM ----------------------------------------------------------
    def dictation_sentence(self, word: str) -> str:
        messages = [{"role": "user", "content": load_prompt("dictation_sentence") + f"\n\nTarget word: {word}"}]
        out = _extract_json(self._post(messages, max_tokens=120))
        sentence = str(out.get("sentence", "")).strip()
        if not re.search(rf"\b{re.escape(word)}\b", sentence, re.I):
            raise ValueError(f"model sentence does not contain {word!r}: {sentence!r}")
        return sentence

    def narrate(self, report: dict) -> str:
        messages = [{"role": "user", "content": load_prompt("report_narrative") + "\n\n" + json.dumps(report)}]
        return self._post(messages, max_tokens=300).strip()


def backend_from_name(name: str | None):
    """None / 'none' means no model. 'lmstudio' or 'openai' use the OpenAI-compatible client."""
    if not name or name == "none":
        return None
    if name in ("lmstudio", "openai", "local"):
        return OpenAICompat.from_env()
    raise ValueError(f"unknown backend {name!r}")
