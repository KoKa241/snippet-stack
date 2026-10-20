"""Shared library filtering and ranking for HTML and API clients."""
from django.db.models import Case, When, IntegerField
from .models import Snippet
from .search import search_snippets


def select_snippets(user_id, *, q='', language='', tag='', favorite=None, sort='relevance'):
    snippets = Snippet.objects.filter(owner_id=user_id).prefetch_related('tags')
    if language:
        snippets = snippets.filter(language=language)
    if tag:
        snippets = snippets.filter(tags__name=tag)
    if favorite is not None:
        snippets = snippets.filter(favorite=favorite)
    status = ''
    if q:
        result = search_snippets(snippets, user_id=user_id, text=q)
        status = result.semantic_status
        snippets = snippets.filter(pk__in=result.ids)
        if result.ids and sort == 'relevance':
            snippets = snippets.order_by(Case(
                *[When(pk=pk, then=rank) for rank, pk in enumerate(result.ids)],
                output_field=IntegerField(),
            ))
    if sort == 'title':
        snippets = snippets.order_by('title', 'pk')
    elif sort == 'updated' or not q:
        snippets = snippets.order_by('-updated_at', '-pk')
    return snippets, status
