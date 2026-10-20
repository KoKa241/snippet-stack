"""Generate public PWA translations from the same catalog as the online UI."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import translation
from django.utils.translation import gettext, gettext_noop


OFFLINE_MESSAGES = (
    gettext_noop('You are offline'),
    gettext_noop('Connect to the server to access your private snippets. Your data is saved.'),
    gettext_noop('Try again'),
    gettext_noop('Offline · Snippet Stack'),
)
APP_DESCRIPTION = gettext_noop('Your personal collection of code and commands')


class Command(BaseCommand):
    help = 'Generate Russian offline strings and the PWA manifest from the compiled catalog.'

    def handle(self, *args, **options):
        public = Path(settings.BASE_DIR) / 'static'
        with translation.override('ru'):
            messages = {source: gettext(source) for source in OFFLINE_MESSAGES}
            manifest = json.loads((public / 'manifest.webmanifest').read_text())
            manifest.update(lang='ru', description=gettext(APP_DESCRIPTION))
        (public / 'i18n').mkdir(exist_ok=True)
        (public / 'i18n/ru.json').write_text(json.dumps(messages, ensure_ascii=False, indent=2) + '\n')
        (public / 'manifest.ru.webmanifest').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        self.stdout.write('Generated public Russian translation assets.')
