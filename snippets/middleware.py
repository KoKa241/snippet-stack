from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils import translation
from django.utils.cache import patch_vary_headers


class LanguageMiddleware(LocaleMiddleware):
    """Prefer explicit settings; English is the default regardless of browser locale."""

    def process_request(self, request):
        from .models import UserPreference
        language = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME, settings.LANGUAGE_CODE)
        if request.user.is_authenticated:
            saved = UserPreference.objects.filter(user_id=request.user.pk).values_list('language', flat=True).first()
            if saved:
                language = saved
        if language not in dict(settings.LANGUAGES):
            language = settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = language

    def process_response(self, request, response):
        response = super().process_response(request, response)
        patch_vary_headers(response, ('Cookie',))
        return response


class HeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        response['Referrer-Policy'] = 'same-origin'
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if not request.path.startswith('/static/'):
            response['Cache-Control'] = 'no-store'
        return response
