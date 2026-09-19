import os
from pathlib import Path
from dataclasses import dataclass, field

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

@dataclass
class Settings:
    # LLM & Search
    GROQ_API_KEY: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    GROQ_MODEL: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"))
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

    def validate_keys(self) -> dict[str, bool]:
        """Check available LLM and search keys without exposing values."""
        return {
            "groq": bool(self.GROQ_API_KEY),
            "openai": bool(self.OPENAI_API_KEY),
            "gemini": bool(self.GEMINI_API_KEY),
            "tavily": bool(self.TAVILY_API_KEY),
        }

settings = Settings()

