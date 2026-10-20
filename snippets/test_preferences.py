import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import translation

from .models import Snippet, UserPreference


@override_settings(AXES_ENABLED=False, SEARCH_SEMANTIC_ENABLED=False)
class LanguagePreferenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('language-user')
        self.other = get_user_model().objects.create_user('another-user')

    def tearDown(self):
        translation.deactivate()

    def test_english_is_default_even_for_a_russian_browser(self):
        response = self.client.get('/login/', HTTP_ACCEPT_LANGUAGE='ru-RU,ru;q=0.9')
        self.assertContains(response, '<html lang="en"')
        self.assertContains(response, 'Log in')
        self.assertContains(response, 'Username:')
        self.assertEqual(response['Content-Language'], 'en')
        self.assertContains(response, '/settings/')

    def test_guest_can_select_russian_before_logging_in(self):
        response = self.client.post('/settings/', {'language': 'ru'})
        self.assertRedirects(response, '/settings/')
        cookie = response.cookies[settings.LANGUAGE_COOKIE_NAME]
        self.assertEqual(cookie.value, 'ru')
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertFalse(UserPreference.objects.exists())
        response = self.client.get('/login/')
        with translation.override('ru'):
            self.assertContains(response, translation.gettext('Log in'))
            self.assertContains(response, translation.gettext('Username'))
        self.assertContains(response, '<html lang="ru"')
        self.assertContains(response, 'manifest.ru.')
        self.assertEqual(response['Content-Language'], 'ru')

    def test_account_language_is_available_on_another_device(self):
        self.client.force_login(self.user)
        self.client.post('/settings/', {'language': 'ru'})
        self.assertEqual(UserPreference.objects.get(user=self.user).language, 'ru')
        second_device = Client()
        second_device.force_login(self.user)
        response = second_device.get('/')
        self.assertContains(response, '<html lang="ru"')
        with translation.override('ru'):
            self.assertContains(response, translation.gettext('All snippets'))
        second_device.force_login(self.other)
        self.assertContains(second_device.get('/'), '<html lang="en"')

    def test_account_preference_takes_priority_over_an_old_cookie(self):
        UserPreference.objects.create(user=self.user, language='en')
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'ru'
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/'), '<html lang="en"')

    def test_switch_back_to_english_and_preserve_snippet_contents(self):
        snippet = Snippet.objects.create(owner=self.user, title='Original title', code='\n    print("hello")\n')
        self.client.force_login(self.user)
        self.client.post('/settings/', {'language': 'ru'})
        response = self.client.post('/settings/', {'language': 'en'}, follow=True)
        self.assertContains(response, 'Settings saved.')
        self.assertContains(response, '<html lang="en"')
        self.assertEqual(UserPreference.objects.get(user=self.user).language, 'en')
        snippet.refresh_from_db()
        self.assertEqual(snippet.title, 'Original title')
        self.assertEqual(snippet.code, '\n    print("hello")\n')

    def test_invalid_language_does_not_change_the_account(self):
        UserPreference.objects.create(user=self.user, language='ru')
        self.client.force_login(self.user)
        response = self.client.post('/settings/', {'language': '../../unsupported'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(UserPreference.objects.get(user=self.user).language, 'ru')
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, response.cookies)

    def test_preferences_cannot_be_changed_for_another_user(self):
        UserPreference.objects.create(user=self.other, language='en')
        self.client.force_login(self.user)
        self.client.post('/settings/', {'language': 'ru', 'user_id': self.other.pk})
        self.assertEqual(UserPreference.objects.get(user=self.other).language, 'en')
        self.assertEqual(UserPreference.objects.get(user=self.user).language, 'ru')

    def test_settings_changes_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/settings/', {'language': 'ru'}).status_code, 403)
        self.assertEqual(client.get('/settings/').status_code, 200)
        response = client.post('/settings/', {'language': 'ru', 'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302)

    def test_invalid_cookie_falls_back_to_english(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'unknown'
        self.assertEqual(self.client.get('/login/')['Content-Language'], 'en')

    def test_forms_errors_notifications_and_copy_text_are_translated(self):
        self.client.force_login(self.user)
        self.client.post('/settings/', {'language': 'ru'})
        with translation.override('ru'):
            response = self.client.get('/new/')
            for source in ['Title', 'Description', 'Code', 'Tags', 'Code copied']:
                self.assertContains(response, translation.gettext(source))
            response = self.client.post('/new/', {'title': 'Invalid tags', 'code': 'x', 'language': 'python', 'tag_names': 'x' * 33})
            self.assertContains(response, translation.gettext('Use up to 10 tags, each at most 32 characters long.'))
            response = self.client.post('/new/', {'title': 'Valid', 'code': 'x', 'language': 'python'}, follow=True)
            self.assertContains(response, translation.gettext('Snippet saved.'))
        self.client.post('/settings/', {'language': 'en'})
        self.assertContains(self.client.get('/new/'), 'What is this snippet useful for?')

    def test_pwa_translation_assets_match_the_catalog(self):
        public = Path(settings.BASE_DIR) / 'static'
        english = json.loads((public / 'manifest.webmanifest').read_text())
        russian = json.loads((public / 'manifest.ru.webmanifest').read_text())
        self.assertEqual(english['lang'], 'en')
        self.assertEqual(russian['lang'], 'ru')
        messages = json.loads((public / 'i18n/ru.json').read_text())
        with translation.override('ru'):
            for source, text in messages.items():
                self.assertEqual(translation.gettext(source), text)
        worker = (public / 'sw.js').read_text()
        self.assertIn('/static/i18n/ru.json', worker)
        self.assertIn('/static/offline.js', worker)
