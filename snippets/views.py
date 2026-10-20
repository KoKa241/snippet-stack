from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.conf import settings
from .forms import SnippetForm
from .models import Snippet, LANGUAGES

def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Аккаунт создан. Войдите в свой стек.')
        return redirect('login')
    return render(request, 'registration/register.html', {'form': form})

@login_required
def home(request):
    base = Snippet.objects.filter(owner=request.user)
    snippets = base.prefetch_related('tags')
    q = request.GET.get('q', '')[:200].strip()
    language = request.GET.get('language', '')
    tag = request.GET.get('tag', '')
    mode = request.GET.get('view', '')
    if q:
        snippets = snippets.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(code__icontains=q) | Q(tags__name__icontains=q)).distinct()
    if language:
        snippets = snippets.filter(language=language)
    if tag:
        snippets = snippets.filter(tags__name=tag)
    if mode == 'favorites':
        snippets = snippets.filter(favorite=True)
    if mode == 'terminal':
        snippets = snippets.filter(language='shell')
    sort = request.GET.get('sort', 'updated')
    snippets = snippets.order_by('title', 'pk') if sort == 'title' else snippets.order_by('-updated_at', '-pk')
    page = Paginator(snippets, 12).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'home.html', {'page': page, 'q': q, 'language': language, 'tag': tag, 'mode': mode, 'sort': sort, 'languages': LANGUAGES, 'query': params.urlencode()})

@login_required
def edit(request, pk=None):
    snippet = get_object_or_404(Snippet, pk=pk, owner=request.user) if pk else None
    form = SnippetForm(request.POST or None, instance=snippet, initial={'tag_names': ', '.join(snippet.tags.values_list('name', flat=True)) if snippet else ''})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save_for(request.user)
        messages.success(request, 'Сниппет сохранён.')
        return redirect('home')
    return render(request, 'edit.html', {'form': form, 'snippet': snippet})

@login_required
@require_POST
def delete(request, pk):
    get_object_or_404(Snippet, pk=pk, owner=request.user).delete()
    messages.success(request, 'Сниппет удалён.')
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
