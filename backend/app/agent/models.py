"""Models for the deep agent, tried in order for every call: AWS Bedrock, then Groq's free tier, then Ollama on this
machine.

Bedrock (when AWS keys are set): Claude Sonnet coordinates and Claude Haiku runs the helper agents, with Amazon Nova
as the Bedrock backup (Nova needs no extra AWS approval). Fallback happens per model call, not per run: if a model is
throttled, not enabled for the account, times out, or returns a malformed tool call, that one step goes to the next
model and the run carries on. Without AWS keys everything runs on the free models only.
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


# AWS Bedrock: Claude for quality, Nova as the backup (no Anthropic use-case form needed). Override with env vars.
ROLE_BEDROCK_MODEL = {
    "coordinator": os.getenv("PLUMBLINE_BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-6"),
    "helper": os.getenv("PLUMBLINE_BEDROCK_HELPER", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
}
ROLE_BEDROCK_BACKUP = {
    "coordinator": os.getenv("PLUMBLINE_BEDROCK_BACKUP", "us.amazon.nova-pro-v1:0"),
    "helper": os.getenv("PLUMBLINE_BEDROCK_HELPER_BACKUP", "us.amazon.nova-lite-v1:0"),
}
BEDROCK_LABEL = {"claude-sonnet": "Claude Sonnet", "claude-haiku": "Claude Haiku", "nova-pro": "Nova Pro",
                 "nova-lite": "Nova Lite", "nova-2-lite": "Nova 2 Lite"}


def bedrock_ready() -> bool:
    return bool(settings.aws_access_key_id) and os.getenv("PLUMBLINE_BEDROCK", "on") != "off"


def _bedrock(model: str):
    from botocore.config import Config
    from langchain_aws import ChatBedrockConverse
    return ChatBedrockConverse(model=model, region_name=settings.aws_region, temperature=0, max_tokens=4096,
                               config=Config(retries={"max_attempts": 1, "mode": "standard"}, read_timeout=90, connect_timeout=10))


def _bedrock_name(model: str) -> str:
    label = next((v for k, v in BEDROCK_LABEL.items() if k in model), model)
    version = re.search(r"(\d+-\d+)(?:-\d{8})?(?:-v\d)?(?::\d)?$", model)
    return f"Bedrock {label}" + (f" {version.group(1).replace('-', '.')}" if version and "claude" in model else "")


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


# Bedrock errors that won't fix themselves within a run (model not enabled, AWS form pending, account still verifying).
_NOT_ENABLED = ("use case details", "not available for this account", "AccessDenied", "being verified", "Legacy",
                "don't have access", "not authorized")


def _cooldown_seconds(error: Exception) -> float:
    text = f"{type(error).__name__} {error}"
    if any(k in text for k in _NOT_ENABLED):
        return 15 * 60.0  # skip that model for a while instead of failing on every step
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", text)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    low = text.lower()
    return 20.0 if "429" in text or "rate limit" in low or "throttl" in low or "too many requests" in low else 0.0


class FreeChatModel(BaseChatModel):
    """Tries each model in order for every call. Remembers which one answered, for the UI and the trace."""

    chain: list[Any]
    names: list[str]
    retry: Any = None          # used only after every model failed once: local model with a little randomness
    patient: bool = False      # no local model (cloud server): more rounds, waiting out the per-minute rate-limit window
    served: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "plumbline-chain"

    def bind_tools(self, tools, **kwargs):
        kwargs.pop("tool_choice", None)  # forced tool choice isn't supported everywhere; the prompt steers instead
        return self.bind(tools=[convert_to_openai_tool(t) for t in tools], **kwargs)

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        errors = []
        rounds, max_wait = (6, 30.0) if self.patient else (3, 10.0)
        for attempt in range(rounds):
            candidates = list(zip(self.names, self.chain))
            if attempt >= 2 and self.retry is not None:
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
            # Everyone failed this round: wait out the shortest rate-limit window and go again.
            pending = [t - time.time() for t in _COOLDOWN.values() if t > time.time()]
            time.sleep(min(min(pending, default=1.0), max_wait))
        raise RuntimeError("All models failed. " + " | ".join(errors[-4:]))


def free_model(role: str = "coordinator") -> FreeChatModel:
    """The model chain for a role: Bedrock (if AWS keys are set), then the free models."""
    chain, names = [], []
    if bedrock_ready():
        kind = "coordinator" if role == "coordinator" else "helper"
        for m in dict.fromkeys([ROLE_BEDROCK_MODEL[kind], ROLE_BEDROCK_BACKUP[kind]]):
            chain.append(_bedrock(m)); names.append(_bedrock_name(m))
    if settings.groq_api_key:
        m = ROLE_GROQ_MODEL.get(role, ROLE_GROQ_MODEL["coordinator"])
        chain.append(_groq(m)); names.append(f"Groq {m}")
    retry = None
    local = ollama_ready()
    if local:
        chain.append(_ollama()); names.append(f"Ollama {OLLAMA_MODEL}")
        retry = _ollama(temperature=0.5)
    elif settings.groq_api_key:
        # No local model (e.g. the cloud server): the other free Groq models have their own per-minute limits.
        for other in dict.fromkeys(ROLE_GROQ_MODEL.values()):
            if f"Groq {other}" not in names:
                chain.append(_groq(other)); names.append(f"Groq {other}")
    if not chain:
        raise RuntimeError("No model available: set AWS keys for Bedrock, GROQ_API_KEY, or start Ollama with " + OLLAMA_MODEL)
    return FreeChatModel(chain=chain, names=names, retry=retry, served=[], patient=not local)


def any_free_model() -> bool:
    return bedrock_ready() or bool(settings.groq_api_key) or ollama_ready()
