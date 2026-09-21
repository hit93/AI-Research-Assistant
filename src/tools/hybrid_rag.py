"""
Hybrid RAG Engine — Combines BM25 Keyword Search and Vector Cosine Similarity Search
with Reciprocal Rank Fusion (RRF) for node-level precision retrieval.
"""

import math
import re
from dataclasses import dataclass
from typing import List, Dict, Optional
from src.models.schemas import ResearchSource
from src.utils.logger import get_logger

logger = get_logger("tools.hybrid_rag")

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False
    logger.warning("rank-bm25 not installed; falling back to token-overlap search.")


@dataclass
class HybridRAGChunk:
    """Represents a text chunk extracted from a research source."""
    chunk_id: str
    text: str
    source_index: int
    title: str
    url_or_id: str
    source_type: str
    score: float = 0.0
    has_full_text: bool = False


def _tokenize(text: str) -> List[str]:
    """Simple alphanumeric tokenization for BM25 and vector matching."""
    return re.findall(r"\w+", text.lower())


def _cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """Compute cosine similarity between two term-frequency sparse vectors."""
    intersection = set(vec1.keys()) & set(vec2.keys())
    if not intersection:
        return 0.0
    dot_product = sum(vec1[t] * vec2[t] for t in intersection)
    mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    return dot_product / (mag1 * mag2)


def _text_to_tf_vector(text: str) -> Dict[str, float]:
    """Convert text into a term-frequency vector for lightweight cosine similarity."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    tf: Dict[str, float] = {}
    for token in tokens:
        tf[token] = tf.get(token, 0.0) + 1.0
    total = float(len(tokens))
    return {k: v / total for k, v in tf.items()}


def chunk_source(
    source: ResearchSource,
    source_index: int,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> List[HybridRAGChunk]:
    """Split a ResearchSource (full text if available, else content) into overlapping passages."""
    text = (source.full_text if getattr(source, "has_full_text", False) and source.full_text else source.content) or ""
    if not text.strip():
        text = f"{source.title}. {source.content or ''}"

    has_full = bool(getattr(source, "has_full_text", False))
    chunks: List[HybridRAGChunk] = []
    text_len = len(text)
    start = 0

    if text_len <= chunk_size:
        return [
            HybridRAGChunk(
                chunk_id=f"src_{source_index}_chk_0",
                text=text.strip(),
                source_index=source_index,
                title=source.title,
                url_or_id=source.url_or_id,
                source_type=source.source_type,
                has_full_text=has_full,
            )
        ]

    chunk_count = 0
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                HybridRAGChunk(
                    chunk_id=f"src_{source_index}_chk_{chunk_count}",
                    text=chunk_text,
                    source_index=source_index,
                    title=source.title,
                    url_or_id=source.url_or_id,
                    source_type=source.source_type,
                    has_full_text=has_full,
                )
            )
            chunk_count += 1
        start += chunk_size - chunk_overlap

    return chunks


class HybridRAG:
    """
    Hybrid RAG Engine combining BM25 keyword matching and vector cosine similarity
    with Reciprocal Rank Fusion (RRF) for state-of-the-art context retrieval.
    """

    def __init__(
        self,
        sources: List[ResearchSource],
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ):
        self.sources = sources
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunks: List[HybridRAGChunk] = []
        self._tf_vectors: List[Dict[str, float]] = []
        self._bm25: Optional[Any] = None
        self._build_indexes()

    def _build_indexes(self) -> None:
        """Chunk all sources and build BM25 + vector similarity indexes."""
        self.chunks = []
        for idx, src in enumerate(self.sources):
            self.chunks.extend(
                chunk_source(src, idx, self.chunk_size, self.chunk_overlap)
            )

        if not self.chunks:
            logger.warning("[HybridRAG] No chunks built from provided sources.")
            return

        logger.info(f"[HybridRAG] Built {len(self.chunks)} chunks from {len(self.sources)} sources.")

        # Build TF vectors for cosine similarity
        self._tf_vectors = [_text_to_tf_vector(chk.text) for chk in self.chunks]

        # Build BM25 index
        if HAS_BM25:
            corpus_tokens = [_tokenize(chk.text) for chk in self.chunks]
            self._bm25 = BM25Okapi(corpus_tokens)
        else:
            self._bm25 = None

    def search(self, query: str, top_k: int = 5, rrf_k: int = 60) -> List[HybridRAGChunk]:
        """
        Execute Hybrid RAG search combining BM25 & Vector search via Reciprocal Rank Fusion (RRF).

        Args:
            query: The search question, section topic, or verification claim.
            top_k: Number of top re-ranked chunks to return.
            rrf_k: Constant denominator for Reciprocal Rank Fusion scoring (default 60).

        Returns:
            List of HybridRAGChunk sorted by descending hybrid RRF score.
        """
        if not self.chunks or not query.strip():
            return []

        query_tokens = _tokenize(query)
        query_vector = _text_to_tf_vector(query)

        # 1. BM25 Search & Ranking
        bm25_ranks: Dict[int, int] = {}
        if self._bm25 and query_tokens:
            bm25_scores = self._bm25.get_scores(query_tokens)
            sorted_bm25_indices = sorted(
                range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True
            )
            for rank, idx in enumerate(sorted_bm25_indices, start=1):
                bm25_ranks[idx] = rank
        else:
            # Fallback token overlap scoring if BM25 unavailable
            overlap_scores = [
                sum(query_vector.get(t, 0.0) for t in _tokenize(chk.text))
                for chk in self.chunks
            ]
            sorted_indices = sorted(
                range(len(overlap_scores)), key=lambda i: overlap_scores[i], reverse=True
            )
            for rank, idx in enumerate(sorted_indices, start=1):
                bm25_ranks[idx] = rank

        # 2. Vector Cosine Similarity Search & Ranking
        vector_scores = [
            _cosine_similarity(query_vector, tf_vec) for tf_vec in self._tf_vectors
        ]
        sorted_vec_indices = sorted(
            range(len(vector_scores)), key=lambda i: vector_scores[i], reverse=True
        )
        vector_ranks: Dict[int, int] = {
            idx: rank for rank, idx in enumerate(sorted_vec_indices, start=1)
        }

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: Dict[int, float] = {}
        for idx in range(len(self.chunks)):
            r_bm25 = bm25_ranks.get(idx, len(self.chunks))
            r_vec = vector_ranks.get(idx, len(self.chunks))
            score = (1.0 / (rrf_k + r_bm25)) + (1.0 / (rrf_k + r_vec))
            rrf_scores[idx] = score

        # Top-K Selection
        top_indices = sorted(
            rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True
        )[:top_k]

        results = []
        for idx in top_indices:
            chk = self.chunks[idx]
            chk_copy = HybridRAGChunk(
                chunk_id=chk.chunk_id,
                text=chk.text,
                source_index=chk.source_index,
                title=chk.title,
                url_or_id=chk.url_or_id,
                source_type=chk.source_type,
                score=round(rrf_scores[idx], 5),
            )
            results.append(chk_copy)

        logger.debug(f"[HybridRAG] Query '{query[:40]}...' returned {len(results)} chunks")
        return results

    def search_in_source(self, source_index: int, query: str, top_k: int = 3) -> List[HybridRAGChunk]:
        """
        Search strictly within chunks belonging to a specific source index.
        Used for claim-level verification against cited sources.
        """
        source_chunks = [c for c in self.chunks if c.source_index == source_index]
        if not source_chunks or not query.strip():
            return []

        query_tokens = set(_tokenize(query))
        query_vec = _text_to_tf_vector(query)

        scored = []
        for chk in source_chunks:
            chk_tokens = set(_tokenize(chk.text))
            overlap = len(query_tokens & chk_tokens)
            chk_vec = _text_to_tf_vector(chk.text)
            cos_sim = _cosine_similarity(query_vec, chk_vec)
            combined_score = (overlap * 0.4) + (cos_sim * 0.6)
            scored.append((combined_score, chk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [chk for _, chk in scored[:top_k]]


def format_rag_chunks_for_prompt(chunks: List[HybridRAGChunk]) -> str:
    """Format Hybrid RAG context chunks into a clean prompt context block."""
    if not chunks:
        return "No relevant source passages retrieved."

    lines = []
    for i, c in enumerate(chunks, start=1):
        source_label = "📘 Paper" if c.source_type == "arxiv" else "🌐 Web"
        lines.append(
            f"--- RAG Passage [{i}] ({source_label}: \"{c.title}\" | Source #{c.source_index}) ---\n"
            f"{c.text}\n"
        )
    return "\n".join(lines)
