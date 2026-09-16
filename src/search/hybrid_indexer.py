"""Hybrid Search & Vector Indexer using Qdrant and FastEmbed (BGE-M3 Multilingual).

Indexes parsed UI components, routes, and forms for fast semantic and hybrid retrieval.
Includes a lightweight in-memory cosine fallback for environments where Qdrant/FastEmbed
are still being provisioned.
"""

import math
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.core.normalizer import PersianNormalizer, default_normalizer

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    _has_qdrant = True
except ImportError:
    _has_qdrant = False

try:
    from fastembed import TextEmbedding
    _has_fastembed = True
except ImportError:
    _has_fastembed = False


class IndexedItem(BaseModel):
    """A document or UI artifact indexed in the search system."""
    id: str = Field(description="Unique identifier")
    title: str = Field(description="Persian or English title/label")
    content: str = Field(description="Body, extracted JSX, or description")
    file_path: str = Field(description="Path to source file")
    item_type: str = Field(default="component", description="component, route, form, or button")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HybridSearchHit(BaseModel):
    """Hit returned by hybrid search."""
    id: str
    title: str
    content: str
    file_path: str
    item_type: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SimpleInMemoryIndexer:
    """Deterministic token/character n-gram semantic fallback indexer."""

    def __init__(self, normalizer: Optional[PersianNormalizer] = None):
        self.normalizer = normalizer or default_normalizer
        self.items: Dict[str, IndexedItem] = {}
        self.vocab: Dict[str, int] = {}
        self.doc_vectors: Dict[str, Dict[int, float]] = {}

    def _tokenize(self, text: str) -> List[str]:
        norm = self.normalizer.normalize(text).lower()
        words = re.findall(r'[\w\u0600-\u06FF]+', norm)
        # Add character tri-grams for Persian subword matching
        ngrams = []
        for w in words:
            if len(w) >= 3:
                for i in range(len(w) - 2):
                    ngrams.append(w[i:i+3])
        return words + ngrams

    def clear(self):
        self.items.clear()
        self.vocab.clear()
        self.doc_vectors.clear()

    def index(self, items: List[IndexedItem]):
        for item in items:
            self.items[item.id] = item
            tokens = self._tokenize(f"{item.title} {item.content} {item.file_path}")
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
                if t not in self.vocab:
                    self.vocab[t] = len(self.vocab)

            vec: Dict[int, float] = {}
            total_tokens = len(tokens) or 1
            for t, count in tf.items():
                dim = self.vocab[t]
                vec[dim] = count / total_tokens

            # Compute L2 norm
            norm_val = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self.doc_vectors[item.id] = {d: v / norm_val for d, v in vec.items()}

    def search(self, query: str, limit: int = 5) -> List[HybridSearchHit]:
        query_tokens = self._tokenize(query)
        q_vec: Dict[int, float] = {}
        total = len(query_tokens) or 1
        for t in query_tokens:
            if t in self.vocab:
                dim = self.vocab[t]
                q_vec[dim] = q_vec.get(dim, 0.0) + (1.0 / total)

        q_norm = math.sqrt(sum(v * v for v in q_vec.values()))
        if q_norm == 0:
            # Fallback to simple title/content substring match
            hits = []
            clean_q = self.normalizer.normalize(query).lower()
            for item in self.items.values():
                score = 0.1
                combined = f"{item.title} {item.content} {item.file_path}".lower()
                if clean_q in combined:
                    score = 0.8
                hits.append(
                    HybridSearchHit(
                        id=item.id,
                        title=item.title,
                        content=item.content,
                        file_path=item.file_path,
                        item_type=item.item_type,
                        score=score,
                        metadata=item.metadata
                    )
                )
            hits.sort(key=lambda h: h.score, reverse=True)
            return hits[:limit]

        for dim in q_vec:
            q_vec[dim] /= q_norm

        scores: List[HybridSearchHit] = []
        for doc_id, d_vec in self.doc_vectors.items():
            dot = sum(val * d_vec.get(dim, 0.0) for dim, val in q_vec.items())
            item = self.items[doc_id]
            scores.append(
                HybridSearchHit(
                    id=item.id,
                    title=item.title,
                    content=item.content,
                    file_path=item.file_path,
                    item_type=item.item_type,
                    score=float(dot),
                    metadata=item.metadata
                )
            )

        scores.sort(key=lambda h: h.score, reverse=True)
        return scores[:limit]


class HybridIndexer:
    """High-level Hybrid Indexer leveraging Qdrant + BGE-M3 with resilient fallback."""

    def __init__(
        self,
        collection_name: str = "code2guide_ux_docs",
        location: str = ":memory:",
        embedding_model_name: str = "BAAI/bge-m3"
    ):
        self.collection_name = collection_name
        self.location = location
        self.embedding_model_name = embedding_model_name
        self.use_vector = _has_qdrant and _has_fastembed

        self._fallback_indexer = SimpleInMemoryIndexer()
        self._qdrant_client = None
        self._embedder = None

        if self.use_vector:
            try:
                self._qdrant_client = QdrantClient(location=self.location)
                self._embedder = TextEmbedding(model_name=self.embedding_model_name)
                # Ensure collection exists
                sample_dim = 1024  # BGE-M3 dimension
                self._qdrant_client.recreate_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=sample_dim, distance=Distance.COSINE)
                )
            except Exception:
                self.use_vector = False

    def index_items(self, items: List[IndexedItem]):
        """Indexes parsed UI components and routes."""
        if not items:
            return

        # Always update local fallback for fast keyword lookup
        self._fallback_indexer.index(items)

        if self.use_vector and self._qdrant_client and self._embedder:
            try:
                texts = [f"{it.title} | {it.content}" for it in items]
                embeddings = list(self._embedder.embed(texts))

                points = []
                for idx, (item, emb) in enumerate(zip(items, embeddings)):
                    points.append(
                        PointStruct(
                            id=idx,
                            vector=emb.tolist(),
                            payload={
                                "item_id": item.id,
                                "title": item.title,
                                "content": item.content,
                                "file_path": item.file_path,
                                "item_type": item.item_type,
                                "metadata": item.metadata,
                            }
                        )
                    )

                self._qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=points
                )
            except Exception:
                # Vector failure gracefully shifts to fallback
                pass

    def search(self, query: str, limit: int = 5) -> List[HybridSearchHit]:
        """Hybrid search blending semantic and lexical scores."""
        if self.use_vector and self._qdrant_client and self._embedder:
            try:
                query_emb = list(self._embedder.embed([query]))[0].tolist()
                search_result = self._qdrant_client.search(
                    collection_name=self.collection_name,
                    query_vector=query_emb,
                    limit=limit
                )
                hits = []
                for hit in search_result:
                    payload = hit.payload or {}
                    hits.append(
                        HybridSearchHit(
                            id=str(payload.get("item_id", hit.id)),
                            title=str(payload.get("title", "")),
                            content=str(payload.get("content", "")),
                            file_path=str(payload.get("file_path", "")),
                            item_type=str(payload.get("item_type", "component")),
                            score=float(hit.score),
                            metadata=payload.get("metadata", {})
                        )
                    )
                return hits
            except Exception:
                pass

        return self._fallback_indexer.search(query, limit=limit)
