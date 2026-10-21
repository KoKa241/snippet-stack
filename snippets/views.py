from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import translation
from django.utils.translation import gettext as _
from django.conf import settings
from .forms import SnippetForm, PreferencesForm, APIKeyForm, ExportForm, ImportForm
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from .models import Snippet, LANGUAGES, COMMAND_LANGUAGES, UserPreference, APIKey, Tag
from .selectors import select_snippets
from .api import issue_key
from django.utils import timezone

@sensitive_post_parameters('password1', 'password2')
@require_http_methods(['GET', 'POST'])
def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = UserCreationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, _('Account created. Log in to your stack.'))
        return redirect('login')
    return render(request, 'registration/register.html', {'form': form})

@login_required
def home(request):
    q = request.GET.get('q', '')[:200].strip()
    language = request.GET.get('language', '')
    tag = request.GET.get('tag', '')
    mode = request.GET.get('view', '')
    sort = request.GET.get('sort', 'relevance')
    if sort not in {'relevance', 'updated', 'title'}:
        sort = 'relevance'
    snippets, search_status = select_snippets(
        request.user.pk, q=q, language=language, commands_only=mode == 'terminal',
        tag=tag, favorite=True if mode == 'favorites' else None, sort=sort,
    )
    page = Paginator(snippets, 12).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'home.html', {'page': page, 'q': q, 'language': language, 'tag': tag, 'mode': mode, 'sort': sort, 'languages': [(value, label) for value, label in LANGUAGES if value in COMMAND_LANGUAGES] if mode == 'terminal' else LANGUAGES, 'query': params.urlencode(), 'search_status': search_status})

@login_required
@require_http_methods(['GET', 'POST'])
def edit(request, pk=None):
    snippet = get_object_or_404(Snippet, pk=pk, owner=request.user) if pk else None
    form = SnippetForm(request.POST if request.method == 'POST' else None, instance=snippet, initial={'tag_names': ', '.join(snippet.tags.values_list('name', flat=True)) if snippet else ''})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save_for(request.user)
        messages.success(request, _('Snippet saved.'))
        return redirect('home')
    return render(request, 'edit.html', {'form': form, 'snippet': snippet, 'available_tags': list(Tag.objects.filter(owner=request.user).values('id', 'name', 'color'))})

@login_required
@require_POST
def delete(request, pk):
    get_object_or_404(Snippet, pk=pk, owner=request.user).delete()
    messages.success(request, _('Snippet deleted.'))
    return redirect('home')

@login_required
@require_POST
def favorite(request, pk):
    with transaction.atomic():
        snippet = get_object_or_404(Snippet, pk=pk, owner=request.user)
        snippet.favorite = not snippet.favorite
        snippet.save(update_fields=['favorite'])
    return redirect('home')

def service_worker(request):
    return FileResponse(open(settings.BASE_DIR / 'static/sw.js', 'rb'), content_type='application/javascript')

def health(request):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'status': 'ok'})


@require_http_methods(['GET', 'POST'])
def preferences(request):
    form = PreferencesForm(request.POST if request.method == 'POST' else None,
                           initial={'language': request.LANGUAGE_CODE})
    if request.method == 'POST' and form.is_valid():
        language = form.cleaned_data['language']
        if request.user.is_authenticated:
            UserPreference.objects.update_or_create(user=request.user, defaults={'language': language})
        translation.activate(language)
        request.LANGUAGE_CODE = language
        messages.success(request, _('Settings saved.'))
        response = redirect('settings')
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME, language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            secure=settings.SESSION_COOKIE_SECURE,
            httponly=True, samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )
        return response
    return render(request, 'settings.html', preferences_context(request, form=form))


def preferences_context(request, **extra):
    context = {
        'form': PreferencesForm(initial={'language': request.LANGUAGE_CODE}),
        'key_form': APIKeyForm(),
        'export_form': ExportForm(prefix='export'),
        'import_form': ImportForm(prefix='import'),
        'api_keys': APIKey.objects.filter(owner=request.user) if request.user.is_authenticated else [],
    }
    context.update(extra)
    return context


@login_required
@require_POST
def create_api_key(request):
    form = APIKeyForm(request.POST)
    token = None
    if form.is_valid():
        with transaction.atomic():
            active = APIKey.objects.filter(owner=request.user, revoked_at__isnull=True,
                                           expires_at__gt=timezone.now()).count()
            if active >= 10:
                form.add_error(None, _('You can have up to 10 active keys. Revoke a key before creating another.'))
            else:
                created_key, token = issue_key(request.user, form.cleaned_data['name'], form.cleaned_data['lifetime'])
    response = render(request, 'settings.html', preferences_context(request, key_form=form, new_api_key=token))
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@require_POST
def revoke_api_key(request, pk):
    key = get_object_or_404(APIKey, pk=pk, owner=request.user)
    if key.revoked_at is None:
        key.revoked_at = timezone.now()
        key.save(update_fields=['revoked_at'])
    messages.success(request, _('API key revoked.'))
    return redirect('settings')


@login_required
@require_POST
@sensitive_variables()
@sensitive_post_parameters('export-password', 'export-confirm_password')
def export_data(request):
    from .backups import export_archive, BackupError
    form = ExportForm(request.POST, prefix='export')
    if form.is_valid():
        try:
            archive = export_archive(request.user, form.cleaned_data['password'])
        except BackupError:
            form.add_error(None, _('Export supports up to 2,000 snippets and a 10 MiB archive.'))
        else:
            response = HttpResponse(archive, content_type='application/octet-stream')
            response['Content-Disposition'] = 'attachment; filename="snippet-stack.ssbackup"'
            response['Cache-Control'] = 'no-store'
            return response
    return render(request, 'settings.html', preferences_context(request, export_form=form), status=400)


@login_required
@require_POST
@sensitive_variables()
@sensitive_post_parameters('import-password')
def import_data(request):
    from .backups import import_archive, BackupError, MAX_BYTES
    form = ImportForm(request.POST, request.FILES, prefix='import')
    if form.is_valid():
        try:
            created, skipped = import_archive(request.user, form.cleaned_data['archive'].read(MAX_BYTES + 1), form.cleaned_data['password'])
        except BackupError:
            form.add_error(None, _('Cannot import this archive. Check the password and use a valid Snippet Stack backup. No data was changed.'))
        else:
            messages.success(request, _('Import complete: %(created)s added, %(skipped)s duplicates skipped.') % {'created': created, 'skipped': skipped})
            return redirect('settings')
    return render(request, 'settings.html', preferences_context(request, import_form=form), status=400)
