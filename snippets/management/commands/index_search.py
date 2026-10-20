import time
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection
from snippets.search import get_encoder
from snippets.search_index import index_batch, rebuild_documents
from snippets.models import SearchDocument


class Command(BaseCommand):
    help = 'Download/cache the local model and index missing or changed snippets.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true', help='Poll every 3 seconds; retry temporary failures.')
        parser.add_argument('--rebuild', action='store_true', help='Repair search documents, rebuild FTS and recompute all vectors.')

    def handle(self, *args, **options):
        if options['rebuild']:
            rebuild_documents()
            SearchDocument.objects.update(embedding=None, embedding_model='')
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO snippet_fts(snippet_fts) VALUES ('rebuild')")
        if not settings.SEARCH_SEMANTIC_ENABLED:
            self.stdout.write('Semantic search disabled; FTS index is available.')
            if options['watch']:
                try:
                    while True:
                        time.sleep(60)
                except KeyboardInterrupt:
                    pass
            return
        while True:
            try:
                get_encoder(download=True)
                count = index_batch()
                if count:
                    self.stdout.write(f'Indexed {count} snippets.')
                    continue
                if not options['watch']:
                    return
                close_old_connections()
                time.sleep(3)
            except KeyboardInterrupt:
                return
            except Exception as exc:
                if not options['watch']:
                    raise
                self.stderr.write(f'Indexing paused ({type(exc).__name__}); retry in 30s.')
                close_old_connections()
                time.sleep(30)
