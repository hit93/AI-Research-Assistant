# 🤝 Contributing Guidelines

Thank you for your interest in contributing to the **AI Research Assistant**! This guide details how to set up your environment, follow code standards, and submit contributions.

---

## 🛠️ Local Development Setup

### 1. Prerequisites
- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (strongly recommended) or `pip`
- Git

### 2. Initial Setup
```powershell
# Clone repository
git clone <repo-url>
cd "research assistant"

# Create virtual environment
uv venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# Install main & development dependencies
uv pip install -r requirements.txt
uv pip install -e ".[dev]"
```

### 3. Environment Configuration
Copy the `.env.example` template:
```powershell
cp .env.example .env
```
Populate your `.env` with a free Groq API key from [Groq Console](https://console.groq.com) and an optional Tavily API key from [Tavily](https://tavily.com).

---

## 🏗️ Architecture & Conventions

Before making changes, review [ARCHITECTURE.md](ARCHITECTURE.md).

### Layer Responsibilities
- **Prompts (`src/prompts/`)**: Decoupled `ChatPromptTemplate` instances. No business or retrieval logic.
- **Chains (`src/chains/`)**: LCEL runnables binding prompts, model factory, and Pydantic schemas.
- **Graphs (`src/graphs/`)**: LangGraph `StateGraph`, node handlers, and state schemas.
- **Tools (`src/tools/`)**: Standalone data retrievers with resilient timeouts and defensive error recovery.
- **Models (`src/models/`)**: Pydantic models serving as strict contracts between layers.
- **Utils (`src/utils/`)**: Logging, file exports, and helpers.

---

## 🧪 Testing & Code Quality

Always verify your changes before opening a pull request:

```powershell
# 1. Run Ruff linter
uv run ruff check .

# 2. Automatically fix linting/import issues
uv run ruff check . --fix

# 3. Run all offline unit & mock tests (46 tests)
uv run pytest tests/ -k "not test_arxiv_search and not test_web_search"

# 4. Run end-to-end tests including live network APIs (requires API keys)
uv run pytest tests/
```

---

## 🚢 Pull Request Checklist

- [ ] New nodes, chains, or tools have accompanying unit tests in `tests/`.
- [ ] Code conforms to Ruff standards (`uv run ruff check .`).
- [ ] Offline test suite passes 100% without failures.
- [ ] Any new configuration option is documented in `.env.example` and `config/settings.py`.
- [ ] Branch naming convention: `feat/<feature-name>`, `fix/<bug-name>`, or `docs/<update-name>`.
