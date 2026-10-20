import os
from unittest import skipUnless
from unittest.mock import patch
import numpy as np
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from .models import Snippet, Tag, SearchDocument
from .search import fts_query, reciprocal_rank_fusion, search_snippets
from .search_index import index_batch, rebuild_documents


def vector(index=0):
    result = np.zeros(384, dtype=np.float32)
    result[index] = 1
    return result


@override_settings(SEARCH_SEMANTIC_ENABLED=False, AXES_ENABLED=False)
class SearchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('search-user')
        self.other = get_user_model().objects.create_user('other-user')
        self.command = Snippet.objects.create(owner=self.user, title='Free port',
            description='Terminate the process listening on a TCP port',
            code='lsof -ti:8080 | xargs kill -9', language='shell')
        self.python = Snippet.objects.create(owner=self.user, title='Read JSON',
            code='json.loads(data)', language='python')
        self.secret = Snippet.objects.create(owner=self.other, title='Free port secret',
            code='lsof -ti:8080 | xargs kill -9', language='shell')

    def search(self, text, queryset=None):
        return search_snippets(queryset if queryset is not None else Snippet.objects.all(),
                               user_id=self.user.pk, text=text)

    def embed(self, snippet, index=0):
        SearchDocument.objects.filter(pk=snippet.pk).update(
            embedding=vector(index).astype('<f4').tobytes(), embedding_model=settings.SEARCH_MODEL)

    def test_bm25_and_owner_scope(self):
        self.assertEqual(self.search('8080').ids, [self.command.pk])
        self.assertEqual(self.search('lsof kill').ids, [self.command.pk])

    def test_query_is_data_not_fts_syntax(self):
        for query in ['" OR * NOT -', 'title:secret', '"; DROP TABLE snippets_snippet;--', '(){}', '💻']:
            result = self.search(query)
            self.assertNotIn(self.secret.pk, result.ids)
        self.assertTrue(Snippet.objects.filter(pk=self.command.pk).exists())
        self.assertEqual(fts_query(''), '')
        self.assertEqual(fts_query('kill -9'), '"kill"* OR "9"*')

    def test_tags_rename_remove_and_delete_update_fts(self):
        tag = Tag.objects.create(owner=self.user, name='network')
        self.command.tags.add(tag)
        self.assertEqual(self.search('network').ids, [self.command.pk])
        tag.name = 'ports'
        tag.save()
        self.assertEqual(self.search('network').ids, [])
        self.assertEqual(self.search('ports').ids, [self.command.pk])
        tag.delete()
        self.assertEqual(self.search('ports').ids, [])

    def test_reverse_clear_updates_fts(self):
        tag = Tag.objects.create(owner=self.user, name='reverse-tag')
        tag.snippet_set.add(self.command)
        self.assertEqual(self.search('reverse').ids, [self.command.pk])
        tag.snippet_set.clear()
        self.assertEqual(self.search('reverse').ids, [])

    def test_edit_invalidates_embedding_but_favorite_does_not(self):
        self.embed(self.command)
        self.command.favorite = True
        self.command.save(update_fields=['favorite'])
        self.assertIsNotNone(SearchDocument.objects.get(pk=self.command.pk).embedding)
        self.command.code = 'docker ps'
        self.command.save()
        self.assertIsNone(SearchDocument.objects.get(pk=self.command.pk).embedding)
        self.assertEqual(self.search('lsof').ids, [])
        self.assertEqual(self.search('docker').ids, [self.command.pk])

    def test_delete_removes_fts_and_vector(self):
        pk = self.command.pk
        self.command.delete()
        self.assertFalse(SearchDocument.objects.filter(pk=pk).exists())
        self.assertEqual(self.search('lsof').ids, [])

    def test_rebuild_repairs_bulk_updates(self):
        Snippet.objects.filter(pk=self.command.pk).update(code='unique_rebuilt_command')
        rebuild_documents()
        self.assertEqual(self.search('rebuilt').ids, [self.command.pk])
        self.assertEqual(self.search('lsof').ids, [])

    def test_rrf_one_based_ranks_and_deterministic_ties(self):
        self.assertEqual(reciprocal_rank_fusion([10, 20], [30, 20]), [20, 10, 30])
        self.assertEqual(reciprocal_rank_fusion([10, 10, 20]), [10, 20])

    @override_settings(SEARCH_SEMANTIC_ENABLED=True)
    @patch('snippets.search.encode_query', return_value=vector())
    def test_semantic_only_match_and_pre_filtered_top_k(self, encode):
        self.embed(self.command)
        self.embed(self.python, 1)
        self.embed(self.secret)
        with override_settings(SEARCH_CANDIDATES=1):
            result = self.search('освободить занятый порт')
        self.assertEqual(result.ids, [self.command.pk])
        self.assertEqual(result.semantic_status, 'ready')
        self.assertEqual(self.search('освободить порт', Snippet.objects.filter(language='python')).ids, [])
        self.assertEqual(self.search('освободить порт', Snippet.objects.filter(favorite=True)).ids, [])

    @override_settings(SEARCH_SEMANTIC_ENABLED=True)
    @patch('snippets.search.encode_query', side_effect=RuntimeError('offline'))
    def test_model_failure_falls_back_to_bm25(self, encode):
        self.embed(self.command)
        result = self.search('lsof')
        self.assertEqual(result.ids, [self.command.pk])
        self.assertEqual(result.semantic_status, 'unavailable')

    @override_settings(SEARCH_SEMANTIC_ENABLED=True)
    @patch('snippets.search.encode_query')
    def test_unindexed_docs_are_immediately_searchable_without_model(self, encode):
        result = self.search('lsof')
        self.assertEqual(result.ids, [self.command.pk])
        self.assertEqual(result.semantic_status, 'indexing')
        encode.assert_not_called()

    @patch('snippets.search.encode_documents')
    def test_background_indexing_cannot_overwrite_newer_edit(self, encode):
        def change_during_inference(texts):
            self.command.code = 'newer edit'
            self.command.save()
            return np.stack([vector() for _ in texts])
        encode.side_effect = change_during_inference
        index_batch()
        self.assertIsNone(SearchDocument.objects.get(pk=self.command.pk).embedding)
        self.assertIsNotNone(SearchDocument.objects.get(pk=self.python.pk).embedding)

    def test_search_page_and_language_filter(self):
        self.client.force_login(self.user)
        response = self.client.get('/?q=lsof')
        self.assertContains(response, 'Free port')
        self.assertNotContains(response, 'Free port secret')
        self.assertContains(response, 'По релевантности')
        self.assertNotContains(self.client.get('/?q=lsof&language=python'), 'Free port')


# Explicit opt-in: uses the cached real ONNX model, never downloads during tests.
@skipUnless(os.getenv('RUN_SEMANTIC_TESTS') == '1', 'Set RUN_SEMANTIC_TESTS=1 after index_search downloads the model')
@override_settings(SEARCH_SEMANTIC_ENABLED=True, AXES_ENABLED=False)
class RealSemanticSearchTests(TestCase):
    def test_russian_query_finds_english_command_end_to_end(self):
        user = get_user_model().objects.create_user('semantic-user')
        command = Snippet.objects.create(owner=user, title='Free TCP port',
            description='Terminate the process listening on a port',
            code='lsof -ti:8080 | xargs kill -9', language='shell')
        Snippet.objects.create(owner=user, title='Start HTTP server',
            description='Serve files in the current directory',
            code='python -m http.server 8080', language='shell')
        Snippet.objects.create(owner=user, title='Read JSON file',
            description='Load JSON configuration from disk', code='json.loads(data)', language='python')
        index_batch()
        for query in ['убить процесс на порту 8080', 'освободить занятый порт']:
            result = search_snippets(Snippet.objects.all(), user_id=user.pk, text=query)
            self.assertEqual(result.ids[0], command.pk)
            self.assertEqual(result.semantic_status, 'ready')
        self.client.force_login(user)
        response = self.client.get('/', {'q': 'освободить занятый порт'})
        self.assertEqual(response.context['page'][0].pk, command.pk)
        self.assertContains(response, 'Поиск по словам и смыслу')


@override_settings(SEARCH_SEMANTIC_ENABLED=False)
class SearchMigrationTests(TransactionTestCase):
    def test_existing_snippets_and_tags_are_backfilled(self):
        executor = MigrationExecutor(connection)
        old_target = [('snippets', '0001_initial')]
        new_target = [('snippets', '0003_search_fts')]
        executor.migrate(old_target)
        try:
            apps = executor.loader.project_state(old_target).apps
            user = apps.get_model('auth', 'User').objects.create(username='existing-user')
            snippet = apps.get_model('snippets', 'Snippet').objects.create(
                owner_id=user.pk, title='Old command', code='lsof -ti:8080')
            tag = apps.get_model('snippets', 'Tag').objects.create(owner_id=user.pk, name='legacy')
            snippet.tags.add(tag)
        finally:
            MigrationExecutor(connection).migrate(new_target)
        document = SearchDocument.objects.get(pk=snippet.pk)
        self.assertEqual(document.tags, 'legacy')
        self.assertIsNone(document.embedding)
        result = search_snippets(Snippet.objects.all(), user_id=user.pk, text='legacy 8080')
        self.assertEqual(result.ids, [snippet.pk])
