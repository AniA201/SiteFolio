"""Server-side configuration. Secrets come from environment variables or backend/.env (gitignored).

Nothing here is ever sent to the browser except the Matterport SDK key, which is browser-safe.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _get(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    matterport_api_key: str | None = _get("MATTERPORT_API_KEY")
    matterport_api_token: str | None = _get("MATTERPORT_API_TOKEN")
    matterport_sdk_key: str | None = _get("VITE_MATTERPORT_SDK_KEY") or _get("MATTERPORT_SDK_KEY")
    vexcel_api_key: str | None = _get("VEXCEL_API_KEY")
    costar_kit_url: str | None = _get("COSTAR_KIT_URL")
    costar_kit_zip: str | None = _get("COSTAR_KIT_ZIP")
    costar_zip_password: str | None = _get("COSTAR_ZIP_PASSWORD")
    anthropic_api_key: str | None = _get("ANTHROPIC_API_KEY")
    groq_api_key: str | None = _get("GROQ_API_KEY")
    aws_access_key_id: str | None = _get("AWS_ACCESS_KEY_ID")  # AWS Bedrock models for the agent (boto3 reads the rest)
    aws_region: str = _get("AWS_REGION") or "us-east-1"
    langsmith_api_key: str | None = _get("LANGSMITH_API_KEY")
    tiger_database_url: str | None = _get("TIGER_DATABASE_URL")
    public_url: str | None = _get("PUBLIC_URL")  # where phones reach the app, e.g. https://plumbline.us
    models_index_csv: Path = Path(_get("MODELS_INDEX_CSV") or BACKEND_DIR / "app" / "data" / "models_index.csv")

    @property
    def agent_enabled(self) -> bool:
        """Run the real deep agent on a free model (Groq free tier or local Ollama). PLUMBLINE_AGENT=replay forces the
        recorded plans. Checked per run, so starting Ollama later switches the agent on without a restart."""
        if os.getenv("PLUMBLINE_AGENT", "deep") == "replay":
            return False
        from .agent.models import any_free_model
        return any_free_model()

    def integrations(self) -> dict[str, bool]:
        """Which outside services are configured. Safe to expose: booleans only."""
        return {
            "matterport": bool(self.matterport_api_key and self.matterport_api_token),
            "matterport_sdk": bool(self.matterport_sdk_key),
            "matterport_index": self.models_index_csv.exists(),
            "vexcel": bool(self.vexcel_api_key),
            "costar": bool(self.costar_zip_password and (self.costar_kit_url or self.costar_kit_zip)),
            "ai_model": bool(self.anthropic_api_key),
            "groq": bool(self.groq_api_key),
            "bedrock": bool(self.aws_access_key_id),
            "deep_agent": self.agent_enabled,
            "langsmith": bool(self.langsmith_api_key),
            "tiger": bool(self.tiger_database_url),
        }


settings = Settings()

# LangSmith traces every deep-agent run when a key is set (LangChain reads these variables).
if settings.langsmith_api_key:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", "plumbline")
