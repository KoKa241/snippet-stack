import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from .backups import BackupError, MAX_BYTES, MAGIC, decrypt, encrypt, export_archive, import_archive, record
from .models import SearchDocument, Snippet, Tag


@override_settings(AXES_ENABLED=False, SEARCH_SEMANTIC_ENABLED=False)
class BackupTests(TestCase):
    password = 'separate archive passphrase'

    def setUp(self):
        self.user = get_user_model().objects.create_user('backup-owner')
        self.other = get_user_model().objects.create_user('backup-recipient')
        self.snippet = Snippet.objects.create(owner=self.user, title='Free port', description='Описание', code='lsof -ti:8080 | xargs kill -9\n', language='shell', favorite=True)
        self.snippet.tags.add(Tag.objects.create(owner=self.user, name='terminal'))
        self.private = Snippet.objects.create(owner=self.other, title='Private', code='other user secret')

    def upload(self, blob):
        return SimpleUploadedFile('backup.ssbackup', blob, content_type='application/octet-stream')

    def test_roundtrip_preserves_data_and_owner_scope_and_is_idempotent(self):
        archive = export_archive(self.user, self.password)
        self.assertNotIn(self.snippet.code.encode(), archive)
        payload = json.loads(decrypt(archive, self.password))
        self.assertEqual(len(payload['snippets']), 1)
        self.assertEqual(set(payload), {'version', 'snippets'})
        self.assertNotIn('owner', payload['snippets'][0])
        self.assertEqual(import_archive(self.other, archive, self.password), (1, 0))
        restored = Snippet.objects.get(owner=self.other, title=self.snippet.title)
        self.assertEqual(record(restored), record(self.snippet))
        self.assertEqual(restored.tags.get().owner_id, self.other.pk)
        self.assertEqual(restored.tags.get().color, self.snippet.tags.get().color)
        self.assertTrue(SearchDocument.objects.filter(snippet=restored).exists())
        self.assertEqual(import_archive(self.other, archive, self.password), (0, 1))
        self.assertTrue(Snippet.objects.filter(pk=self.private.pk).exists())

    def test_export_uses_fresh_salt_and_nonce(self):
        self.assertNotEqual(export_archive(self.user, self.password), export_archive(self.user, self.password))

    def test_wrong_password_and_tampering_never_write(self):
        archive = export_archive(self.user, self.password)
        for blob, password in [(archive, 'wrong'), (archive[:-1] + bytes([archive[-1] ^ 1]), self.password), (archive[:len(MAGIC)] + bytes([archive[len(MAGIC)] ^ 1]) + archive[len(MAGIC)+1:], self.password), (archive[:12], self.password), (b'{}', self.password)]:
            with self.assertRaises(BackupError):
                import_archive(self.other, blob, password)
        self.assertEqual(Snippet.objects.filter(owner=self.other).count(), 1)

    def test_entire_payload_validated_before_writing(self):
        valid = record(self.snippet)
        invalid = dict(valid, title='x' * 121)
        for change in [{'favorite': 'false'}, {'owner': self.user.pk}, {'language': 'invalid'}, {'tags': ['a,b']}, {'tags': ['a'] * 11}, {'created_at': '2026-01-01'}, {'code': ''}, {'code': '\ud800'}, {'title': '\udfff'}, {'tags': ['bad\x01tag']}, {'tags': ['\ud800']}]:
            with self.subTest(change=change):
                rows = [valid, dict(valid, **change)]
                archive = encrypt(json.dumps({'version': 1, 'snippets': rows}).encode(), self.password)
                with self.assertRaises(BackupError):
                    import_archive(self.other, archive, self.password)
        archive = encrypt(json.dumps({'version': 1, 'snippets': [valid, invalid]}).encode(), self.password)
        with self.assertRaises(BackupError):
            import_archive(self.other, archive, self.password)
        self.assertEqual(Snippet.objects.filter(owner=self.other).count(), 1)

    def test_invalid_payload_shapes_and_versions(self):
        for data in [[], {}, {'version': True, 'snippets': []}, {'version': 3, 'snippets': []}, {'version': 1, 'snippets': {}}, {'version': 1, 'snippets': [None]}]:
            with self.assertRaises(BackupError):
                import_archive(self.other, encrypt(json.dumps(data).encode(), self.password), self.password)

    def test_database_error_rolls_back_import(self):
        archive = export_archive(self.user, self.password)
        with patch('snippets.backups.Tag.objects.get_or_create', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                import_archive(self.other, archive, self.password)
        self.assertEqual(Snippet.objects.filter(owner=self.other).count(), 1)

    def test_size_and_count_limits(self):
        with self.assertRaises(BackupError):
            decrypt(b'x' * (MAX_BYTES + 1), self.password)
        with patch('snippets.backups.MAX_SNIPPETS', 0):
            with self.assertRaises(BackupError):
                export_archive(self.user, self.password)
        self.client.force_login(self.user)
        response = self.client.post('/settings/import/', {'import-password': self.password, 'import-archive': self.upload(b'x' * (MAX_BYTES + 1))})
        self.assertEqual(response.status_code, 400)

    def test_browser_download_and_upload_with_password_validation(self):
        self.client.force_login(self.user)
        response = self.client.post('/settings/export/', {'export-password': 'short', 'export-confirm_password': 'short'})
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/settings/export/', {'export-password': self.password, 'export-confirm_password': 'different'})
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, 'value="' + self.password, status_code=400)
        response = self.client.post('/settings/export/', {'export-password': self.password, 'export-confirm_password': self.password})
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.client.force_login(self.other)
        uploaded = self.client.post('/settings/import/', {'import-password': self.password, 'import-archive': self.upload(response.content)})
        self.assertRedirects(uploaded, '/settings/')
        self.assertTrue(Snippet.objects.filter(owner=self.other, title='Free port').exists())

    def test_endpoints_require_session_post_and_csrf(self):
        for url in ['/settings/export/', '/settings/import/']:
            self.assertEqual(self.client.post(url).status_code, 302)
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(url).status_code, 405)
            strict = Client(enforce_csrf_checks=True)
            strict.force_login(self.user)
            self.assertEqual(strict.post(url).status_code, 403)
            self.client.logout()

    def test_empty_archive_and_internal_duplicates(self):
        self.assertEqual(import_archive(self.user, encrypt(b'{"version":1,"snippets":[]}', self.password), self.password), (0, 0))
        row = record(self.snippet)
        archive = encrypt(json.dumps({'version': 1, 'snippets': [row, row]}).encode(), self.password)
        self.assertEqual(import_archive(self.other, archive, self.password), (1, 1))

    def test_import_preserves_existing_tag_colors_and_rejects_invalid_colors(self):
        existing = Tag.objects.create(owner=self.other, name='terminal', color='#112233')
        archive = export_archive(self.user, self.password)
        import_archive(self.other, archive, self.password)
        existing.refresh_from_db()
        self.assertEqual(existing.color, '#112233')
        payload = json.loads(decrypt(archive, self.password))
        payload['snippets'][0]['tag_colors']['terminal'] = 'red; color: black'
        with self.assertRaises(BackupError):
            import_archive(self.other, encrypt(json.dumps(payload).encode(), self.password), self.password)
