from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.utils import timezone

from .api import issue_key
from .models import APIKey, Snippet, Tag


@override_settings(AXES_ENABLED=False, SEARCH_SEMANTIC_ENABLED=False)
class APITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('api-user')
        self.other = get_user_model().objects.create_user('other-user')
        self.snippet = Snippet.objects.create(owner=self.user, title='Free port', code='lsof -ti:8080', language='shell')
        self.private = Snippet.objects.create(owner=self.other, title='Other private snippet', code='secret')
        self.key, self.token = issue_key(self.user, 'Terminal', 90)
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}

    def test_key_storage_and_read(self):
        self.assertNotEqual(self.key.digest, self.token)
        self.assertNotIn(self.token, str(APIKey.objects.values().get(pk=self.key.pk)))
        response = self.client.get('/api/v1/snippets/', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['code'], self.snippet.code)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.last_used_at)

    def test_session_login_cannot_replace_bearer_authentication(self):
        self.client.force_login(self.user)
        for header in ['', 'Bearer invalid', self.token, 'Basic abc']:
            response = self.client.get('/api/v1/snippets/', HTTP_AUTHORIZATION=header)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()['error']['code'], 'unauthorized')
        self.assertEqual(self.client.get('/api/v1/snippets/', {'api_key': self.token}).status_code, 401)

    def test_bearer_owner_wins_over_browser_session(self):
        self.client.force_login(self.other)
        result = self.client.get('/api/v1/snippets/', **self.headers).json()
        self.assertEqual([s['id'] for s in result['results']], [self.snippet.pk])
        self.assertEqual(self.client.get(f'/api/v1/snippets/{self.private.pk}/', **self.headers).status_code, 404)
        self.assertEqual(self.client.get(f'/api/v1/snippets/{self.snippet.pk}/', **self.headers).status_code, 200)

    def test_revoked_expired_and_inactive_user_keys_are_rejected(self):
        APIKey.objects.filter(pk=self.key.pk).update(revoked_at=timezone.now())
        self.assertEqual(self.client.get('/api/v1/snippets/', **self.headers).status_code, 401)
        APIKey.objects.filter(pk=self.key.pk).update(revoked_at=None, expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get('/api/v1/snippets/', **self.headers).status_code, 401)
        APIKey.objects.filter(pk=self.key.pk).update(expires_at=timezone.now() + timedelta(days=1))
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get('/api/v1/snippets/', **self.headers).status_code, 401)

    def test_search_filters_and_pagination(self):
        tag = Tag.objects.create(owner=self.user, name='network')
        self.snippet.tags.add(tag)
        Snippet.objects.create(owner=self.user, title='Python', code='print(8080)', language='python', favorite=True)
        response = self.client.get('/api/v1/snippets/', {'q': '8080', 'language': 'shell', 'tag': 'network'}, **self.headers)
        self.assertEqual([s['id'] for s in response.json()['results']], [self.snippet.pk])
        self.assertEqual(self.client.get('/api/v1/snippets/', {'favorite': 'true'}, **self.headers).json()['count'], 1)
        response = self.client.get('/api/v1/snippets/', {'page_size': 1}, **self.headers).json()
        self.assertEqual(response['next_page'], 2)
        self.assertEqual(response['count'], 2)
        self.assertEqual(self.client.get('/api/v1/snippets/', {'page': 99}, **self.headers).status_code, 404)

    def test_invalid_parameters_are_bounded(self):
        for params in [{'q': 'a'*201}, {'page_size': 51}, {'page_size': 0}, {'page': -1}, {'language': 'invalid'}, {'favorite': 'maybe'}, {'sort': 'random'}]:
            response = self.client.get('/api/v1/snippets/', params, **self.headers)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()['error']['code'], 'invalid_parameters')

    @override_settings(API_RATE_LIMIT=2)
    def test_shared_database_rate_limit_and_reset(self):
        self.assertEqual(self.client.get('/api/v1/snippets/', **self.headers).status_code, 200)
        other_client = Client()
        self.assertEqual(other_client.get('/api/v1/snippets/', **self.headers).status_code, 200)
        response = other_client.get('/api/v1/snippets/', **self.headers)
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response)
        APIKey.objects.filter(pk=self.key.pk).update(window_started_at=timezone.now()-timedelta(seconds=61))
        self.assertEqual(self.client.get('/api/v1/snippets/', **self.headers).status_code, 200)

    def test_api_is_read_only_even_without_a_csrf_cookie(self):
        client = Client(enforce_csrf_checks=True)
        for method in ['post', 'put', 'patch', 'delete']:
            response = getattr(client, method)(f'/api/v1/snippets/{self.snippet.pk}/', **self.headers)
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response.json()['error']['code'], 'method_not_allowed')
        self.assertTrue(Snippet.objects.filter(pk=self.snippet.pk).exists())

    def test_web_key_creation_shows_secret_only_once(self):
        self.client.force_login(self.user)
        response = self.client.post('/settings/api-keys/create/', {'name': 'Editor', 'lifetime': 30})
        self.assertEqual(response.status_code, 200)
        token = response.context['new_api_key']
        self.assertTrue(token.startswith('ss_'))
        self.assertContains(response, token)
        self.assertNotContains(self.client.get('/settings/'), token)
        key = APIKey.objects.get(name='Editor')
        self.assertEqual(key.owner, self.user)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_key_management_requires_session_csrf_and_ownership(self):
        self.assertEqual(self.client.post('/settings/api-keys/create/', {'name': 'X', 'lifetime': 30}).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post('/settings/api-keys/create/', {'name': 'X', 'lifetime': 30}).status_code, 403)
        self.assertEqual(client.post(f'/settings/api-keys/{self.key.pk}/revoke/').status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(f'/settings/api-keys/{self.key.pk}/revoke/').status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(f'/settings/api-keys/{self.key.pk}/revoke/').status_code, 302)
        self.assertEqual(self.client.get('/api/v1/snippets/', **self.headers).status_code, 401)

    def test_active_key_limit_and_invalid_lifetime(self):
        self.client.force_login(self.user)
        response = self.client.post('/settings/api-keys/create/', {'name': 'Bad', 'lifetime': 99999})
        self.assertTrue(response.context['key_form'].errors)
        for i in range(9):
            issue_key(self.user, f'Key {i}', 30)
        response = self.client.post('/settings/api-keys/create/', {'name': 'Extra', 'lifetime': 30})
        self.assertTrue(response.context['key_form'].errors)
        self.assertEqual(APIKey.objects.filter(owner=self.user).count(), 10)
