import hashlib
import json
from django.db import migrations


def backfill(apps, schema_editor):
    Snippet = apps.get_model('snippets', 'Snippet')
    Document = apps.get_model('snippets', 'SearchDocument')
    for snippet in Snippet.objects.iterator():
        fields = {'title': snippet.title, 'description': snippet.description, 'code': snippet.code,
                  'tags': ' '.join(snippet.tags.order_by('name').values_list('name', flat=True))}
        digest = hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        Document.objects.create(snippet_id=snippet.pk, content_hash=digest, **fields)


class Migration(migrations.Migration):
    dependencies = [('snippets', '0002_searchdocument')]
    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunSQL(
            """
            CREATE VIRTUAL TABLE snippet_fts USING fts5(
                title, description, code, tags,
                content='snippets_searchdocument', content_rowid='snippet_id',
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TRIGGER search_document_insert AFTER INSERT ON snippets_searchdocument BEGIN
                INSERT INTO snippet_fts(rowid, title, description, code, tags)
                VALUES (new.snippet_id, new.title, new.description, new.code, new.tags);
            END;
            CREATE TRIGGER search_document_delete AFTER DELETE ON snippets_searchdocument BEGIN
                INSERT INTO snippet_fts(snippet_fts, rowid, title, description, code, tags)
                VALUES ('delete', old.snippet_id, old.title, old.description, old.code, old.tags);
            END;
            CREATE TRIGGER search_document_update AFTER UPDATE OF title, description, code, tags ON snippets_searchdocument BEGIN
                INSERT INTO snippet_fts(snippet_fts, rowid, title, description, code, tags)
                VALUES ('delete', old.snippet_id, old.title, old.description, old.code, old.tags);
                INSERT INTO snippet_fts(rowid, title, description, code, tags)
                VALUES (new.snippet_id, new.title, new.description, new.code, new.tags);
            END;
            INSERT INTO snippet_fts(snippet_fts) VALUES ('rebuild');
            """,
            """
            DROP TRIGGER IF EXISTS search_document_insert;
            DROP TRIGGER IF EXISTS search_document_delete;
            DROP TRIGGER IF EXISTS search_document_update;
            DROP TABLE IF EXISTS snippet_fts;
            """,
        ),
    ]
