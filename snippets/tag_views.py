from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.utils.translation import gettext as _

from .models import Tag
from .tag_colors import valid_color, foreground


@login_required
@require_POST
def create(request):
    name = request.POST.get('name', '').strip().lower()
    if not name or len(name) > 32 or ',' in name or any(ord(char) < 32 for char in name):
        return JsonResponse({'error': _('Use a tag name of 1–32 characters without commas.')}, status=400)
    tag, created = Tag.objects.get_or_create(owner=request.user, name=name)
    return JsonResponse({'id': tag.pk, 'name': tag.name, 'color': tag.color}, status=201 if created else 200)


@login_required
@require_POST
def color(request, pk):
    tag = get_object_or_404(Tag, owner=request.user, pk=pk)
    value = request.POST.get('color', '')
    if not valid_color(value):
        return JsonResponse({'error': _('Enter a color in #RRGGBB format.')}, status=400)
    tag.color = value.lower()
    # Color does not change the searchable content of a tag.
    Tag.objects.filter(pk=tag.pk).update(color=tag.color)
    return JsonResponse({'id': tag.pk, 'name': tag.name, 'color': tag.color})


@login_required
@require_GET
def stylesheet(request):
    rules = []
    for tag in Tag.objects.filter(owner=request.user).only('id', 'color'):
        if valid_color(tag.color):
            rules.append(f'.tag-color-{tag.pk}, .card-tags a.tag-color-{tag.pk} {{ background-color: {tag.color}; color: {foreground(tag.color)}; }}')
    return HttpResponse('\n'.join(rules), content_type='text/css')
