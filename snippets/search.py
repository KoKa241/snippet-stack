"""SQLite FTS5 BM25 + bounded-memory exact cosine retrieval + RRF."""
import heapq
import logging
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from django.conf import settings
from django.db import connection
from .models import SearchDocument

logger = logging.getLogger(__name__)
_encoder = None
_encoder_lock = threading.Lock()
_retry_after = 0.0


def get_encoder(*, download=False):
    global _encoder, _retry_after
    with _encoder_lock:
        if _encoder is not None:
            return _encoder
        if not download and time.monotonic() < _retry_after:
            raise RuntimeError('Semantic model is temporarily unavailable')
        try:
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            from fastembed import TextEmbedding
            _encoder = TextEmbedding(
                model_name=settings.SEARCH_MODEL,
                cache_dir=settings.SEARCH_MODEL_CACHE,
                threads=settings.SEARCH_THREADS,
                local_files_only=not download,
            )
        except Exception:
            _retry_after = time.monotonic() + 60
            raise
        return _encoder


def normalize(vectors):
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != 384 or not np.isfinite(matrix).all():
        raise ValueError('Invalid embedding shape or values')
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError('Zero embedding')
    return matrix / norms


def encode_documents(texts):
    return normalize(list(get_encoder().embed(texts, batch_size=32)))


@lru_cache(maxsize=128)
def encode_query(text):
    # Memory-only cache; this module never persists query text.
    return normalize(list(get_encoder().query_embed(text)))[0]


def fts_query(text):
    # Never accept FTS operators/column selectors from user input.
    words = list(dict.fromkeys(re.findall(r'[^\W_]+', text.casefold())))[:32]
    return ' OR '.join('"' + word + '"*' for word in words)


def lexical_candidates(queryset, text, limit):
    query = fts_query(text)
    if not query:
        return []
    sql, params = queryset.order_by().values('pk').query.sql_with_params()
    with connection.cursor() as cursor:
        cursor.execute(
            f'''SELECT rowid FROM snippet_fts
                WHERE snippet_fts MATCH %s AND rowid IN ({sql})
                ORDER BY bm25(snippet_fts, 4.0, 2.0, 1.0, 3.0), rowid
                LIMIT %s''', [query, *params, limit],
        )
        return [row[0] for row in cursor.fetchall()]


def vector_candidates(queryset, text, limit):
    documents = SearchDocument.objects.filter(
        snippet_id__in=queryset.order_by().values('pk'),
        embedding_model=settings.SEARCH_MODEL, embedding__isnull=False,
    ).order_by('pk').values_list('snippet_id', 'embedding')
    if not documents.exists():
        return []
    query = encode_query(text)
    # No ANN truncation before owner/tag/language filtering; never load other users' vectors.
    best, batch = [], []

    def score_batch(rows):
        ids, vectors = [], []
        for pk, blob in rows:
            if len(blob) != 384 * 4:
                continue
            vector = np.frombuffer(blob, dtype='<f4')
            if np.isfinite(vector).all():
                ids.append(pk)
                vectors.append(vector)
        if not vectors:
            return
        scores = np.stack(vectors) @ query
        for pk, score in zip(ids, scores, strict=True):
            if score < settings.SEARCH_MIN_SIMILARITY:
                continue
            entry = (float(score), -pk)
            if len(best) < limit:
                heapq.heappush(best, entry)
            elif entry > best[0]:
                heapq.heapreplace(best, entry)

    for row in documents.iterator(chunk_size=256):
        batch.append(row)
        if len(batch) == 256:
            score_batch(batch)
            batch.clear()
    score_batch(batch)
    return [-pk for _, pk in sorted(best, reverse=True)]


def reciprocal_rank_fusion(*rankings, k=60):
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, pk in enumerate(dict.fromkeys(ranking), start=1):
            scores[pk] += 1 / (k + rank)
    return sorted(scores, key=lambda pk: (-scores[pk], pk))


@dataclass
class SearchResult:
    ids: list[int]
    semantic_status: str


def search_snippets(queryset, *, user_id, text):
    queryset = queryset.filter(owner_id=user_id)
    text = text.strip()[:200]
    if not fts_query(text):
        return SearchResult([], 'lexical')
    limit = settings.SEARCH_CANDIDATES
    lexical = lexical_candidates(queryset, text, limit)
    semantic, status = [], 'disabled'
    if settings.SEARCH_SEMANTIC_ENABLED:
        pending = SearchDocument.objects.filter(snippet_id__in=queryset.order_by().values('pk')).exclude(
            embedding_model=settings.SEARCH_MODEL, embedding__isnull=False,
        ).exists()
        status = 'indexing' if pending else 'ready'
        try:
            semantic = vector_candidates(queryset, text, limit)
        except Exception as exc:
            # Public UI and logs never expose paths, snippets or query contents.
            logger.warning('Semantic search unavailable (%s)', type(exc).__name__)
            status = 'unavailable'
    return SearchResult(reciprocal_rank_fusion(lexical, semantic), status)
