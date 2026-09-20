import os
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field


BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)
except ImportError:
    pass


@dataclass
class Settings:
    # LLM & Search
    GROQ_API_KEY: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    GROQ_MODEL: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"))
    SYNTHESIZER_MODEL: str = field(default_factory=lambda: os.getenv("SYNTHESIZER_MODEL", "openai/gpt-oss-120b"))
    VERIFIER_MODEL: str = field(default_factory=lambda: os.getenv("VERIFIER_MODEL", "openai/gpt-oss-120b"))
    SEARCH_ENGINE: str = field(default_factory=lambda: os.getenv("SEARCH_ENGINE", "tavily"))
    
    # Optional fallback keys
    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    GEMINI_API_KEY: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    TAVILY_API_KEY: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    
    # Paths & Logging
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    REPORTS_DIR: Path = field(default_factory=lambda: BASE_DIR / os.getenv("REPORTS_DIR", "data/reports"))
    CACHE_DIR: Path = field(default_factory=lambda: BASE_DIR / os.getenv("CACHE_DIR", "data/cache"))

    # Phase 4: Gateway, Memory & Semantic Cache
    FALLBACK_MODEL: str = field(default_factory=lambda: os.getenv("FALLBACK_MODEL", "llama-3.1-8b-instant"))
    REDIS_URL: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    DATABASE_URL: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/research_memory"))
    SEMANTIC_CACHE_ENABLED: bool = field(default_factory=lambda: os.getenv("SEMANTIC_CACHE_ENABLED", "true").lower() in ("true", "1", "yes"))
    CACHE_SIMILARITY_THRESHOLD: float = field(default_factory=lambda: float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.85")))

    # Observability (LangSmith)
    LANGCHAIN_TRACING_V2: str = field(default_factory=lambda: os.getenv("LANGCHAIN_TRACING_V2", "false"))
    LANGCHAIN_PROJECT: str = field(default_factory=lambda: os.getenv("LANGCHAIN_PROJECT", "research-assistant"))
    LANGCHAIN_ENDPOINT: str = field(default_factory=lambda: os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"))

    def validate_keys(self) -> dict[str, Any]:
        """Check available LLM and search keys without exposing values."""
        ls_key = (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY", "")).strip("'\"")
        is_ls_configured = bool(ls_key) and os.getenv("LANGCHAIN_TRACING_V2", "false").lower() in ("true", "1")
        
        return {
            "groq": bool(self.GROQ_API_KEY),
            "openai": bool(self.OPENAI_API_KEY),
            "gemini": bool(self.GEMINI_API_KEY),
            "tavily": bool(self.TAVILY_API_KEY),
            "langsmith": _ls_is_valid,
            "langsmith_configured": is_ls_configured,
            "langsmith_msg": _ls_status_msg,
        }


def check_langsmith_key(api_key: str, workspace_id: str = "", endpoint: str = "") -> tuple[bool, str]:
    """Validate LangSmith API key with a fast ping against the configured endpoint."""
    if not api_key:
        return False, "Key missing"
    try:
        import requests
        target_endpoint = (
            endpoint
            or os.getenv("LANGSMITH_ENDPOINT")
            or os.getenv("LANGCHAIN_ENDPOINT")
            or "https://api.smith.langchain.com"
        ).strip("'\"").rstrip("/")
        headers = {"x-api-key": api_key, "Accept": "application/json"}
        if workspace_id:
            headers["x-tenant-id"] = workspace_id
        resp = requests.get(
            f"{target_endpoint}/sessions?limit=1",
            headers=headers,
            timeout=2.5,
        )
        if resp.status_code == 200:
            return True, "Valid"
        elif resp.status_code == 403:
            return False, "Forbidden (403)"
        elif resp.status_code == 401:
            return False, "Unauthorized (401)"
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Network check failed ({e})"


# Check and configure LangSmith on startup
_tracing_requested = os.getenv("LANGSMITH_TRACING", os.getenv("LANGCHAIN_TRACING_V2", "")).lower() in ("true", "1")
_raw_ls_key = (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY", "")).strip("'\"")
_workspace_id = (os.getenv("LANGSMITH_WORKSPACE_ID") or os.getenv("LANGCHAIN_WORKSPACE_ID", "")).strip("'\"")
_endpoint = (os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT") or "https://api.smith.langchain.com").strip("'\"").rstrip("/")
_ls_is_valid = False
_ls_status_msg = "Disabled"

if _tracing_requested:
    _ls_is_valid, _ls_status_msg = check_langsmith_key(_raw_ls_key, _workspace_id, _endpoint)
    if _ls_is_valid:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_API_KEY"] = _raw_ls_key
        os.environ["LANGCHAIN_API_KEY"] = _raw_ls_key
        if _workspace_id:
            os.environ["LANGSMITH_WORKSPACE_ID"] = _workspace_id
            os.environ["LANGCHAIN_WORKSPACE_ID"] = _workspace_id
        _proj = (os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT", "research-assistant")).strip("'\"")
        os.environ["LANGSMITH_PROJECT"] = _proj
        os.environ["LANGCHAIN_PROJECT"] = _proj
        os.environ["LANGSMITH_ENDPOINT"] = _endpoint
        os.environ["LANGCHAIN_ENDPOINT"] = _endpoint
        print(f"[LangSmith] [OK] Key verified successfully. Tracing active on project '{_proj}' (Endpoint: {_endpoint}).")
    else:
        # Automatically disable tracing to suppress continuous 403 errors
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        print(f"[LangSmith] [WARN] Key validation failed ({_ls_status_msg}). Auto-disabled tracing to prevent error spam.")
else:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


settings = Settings()




