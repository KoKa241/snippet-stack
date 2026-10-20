import os
from pathlib import Path
from datetime import timedelta
from django.utils.translation import gettext_lazy as _
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.environ['SECRET_KEY']
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',')
CSRF_TRUSTED_ORIGINS = list(filter(None, os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',')))
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'axes', 'snippets']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'snippets.middleware.LanguageMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware', 'axes.middleware.AxesMiddleware', 'snippets.middleware.HeadersMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages', 'snippets.context_processors.library']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATA_DIR = Path(os.getenv('DATA_DIR', BASE_DIR / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': DATA_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.' + name} for name in ['UserAttributeSimilarityValidator', 'MinimumLengthValidator', 'CommonPasswordValidator', 'NumericPasswordValidator']]
AUTHENTICATION_BACKENDS = ['axes.backends.AxesStandaloneBackend', 'django.contrib.auth.backends.ModelBackend']
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ['ip_address']
AXES_RESET_ON_SUCCESS = True
LANGUAGE_CODE = 'en'
LANGUAGES = [('en', _('English')), ('ru', _('Russian'))]
LOCALE_PATHS = [BASE_DIR / 'locale']
USE_I18N = True
LANGUAGE_COOKIE_NAME = 'snippet_language'
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = 'Lax'
TIME_ZONE = 'UTC'
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
SECURE_SSL_REDIRECT = os.getenv('HTTPS', 'false').lower() == 'true'
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SECURE_HSTS_SECONDS = 31536000 if SECURE_SSL_REDIRECT else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL_REDIRECT
SECURE_HSTS_PRELOAD = SECURE_SSL_REDIRECT
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 262144

# Enable only behind a trusted proxy that overwrites X-Forwarded-Proto.
if os.getenv('TRUST_PROXY', 'false').lower() == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_REDIRECT_EXEMPT = [r'^health/$']

# Local CPU semantic search. Model downloads are only performed by index_search.
SEARCH_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
SEARCH_MODEL_CACHE = os.getenv('SEARCH_MODEL_CACHE', str(DATA_DIR / 'models'))
SEARCH_SEMANTIC_ENABLED = os.getenv('SEARCH_SEMANTIC_ENABLED', 'true').lower() == 'true'
SEARCH_THREADS = int(os.getenv('SEARCH_THREADS', '2'))
SEARCH_CANDIDATES = 100
SEARCH_MIN_SIMILARITY = float(os.getenv('SEARCH_MIN_SIMILARITY', '0.25'))

# Shared database-backed fixed window: requests per key per 60 seconds.
API_RATE_LIMIT = 60
