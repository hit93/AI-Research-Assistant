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

    def validate_keys(self) -> dict[str, bool]:
        """Check available LLM and search keys without exposing values."""
        return {
            "groq": bool(self.GROQ_API_KEY),
            "openai": bool(self.OPENAI_API_KEY),
            "gemini": bool(self.GEMINI_API_KEY),
            "tavily": bool(self.TAVILY_API_KEY),
        }

settings = Settings()
