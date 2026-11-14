"""Free models for the deep agent: Groq's free tier first, Ollama on this machine when Groq can't answer.

Fallback happens per model call, not per run: if Groq rate-limits (its free tier allows 8,000 tokens a minute per
model), times out, or returns a malformed tool call, that one step goes to Ollama and the run carries on. Nothing
here costs money. Configure with PLUMBLINE_MODELS, e.g. "groq:openai/gpt-oss-120b,ollama:gpt-oss:20b".
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import httpx
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from ..settings import settings

log = logging.getLogger("plumbline.agent")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("PLUMBLINE_OLLAMA_MODEL", "gpt-oss:20b")

# Each Groq model has its own free per-minute token budget, so the coordinator and helpers use different ones.
ROLE_GROQ_MODEL = {
    "coordinator": os.getenv("PLUMBLINE_GROQ_MODEL", "openai/gpt-oss-120b"),
    "roof": "openai/gpt-oss-20b",
    "interior": "qwen/qwen3.8-27b",
    "records": "openai/gpt-oss-20b",
}


def ollama_ready(model: str = OLLAMA_MODEL) -> bool:
    try:
        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).json().get("models", [])
    except Exception:
        return False
    return any(t.get("name", "").split(":latest")[0] == model.split(":latest")[0] for t in tags)


def _groq(model: str):
    from langchain_groq import ChatGroq
    kw = {"reasoning_effort": "low"} if "gpt-oss" in model else {}
    return ChatGroq(model=model, api_key=settings.groq_api_key, temperature=0, max_retries=0, timeout=60, **kw)


def _ollama(model: str = OLLAMA_MODEL, temperature: float = 0):
    from langchain_ollama import ChatOllama
    return ChatOllama(model=model, base_url=OLLAMA_URL, temperature=temperature, num_ctx=16384, keep_alive="30m",
                      reasoning="low" if "gpt-oss" in model else None)


# After a rate limit, skip that model until its window resets instead of retrying it on every step.
_COOLDOWN: dict[str, float] = {}


def _cooldown_seconds(error: Exception) -> float:
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(error))
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    return 20.0 if "429" in str(error) or "rate limit" in str(error).lower() else 0.0


class FreeChatModel(BaseChatModel):
    """Tries each model in order for every call. Remembers which one answered, for the UI and the trace."""

    chain: list[Any]
    names: list[str]
    retry: Any = None          # used only after every model failed once: local model with a little randomness
    served: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "plumbline-free"

    def bind_tools(self, tools, **kwargs):
        kwargs.pop("tool_choice", None)  # forced tool choice isn't supported everywhere; the prompt steers instead
        return self.bind(tools=[convert_to_openai_tool(t) for t in tools], **kwargs)

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        errors = []
        for attempt in range(3):
            candidates = list(zip(self.names, self.chain))
            if attempt == 2 and self.retry is not None:
                candidates.append((self.names[-1] + " (retry)", self.retry))
            for i, (name, model) in enumerate(candidates):
                last = i == len(candidates) - 1
                if not last and attempt == 0 and _COOLDOWN.get(name, 0) > time.time():
                    continue
                try:
                    result = model._generate(messages, stop=stop, **kwargs)
                    self.served.append(name.replace(" (retry)", ""))
                    return result
                except Exception as e:  # rate limit, timeout, malformed tool call, model not loaded: try the next one
                    errors.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")
                    wait = _cooldown_seconds(e)
                    if wait:
                        _COOLDOWN[name] = time.time() + wait
                    log.warning("model %s failed, falling back: %s", name, str(e)[:120])
            # Everyone failed this round: wait out the shortest rate-limit window (at most 10 s) and go again.
            pending = [t - time.time() for t in _COOLDOWN.values() if t > time.time()]
            time.sleep(min(min(pending, default=1.0), 10.0))
        raise RuntimeError("All free models failed. " + " | ".join(errors[-4:]))


def free_model(role: str = "coordinator") -> FreeChatModel:
    chain, names = [], []
    if settings.groq_api_key:
        m = ROLE_GROQ_MODEL.get(role, ROLE_GROQ_MODEL["coordinator"])
        chain.append(_groq(m)); names.append(f"Groq {m}")
    retry = None
    if ollama_ready():
        chain.append(_ollama()); names.append(f"Ollama {OLLAMA_MODEL}")
        retry = _ollama(temperature=0.5)
    if not chain:
        raise RuntimeError("No free model available: set GROQ_API_KEY or start Ollama with " + OLLAMA_MODEL)
    return FreeChatModel(chain=chain, names=names, retry=retry, served=[])


def any_free_model() -> bool:
    return bool(settings.groq_api_key) or ollama_ready()
