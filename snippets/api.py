"""Read-only API. Bearer credentials are independent of browser sessions."""
import hashlib
import math
import re
import secrets
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.core.paginator import Paginator, EmptyPage
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .forms import APISearchForm
from .models import APIKey, Snippet
from .selectors import select_snippets


def issue_key(owner, name, lifetime):
    token = 'ss_' + secrets.token_urlsafe(32)
    key = APIKey.objects.create(
        owner=owner, name=name, prefix=token[:11],
        digest=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(days=lifetime),
    )
    return key, token


def error(code, message, status, **extra):
    response = JsonResponse({'error': {'code': code, 'message': message, **extra}}, status=status)
    if status == 401:
        response['WWW-Authenticate'] = 'Bearer realm="Snippet Stack"'
    return response


def api_key_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.method != 'GET':
            response = error('method_not_allowed', 'Only GET is supported.', 405)
            response['Allow'] = 'GET'
            return response
        header = request.headers.get('Authorization', '')
        match = re.fullmatch(r'Bearer (ss_[A-Za-z0-9_-]{43})', header, flags=re.IGNORECASE)
        if not match:
            return error('unauthorized', 'A valid Bearer API key is required.', 401)
        digest = hashlib.sha256(match.group(1).encode()).hexdigest()
        now = timezone.now()
        with transaction.atomic():
            key = APIKey.objects.select_for_update().filter(
                digest=digest, revoked_at__isnull=True, expires_at__gt=now, owner__is_active=True,
            ).first()
            if key is None:
                return error('unauthorized', 'A valid Bearer API key is required.', 401)
            if key.window_started_at is None or (now - key.window_started_at).total_seconds() >= 60:
                key.window_started_at, key.window_requests = now, 0
            if key.window_requests >= settings.API_RATE_LIMIT:
                response = error('rate_limited', 'Too many requests. Try again shortly.', 429)
                response['Retry-After'] = str(max(1, math.ceil(60 - (now - key.window_started_at).total_seconds())))
                return response
            key.window_requests += 1
            key.last_used_at = now
            key.save(update_fields=['window_started_at', 'window_requests', 'last_used_at'])
        request.api_owner_id = key.owner_id
        response = view(request, *args, **kwargs)
        response['X-RateLimit-Limit'] = str(settings.API_RATE_LIMIT)
        response['X-RateLimit-Remaining'] = str(settings.API_RATE_LIMIT - key.window_requests)
        return response
    return wrapped


def serialize(snippet):
    return {
        'id': snippet.pk, 'title': snippet.title, 'description': snippet.description,
        'code': snippet.code, 'language': snippet.language, 'favorite': snippet.favorite,
        'tags': [tag.name for tag in snippet.tags.all()],
        'created_at': snippet.created_at.isoformat(), 'updated_at': snippet.updated_at.isoformat(),
    }


@csrf_exempt
@api_key_required
def search(request):
    form = APISearchForm(request.GET)
    if not form.is_valid():
        return error('invalid_parameters', 'Check the query parameters.', 400, fields=form.errors.get_json_data())
    data = form.cleaned_data
    snippets, status = select_snippets(
        request.api_owner_id, q=data['q'], language=data['language'], tag=data['tag'],
        favorite={'true': True, 'false': False}.get(data['favorite']), sort=data['sort'] or 'relevance',
    )
    paginator = Paginator(snippets, data['page_size'] or 20)
    try:
        page = paginator.page(data['page'] or 1)
    except EmptyPage:
        return error('page_not_found', 'This page does not exist.', 404)
    return JsonResponse({
        'count': paginator.count, 'page': page.number, 'page_size': paginator.per_page,
        'next_page': page.next_page_number() if page.has_next() else None,
        'previous_page': page.previous_page_number() if page.has_previous() else None,
        'semantic_status': status or 'not_requested',
        'results': [serialize(snippet) for snippet in page],
    })


@csrf_exempt
@api_key_required
def detail(request, pk):
    snippet = Snippet.objects.filter(pk=pk, owner_id=request.api_owner_id).prefetch_related('tags').first()
    if snippet is None:
        return error('not_found', 'Snippet not found.', 404)
    return JsonResponse(serialize(snippet))
