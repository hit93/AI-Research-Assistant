"""
Unit tests for Phase 4: LLM Gateway, STM, LTM, and Semantic Caching.
"""

from unittest.mock import MagicMock, patch
from src.chains.gateway import CircuitBreaker, LLMGateway
from src.memory.stm import ShortTermMemory
from src.memory.ltm import LongTermMemory
from src.memory.semantic_cache import SemanticCache, compute_query_similarity
from src.models.schemas import ResearchResult, QueryPlan, SynthesisSection, VerificationResult


def test_circuit_breaker_logic():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=1.0)
    assert not cb.is_open

    cb.record_failure()
    assert not cb.is_open
    assert cb.failure_count == 1

    cb.record_failure()
    assert cb.is_open

    cb.record_success()
    assert not cb.is_open
    assert cb.failure_count == 0


def test_gateway_fallback_on_primary_failure():
    gateway = LLMGateway(primary_model="fake-primary", fallback_model="fake-fallback", max_retries=1)

    mock_fallback_response = MagicMock(content="Fallback response")

    with patch("src.chains.gateway.get_chat_llm") as mock_get_llm:
        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = RuntimeError("Primary Groq rate-limited")

        fallback_llm = MagicMock()
        fallback_llm.invoke.return_value = mock_fallback_response

        # First call gets primary, second gets fallback
        mock_get_llm.side_effect = [primary_llm, fallback_llm]

        res = gateway.invoke([MagicMock()])
        assert res.content == "Fallback response"
        assert gateway.circuit_breaker.failure_count == 1


def test_stm_session_lifecycle(tmp_path):
    stm = ShortTermMemory(redis_url="redis://fake-host:6379/9")
    session_id = "test_sess_001"

    stm.set_session(session_id, {"topic": "AI", "step": "planning"})
    data = stm.get_session(session_id)
    assert data is not None
    assert data["topic"] == "AI"

    stm.update_session(session_id, "step", "synthesizing")
    updated = stm.get_session(session_id)
    assert updated["step"] == "synthesizing"

    stm.clear_session(session_id)
    assert stm.get_session(session_id) is None


def test_ltm_persistence(tmp_path):
    db_file = tmp_path / "test_ltm.db"
    ltm = LongTermMemory(db_path=db_file)

    sample_result = ResearchResult(
        query="Quantum Computing",
        plan=QueryPlan(original_query="Quantum Computing"),
        sources=[],
        synthesis=[SynthesisSection(heading="Overview", content="Quantum bits are qubits.")],
        verification=VerificationResult(is_approved=True, overall_score=9),
        duration_seconds=3.2,
    )

    rec_id = ltm.save_research("Quantum Computing", sample_result)
    assert rec_id == 1

    history = ltm.get_history(limit=5)
    assert len(history) == 1
    assert history[0]["topic"] == "Quantum Computing"
    assert history[0]["score"] == 9

    search_hits = ltm.search_past_research("qubits")
    assert len(search_hits) == 1
    assert search_hits[0]["topic"] == "Quantum Computing"


def test_query_similarity_computation():
    # Exact match
    assert compute_query_similarity("Machine Learning in Healthcare", "Machine Learning in Healthcare") == 1.0

    # Minor variation
    sim_high = compute_query_similarity("Machine Learning in Healthcare", "machine learning in healthcare systems")
    assert sim_high > 0.80

    # Completely different topic
    sim_low = compute_query_similarity("Quantum Physics", "Baking Chocolate Cake")
    assert sim_low < 0.20


def test_semantic_cache_hit_and_miss(tmp_path):
    cache_file = tmp_path / "test_cache.json"
    cache = SemanticCache(cache_file=cache_file)
    cache.threshold = 0.80

    sample_result = ResearchResult(
        query="Autonomous Driving Safety",
        plan=QueryPlan(original_query="Autonomous Driving Safety"),
        sources=[],
        synthesis=[SynthesisSection(heading="Safety", content="LiDAR and radar fusion.")],
        duration_seconds=2.0,
    )

    # Initially empty
    hit, score = cache.get("Autonomous Driving Safety")
    assert hit is None

    # Populate cache
    cache.set("Autonomous Driving Safety", sample_result)

    # Exact query hit
    hit_exact, score_exact = cache.get("Autonomous Driving Safety")
    assert hit_exact is not None
    assert score_exact == 1.0
    assert hit_exact.query == "Autonomous Driving Safety"

    # Similar query hit
    hit_similar, score_sim = cache.get("autonomous driving safety protocols")
    assert hit_similar is not None
    assert score_sim >= 0.80

    # Unrelated query miss
    hit_unrelated, _ = cache.get("Photosynthesis in plants")
    assert hit_unrelated is None
