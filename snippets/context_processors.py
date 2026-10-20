from django.db.models import Count, Q
from .models import Snippet, Tag


def library(request):
    if not request.user.is_authenticated:
        return {}
    counts = Snippet.objects.filter(owner=request.user).aggregate(total=Count('pk'), favorites=Count('pk', filter=Q(favorite=True)), terminals=Count('pk', filter=Q(language='shell')))
    counts['tags'] = Tag.objects.filter(owner=request.user, snippet__isnull=False).annotate(total=Count('snippet'))
    return counts
