"""SQLite FTS5 BM25 + sqlite-vec cosine retrieval + local E5 + RRF."""
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


def get_encoder():
    global _encoder, _retry_after
    with _encoder_lock:
        if _encoder is not None:
            return _encoder
        if time.monotonic() < _retry_after:
            raise RuntimeError('Semantic model is temporarily unavailable')
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            torch.set_num_threads(settings.SEARCH_THREADS)
            encoder = SentenceTransformer(
                str(settings.SEARCH_MODEL_PATH), device='cpu', local_files_only=True,
                trust_remote_code=False,
            )
            if encoder.get_sentence_embedding_dimension() != 384:
                raise ValueError('Expected a 384-dimensional E5 model')
            encoder.prompts = {}
            encoder.default_prompt_name = None
            _encoder = encoder
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
    return normalize(get_encoder().encode(
        ['passage: ' + text for text in texts], batch_size=32,
        convert_to_numpy=True, show_progress_bar=False,
    ))


@lru_cache(maxsize=128)
def encode_query(text):
    # Memory-only cache; this module never persists query text.
    return normalize(get_encoder().encode(
        ['query: ' + text], convert_to_numpy=True, show_progress_bar=False,
    ))[0]


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
    query = encode_query(text).astype('<f4').tobytes()
    # Load the trusted packaged extension only when semantic retrieval is needed.
    # Existing BLOB storage remains authoritative: edits/deletes invalidate it atomically.
    import sqlite_vec
    connection.ensure_connection()
    db = connection.connection
    try:
        db.execute('SELECT vec_version()')
    except Exception:
        db.enable_load_extension(True)
        try:
            sqlite_vec.load(db)
        finally:
            db.enable_load_extension(False)
    sql, params = documents.query.sql_with_params()
    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT snippet_id FROM (
                SELECT snippet_id, vec_distance_cosine(embedding, %s) AS distance
                FROM ({sql}) AS eligible
                WHERE length(embedding) = 1536
            ) WHERE distance <= %s
            ORDER BY distance, snippet_id LIMIT %s""",
            [query, *params, 1 - settings.SEARCH_MIN_SIMILARITY, limit],
        )
        return [row[0] for row in cursor.fetchall()]


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
