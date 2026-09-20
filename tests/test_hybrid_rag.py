"""
Unit tests for Hybrid RAG engine (BM25 + Cosine Similarity Vector Search + Reciprocal Rank Fusion).
"""

from src.models.schemas import ResearchSource
from src.tools.hybrid_rag import (
    HybridRAG,
    HybridRAGChunk,
    chunk_source,
    _cosine_similarity,
    _text_to_tf_vector,
    format_rag_chunks_for_prompt,
)


def test_chunk_source():
    source = ResearchSource(
        title="Quantum Computing Test Paper",
        url_or_id="https://arxiv.org/abs/2301.00001",
        source_type="arxiv",
        authors=["Alice", "Bob"],
        abstract="This is an abstract about quantum error correction.",
        content=(
            "Quantum error correction is vital for fault-tolerant quantum computing. "
            "Surface codes provide high error thresholds around 1%. "
            "Logical qubits are formed from 2D arrays of physical qubits. "
            "Syndrome extraction circuits measure parity checks iteratively."
        ),
    )

    chunks = chunk_source(source, source_index=0, chunk_size=100, chunk_overlap=20)
    assert len(chunks) >= 2
    assert chunks[0].source_index == 0
    assert chunks[0].title == "Quantum Computing Test Paper"
    assert "Quantum error correction" in chunks[0].text


def test_hybrid_rag_search():
    source1 = ResearchSource(
        title="Attention Is All You Need",
        url_or_id="https://arxiv.org/abs/1706.03762",
        source_type="arxiv",
        content=(
            "The Transformer architecture relies on self-attention mechanisms to compute "
            "representations of input sequences without recurrent neural networks. "
            "Multi-head attention projects queries, keys, and values into parallel subspaces."
        ),
    )

    source2 = ResearchSource(
        title="Deep Residual Learning for Image Recognition",
        url_or_id="https://arxiv.org/abs/1512.03385",
        source_type="arxiv",
        content=(
            "ResNet introduces residual skip connections to train extremely deep neural networks. "
            "Convolutions and batch normalization stabilize gradient flow in 152-layer networks."
        ),
    )

    hybrid_rag = HybridRAG([source1, source2], chunk_size=200, chunk_overlap=30)
    assert len(hybrid_rag.chunks) >= 2

    # Query 1: Transformer / self-attention
    results1 = hybrid_rag.search("multi-head self-attention queries keys values", top_k=2)
    assert len(results1) > 0
    assert results1[0].title == "Attention Is All You Need"
    assert results1[0].score > 0.0

    # Query 2: ResNet / residual connections
    results2 = hybrid_rag.search("residual skip connections residual learning", top_k=2)
    assert len(results2) > 0
    assert results2[0].title == "Deep Residual Learning for Image Recognition"


def test_format_rag_chunks_for_prompt():
    chunks = [
        HybridRAGChunk(
            chunk_id="chk_1",
            text="ResNet architecture uses skip connections.",
            source_index=1,
            title="ResNet Paper",
            url_or_id="arxiv.org/123",
            source_type="arxiv",
            score=0.033,
        )
    ]

    formatted = format_rag_chunks_for_prompt(chunks)
    assert "ResNet Paper" in formatted
    assert "ResNet architecture uses skip connections" in formatted
