from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from .models import Snippet, Tag

@override_settings(AXES_ENABLED=False)
class SnippetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('alice', password='Test-pass-9362!')
        self.other = get_user_model().objects.create_user('bob', password='Test-pass-9362!')
        self.snippet = Snippet.objects.create(owner=self.user, title='HTTP retry', code='print("hello")', language='python')
        self.foreign = Snippet.objects.create(owner=self.other, title='PRIVATE', code='secret')
        self.client.force_login(self.user)

    def test_private_library(self):
        response = self.client.get('/')
        self.assertContains(response, 'HTTP retry')
        self.assertNotContains(response, 'PRIVATE')
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_anonymous_redirect(self):
        self.client.logout()
        for path in ['/', '/new/', f'/snippets/{self.snippet.pk}/edit/']:
            self.assertEqual(self.client.get(path).status_code, 302)

    def test_owner_boundaries(self):
        for action in ['edit', 'delete', 'favorite']:
            response = self.client.post(f'/snippets/{self.foreign.pk}/{action}/', {'title': 'stolen', 'code': 'x', 'language': 'sql'})
            self.assertEqual(response.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.title, 'PRIVATE')

    def test_create_and_normalize_tags(self):
        response = self.client.post('/new/', {'title': 'New', 'code': 'ls -la', 'language': 'shell', 'tag_names': 'CLI, cli, Linux'})
        self.assertRedirects(response, '/')
        snippet = Snippet.objects.get(title='New')
        self.assertEqual(snippet.owner, self.user)
        self.assertEqual(list(snippet.tags.values_list('name', flat=True)), ['cli', 'linux'])

    def test_update_and_remove_tags(self):
        tag = Tag.objects.create(owner=self.user, name='old')
        self.snippet.tags.add(tag)
        response = self.client.post(f'/snippets/{self.snippet.pk}/edit/', {'title': 'Changed', 'code': 'SELECT 1', 'language': 'sql', 'tag_names': ''})
        self.assertRedirects(response, '/')
        self.snippet.refresh_from_db()
        self.assertEqual(self.snippet.code, 'SELECT 1')
        self.assertEqual(self.snippet.tags.count(), 0)

    def test_code_whitespace_preserved(self):
        code = '\n    print("indent")\n\n'
        self.client.post('/new/', {'title': 'Whitespace', 'code': code, 'language': 'python'})
        self.assertEqual(Snippet.objects.get(title='Whitespace').code, code)

    def test_invalid_language_and_tags(self):
        for data in [{'language': 'invalid'}, {'tag_names': 'x'*33}, {'tag_names': ','.join(map(str, range(11)))}]:
            payload = {'title': 'Bad', 'code': 'x', 'language': 'python', **data}
            self.assertEqual(self.client.post('/new/', payload).status_code, 200)
        self.assertFalse(Snippet.objects.filter(title='Bad').exists())

    def test_search_tag_and_language(self):
        self.snippet.tags.add(Tag.objects.create(owner=self.user, name='network'))
        for query in ['q=hello', 'q=network', 'tag=network', 'language=python']:
            self.assertContains(self.client.get('/?' + query), 'HTTP retry')
        self.assertNotContains(self.client.get('/?language=sql'), 'HTTP retry')
        self.assertNotContains(self.client.get('/?q=secret'), 'PRIVATE')

    def test_favorite_and_delete_require_post(self):
        for action in ['favorite', 'delete']:
            self.assertEqual(self.client.get(f'/snippets/{self.snippet.pk}/{action}/').status_code, 405)
        self.client.post(f'/snippets/{self.snippet.pk}/favorite/')
        self.assertContains(self.client.get('/?view=favorites'), 'HTTP retry')
        self.client.post(f'/snippets/{self.snippet.pk}/delete/')
        self.assertFalse(Snippet.objects.filter(pk=self.snippet.pk).exists())

    def test_html_escaped(self):
        self.snippet.code = '</textarea><script>alert(1)</script>'
        self.snippet.save()
        response = self.client.get('/')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for path in ['/new/', f'/snippets/{self.snippet.pk}/delete/', f'/snippets/{self.snippet.pk}/favorite/', '/logout/']:
            self.assertEqual(client.post(path, {}).status_code, 403)

    def test_pagination(self):
        Snippet.objects.bulk_create([Snippet(owner=self.user, title=f'Item {i}', code='x') for i in range(15)])
        response = self.client.get('/')
        self.assertEqual(len(response.context['page']), 12)
        self.assertEqual(len(self.client.get('/?page=2').context['page']), 4)

    def test_register_login_logout(self):
        self.client.logout()
        response = self.client.post('/register/', {'username': 'newuser', 'password1': 'Strong-Password-7429!', 'password2': 'Strong-Password-7429!'})
        self.assertRedirects(response, '/login/')
        self.assertRedirects(self.client.post('/login/', {'username': 'newuser', 'password': 'Strong-Password-7429!'}), '/')
        self.assertRedirects(self.client.post('/logout/'), '/login/')

    def test_pwa_and_security_headers(self):
        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/javascript', response['Content-Type'])
        self.assertIn("script-src 'self'", response['Content-Security-Policy'])
        self.assertEqual(self.client.get('/health/').json(), {'status': 'ok'})

@override_settings(AXES_ENABLED=True, AXES_FAILURE_LIMIT=3)
class LoginProtectionTests(TestCase):
    def test_lockout(self):
        get_user_model().objects.create_user('locked', password='Strong-password-992!')
        for _ in range(3):
            response = self.client.post('/login/', {'username': 'locked', 'password': 'wrong'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.client.post('/login/', {'username': 'locked', 'password': 'Strong-password-992!'}).status_code, 429)
