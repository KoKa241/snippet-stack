"""Index maintenance. Embedding inference never runs in the save transaction."""
import hashlib
import json
from django.db import transaction
from .models import SearchDocument, Snippet


def document_fields(snippet):
    fields = {
        'title': snippet.title,
        'description': snippet.description,
        'code': snippet.code,
        'tags': ' '.join(snippet.tags.order_by('name').values_list('name', flat=True)),
    }
    fields['content_hash'] = hashlib.sha256(
        json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return fields


@transaction.atomic
def sync_document(snippet):
    snippet = Snippet.objects.filter(pk=snippet.pk).first()
    if snippet is None:
        return
    fields = document_fields(snippet)
    existing = SearchDocument.objects.filter(pk=snippet.pk)
    if existing.filter(content_hash=fields['content_hash']).exists():
        return
    SearchDocument.objects.update_or_create(
        snippet_id=snippet.pk,
        defaults={**fields, 'embedding': None, 'embedding_model': ''},
    )


def rebuild_documents():
    # Also repairs bulk imports/QuerySet.update(), which bypass Django signals.
    for pk in Snippet.objects.order_by('pk').values_list('pk', flat=True).iterator():
        with transaction.atomic():
            snippet = Snippet.objects.filter(pk=pk).first()
            if snippet:
                sync_document(snippet)


def index_batch(batch_size=32):
    from django.conf import settings
    from django.db.models import Q
    from .search import encode_documents
    documents = list(SearchDocument.objects.filter(
        Q(embedding__isnull=True) | ~Q(embedding_model=settings.SEARCH_MODEL)
    ).order_by('pk')[:batch_size])
    if not documents:
        return 0
    texts = [f'{d.title}\n{d.description}\n{d.tags}\n{d.code}' for d in documents]
    vectors = encode_documents(texts)
    for document, vector in zip(documents, vectors, strict=True):
        # Compare-and-swap: an edit/deletion during inference must win.
        SearchDocument.objects.filter(pk=document.pk, content_hash=document.content_hash).update(
            embedding=vector.astype('<f4').tobytes(), embedding_model=settings.SEARCH_MODEL,
        )
    return len(documents)
