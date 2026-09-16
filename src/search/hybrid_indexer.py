"""Hybrid Search & Vector Indexer using Qdrant + Google / FastEmbed embeddings.

Indexes parsed UI components, routes, and forms for fast semantic and hybrid retrieval.
Includes a lightweight in-memory cosine fallback for environments where Qdrant/embeddings
are still being provisioned.
"""

from __future__ import annotations

import math
import re
import urllib.request
import json
from typing import List, Dict, Any, Optional, Protocol
from pydantic import BaseModel, Field

from src.core.config import settings
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


class Embedder(Protocol):
    def embed(self, texts: List[str]) -> List[List[float]]:
        ...


class GoogleEmbedder:
    """Google Generative Language API text embeddings (AI Studio)."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-004",
        dim: int = 768,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.dim = dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            vectors.append(self._embed_one(text))
        return vectors

    def _embed_one(self, text: str) -> List[float]:
        model = self.model_name
        if not model.startswith("models/"):
            model = f"models/{model}"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/{model}:embedContent"
            f"?key={self.api_key}"
        )
        payload = {
            "model": model,
            "content": {"parts": [{"text": text}]},
        }
        if self.dim:
            payload["outputDimensionality"] = self.dim

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        values = body.get("embedding", {}).get("values")
        if not values:
            raise RuntimeError(f"Google embedding response missing values: {body}")
        return [float(v) for v in values]


class FastEmbedWrapper:
    """Adapter around FastEmbed TextEmbedding."""

    def __init__(self, model_name: str):
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [list(vec) for vec in self._model.embed(texts)]


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
    """High-level Hybrid Indexer leveraging Qdrant + Google/FastEmbed with resilient fallback."""

    def __init__(
        self,
        collection_name: str = "code2guide_ux_docs",
        location: Optional[str] = None,
        url: Optional[str] = None,
        embedding_model_name: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        embedding_dim: Optional[int] = None,
    ):
        self.collection_name = collection_name
        self.url = url if url is not None else settings.qdrant_url
        self.location = location if location is not None else (settings.qdrant_location or ":memory:")
        self.embedding_provider = (embedding_provider or settings.embedding_provider or "google").lower()
        self.embedding_model_name = embedding_model_name or settings.embedding_model
        self.embedding_dim = embedding_dim or settings.embedding_dim or 768
        self.use_vector = False

        self._fallback_indexer = SimpleInMemoryIndexer()
        self._qdrant_client = None
        self._embedder: Optional[Embedder] = None

        if not _has_qdrant:
            return

        try:
            self._embedder = self._build_embedder()
            self._qdrant_client = self._build_qdrant_client()
            if self._embedder is None or self._qdrant_client is None:
                return

            self._qdrant_client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            self.use_vector = True
        except Exception:
            self.use_vector = False
            self._qdrant_client = None
            self._embedder = None

    def _build_embedder(self) -> Optional[Embedder]:
        if self.embedding_provider == "google":
            api_key = settings.google_api_key
            if not api_key:
                return None
            return GoogleEmbedder(
                api_key=api_key,
                model_name=self.embedding_model_name,
                dim=self.embedding_dim,
            )
        if self.embedding_provider == "fastembed" and _has_fastembed:
            return FastEmbedWrapper(self.embedding_model_name)
        return None

    def _build_qdrant_client(self):
        if self.url:
            return QdrantClient(url=self.url, check_compatibility=False)
        return QdrantClient(location=self.location or ":memory:", check_compatibility=False)

    def index_items(self, items: List[IndexedItem]):
        """Indexes parsed UI components and routes."""
        if not items:
            return

        self._fallback_indexer.index(items)

        if self.use_vector and self._qdrant_client and self._embedder:
            try:
                texts = [f"{it.title} | {it.content}" for it in items]
                embeddings = self._embedder.embed(texts)

                points = []
                for idx, (item, emb) in enumerate(zip(items, embeddings)):
                    points.append(
                        PointStruct(
                            id=idx,
                            vector=list(emb),
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
                pass

    def search(self, query: str, limit: int = 5) -> List[HybridSearchHit]:
        """Hybrid search blending semantic and lexical scores."""
        if self.use_vector and self._qdrant_client and self._embedder:
            try:
                query_emb = self._embedder.embed([query])[0]
                search_result = self._qdrant_client.search(
                    collection_name=self.collection_name,
                    query_vector=list(query_emb),
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
