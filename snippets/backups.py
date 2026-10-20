"""Versioned, password-encrypted snippet archives; no executable serialization."""
import hashlib
import json
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.debug import sensitive_variables

from .models import LANGUAGES, Snippet, Tag

MAGIC = b'SNIPPETSTACK\x01'
MAX_BYTES = 10 * 1024 * 1024
MAX_SNIPPETS = 2000
FIELDS = {'title', 'description', 'code', 'language', 'favorite', 'tags', 'created_at', 'updated_at'}


class BackupError(ValueError):
    pass


@sensitive_variables()
def derive_key(password, salt):
    return Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=65536).derive(password.encode('utf-8'))


@sensitive_variables()
def encrypt(payload, password):
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    header = MAGIC + salt + nonce
    if len(payload) + len(header) + 16 > MAX_BYTES:
        raise BackupError('size')
    return header + AESGCM(derive_key(password, salt)).encrypt(nonce, payload, header)


@sensitive_variables()
def decrypt(archive, password):
    header_size = len(MAGIC) + 28
    if not header_size + 16 <= len(archive) <= MAX_BYTES or not archive.startswith(MAGIC):
        raise BackupError('format')
    header = archive[:header_size]
    salt, nonce = header[len(MAGIC):len(MAGIC) + 16], header[-12:]
    try:
        return AESGCM(derive_key(password, salt)).decrypt(nonce, archive[header_size:], header)
    except InvalidTag as exc:
        raise BackupError('authentication') from exc


def record(snippet):
    return {field: getattr(snippet, field) for field in ('title', 'description', 'code', 'language', 'favorite')} | {
        'tags': sorted(tag.name for tag in snippet.tags.all()),
        'created_at': snippet.created_at.isoformat(), 'updated_at': snippet.updated_at.isoformat(),
    }


@sensitive_variables()
def export_archive(user, password):
    # Incremental size accounting bounds memory even for large libraries.
    parts, size = [], 0
    for snippet in Snippet.objects.filter(owner=user).prefetch_related('tags').iterator(chunk_size=100):
        part = json.dumps(record(snippet), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        size += len(part) + 1
        if size > MAX_BYTES - 100 or len(parts) >= MAX_SNIPPETS:
            raise BackupError('size')
        parts.append(part)
    return encrypt(b'{"version":1,"snippets":[' + b','.join(parts) + b']}', password)


def validate_payload(payload):
    try:
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {'version', 'snippets'} or type(data['version']) is not int or data['version'] != 1:
            raise ValueError()
        rows = data['snippets']
        if not isinstance(rows, list) or len(rows) > MAX_SNIPPETS:
            raise ValueError()
        for row in rows:
            if not isinstance(row, dict) or set(row) != FIELDS:
                raise ValueError()
            for field, maximum in [('title', 120), ('description', 500), ('code', 100000), ('language', 16)]:
                if not isinstance(row[field], str) or len(row[field]) > maximum or '\x00' in row[field]:
                    raise ValueError()
            if not row['title'].strip() or not row['code'] or row['language'] not in dict(LANGUAGES) or type(row['favorite']) is not bool:
                raise ValueError()
            tags = row['tags']
            if not isinstance(tags, list) or len(tags) > 10 or any(not isinstance(t, str) or not t or len(t) > 32 or ',' in t or '\x00' in t or t != t.strip().lower() for t in tags):
                raise ValueError()
            if len(set(tags)) != len(tags):
                raise ValueError()
            for field in ['created_at', 'updated_at']:
                if not isinstance(row[field], str) or len(row[field]) > 40:
                    raise ValueError()
                date = parse_datetime(row[field])
                if date is None or timezone.is_naive(date):
                    raise ValueError()
                row[field] = date
        return rows
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise BackupError('schema') from exc


def fingerprint(row):
    # Dates and database IDs do not affect duplicate detection.
    content = {key: row[key] for key in ['title', 'description', 'code', 'language', 'favorite']}
    content['tags'] = sorted(row['tags'])
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).digest()


@sensitive_variables()
def import_archive(user, archive, password):
    rows = validate_payload(decrypt(archive, password))
    created = skipped = 0
    with transaction.atomic():
        existing = {fingerprint(record(s)) for s in Snippet.objects.filter(owner=user).prefetch_related('tags').iterator(chunk_size=100)}
        for row in rows:
            signature = fingerprint(row)
            if signature in existing:
                skipped += 1
                continue
            snippet = Snippet.objects.create(owner=user, **{key: row[key] for key in ['title', 'description', 'code', 'language', 'favorite']})
            snippet.tags.set([Tag.objects.get_or_create(owner=user, name=name)[0] for name in row['tags']])
            Snippet.objects.filter(pk=snippet.pk).update(created_at=row['created_at'], updated_at=row['updated_at'])
            existing.add(signature)
            created += 1
    return created, skipped
