from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from .models import Tag
from .tag_colors import PALETTE, foreground


@override_settings(AXES_ENABLED=False, SEARCH_SEMANTIC_ENABLED=False)
class TagTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tags-user')
        self.other = get_user_model().objects.create_user('other-tags-user')
        self.private = Tag.objects.create(owner=self.other, name='private-tag', color='#123456')
        self.client.force_login(self.user)

    def test_create_normalizes_names_and_reuses_existing_tag(self):
        first = self.client.post('/tags/', {'name': ' Python '})
        self.assertEqual(first.status_code, 201)
        self.assertIn(first.json()['color'], PALETTE)
        again = self.client.post('/tags/', {'name': 'python'})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(first.json(), again.json())
        for name in ['', 'a,b', 'x'*33, 'a\x00b', 'a\nb']:
            self.assertEqual(self.client.post('/tags/', {'name': name}).status_code, 400)

    def test_color_requires_ownership_and_valid_hex(self):
        tag = Tag.objects.create(owner=self.user, name='python')
        url = f'/tags/{tag.pk}/color/'
        self.assertEqual(self.client.post(f'/tags/{self.private.pk}/color/', {'color': '#ffffff'}).status_code, 404)
        self.assertEqual(self.client.post(url, {'color': '#ABCDEF'}).json()['color'], '#abcdef')
        for color in ['red', '#12345', '#123456;}', 'url(https://example.com)', '#123456\n']:
            self.assertEqual(self.client.post(url, {'color': color}).status_code, 400)
        tag.refresh_from_db()
        self.assertEqual(tag.color, '#abcdef')

    def test_dropdown_and_stylesheet_do_not_leak_other_users_tags(self):
        tag = Tag.objects.create(owner=self.user, name='own-tag', color='#abcdef')
        editor = self.client.get('/new/')
        self.assertEqual(list(editor.context['available_tags']), [{'id': tag.pk, 'name': tag.name, 'color': tag.color}])
        self.assertNotContains(editor, 'private-tag')
        css = self.client.get('/tags/colors.css')
        self.assertContains(css, f'.tag-color-{tag.pk}')
        self.assertNotContains(css, f'.tag-color-{self.private.pk}')
        self.assertEqual(css['Cache-Control'], 'no-store')
        self.assertEqual(foreground('#ffffff'), '#000000')
        self.assertEqual(foreground('#000000'), '#ffffff')

    def test_mutations_require_post_session_and_csrf(self):
        tag = Tag.objects.create(owner=self.user, name='owned')
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        for url in ['/tags/', f'/tags/{tag.pk}/color/']:
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(strict.post(url, {'name': 'x', 'color': '#ffffff'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post('/tags/', {'name': 'x'}).status_code, 302)

    def test_editor_still_saves_without_javascript(self):
        response = self.client.post('/new/', {'title': 'Example', 'description': '', 'language': 'python', 'code': 'print(1)', 'tag_names': 'python, example'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Tag.objects.filter(owner=self.user).count(), 2)
        self.assertTrue(all(tag.color in PALETTE for tag in Tag.objects.filter(owner=self.user)))
        editor = self.client.get('/new/')
        self.assertNotContains(editor, 'Your next useful snippet')
        self.assertNotContains(editor, 'SAVE IT FOR LATER')
        self.assertContains(editor, '# Enter code...')
