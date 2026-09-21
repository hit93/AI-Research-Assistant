from pathlib import Path
from unittest.mock import patch
from config.settings import settings
from src.utils.logger import get_logger

def test_settings_initialization():
    assert isinstance(settings.REPORTS_DIR, Path)
    assert isinstance(settings.CACHE_DIR, Path)
    assert settings.LOG_LEVEL in ["DEBUG", "INFO", "WARNING", "ERROR"]
    assert settings.GROQ_MODEL != ""
    assert settings.VERIFIER_MODEL != ""
    assert settings.SEARCH_ENGINE == "tavily"


def test_deprecated_groq_model_is_remapped():
    with patch("src.chains.llm.ChatGroq") as mock_chat, patch("src.chains.llm.settings") as mock_settings:
        mock_settings.GROQ_API_KEY = "test-key"
        mock_settings.GROQ_MODEL = "llama-3.1-8b-instant"
        from src.chains.llm import get_chat_llm
        get_chat_llm(model="llama-3.1-8b-instant")
        assert mock_chat.call_args.kwargs["model"] == "openai/gpt-oss-20b"


def test_key_validation():
    keys = settings.validate_keys()
    assert isinstance(keys, dict)
    assert "groq" in keys
    assert "tavily" in keys

def test_logger():
    logger = get_logger("test_logger")
    assert logger.name == "test_logger"
    logger.info("Logger test run successfully.")

if __name__ == "__main__":
    test_settings_initialization()
    test_key_validation()
    test_logger()
    print("All Phase 1 checkpoint tests passed successfully!")

