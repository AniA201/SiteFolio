"""LangSmith links for agent runs (free Developer plan). Tracing is on whenever LANGSMITH_API_KEY is set."""
from __future__ import annotations

import time


def trace_url(run_id: str, attempts: int = 6) -> str | None:
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers
        from langsmith import Client
    except ImportError:
        return None
    from ..settings import settings
    if not settings.langsmith_api_key:
        return None
    wait_for_all_tracers()
    client = Client()
    for _ in range(attempts):
        try:
            return client.get_run_url(run=client.read_run(run_id))
        except Exception:
            time.sleep(2)
    return None
