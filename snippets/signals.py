from django.db.models.signals import m2m_changed, post_save, post_delete, pre_delete
from django.dispatch import receiver
from .models import Snippet, Tag
from .search_index import sync_document


@receiver(post_save, sender=Snippet)
def snippet_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        sync_document(instance)


@receiver(m2m_changed, sender=Snippet.tags.through)
def tags_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if reverse:
        if action == 'pre_clear':
            instance._search_snippet_ids = list(instance.snippet_set.values_list('pk', flat=True))
        if action in {'post_add', 'post_remove', 'post_clear'}:
            ids = getattr(instance, '_search_snippet_ids', []) if action == 'post_clear' else pk_set
            for snippet in Snippet.objects.filter(pk__in=ids):
                sync_document(snippet)
    elif action in {'post_add', 'post_remove', 'post_clear'}:
        sync_document(instance)


@receiver(post_save, sender=Tag)
def tag_renamed(sender, instance, raw=False, **kwargs):
    if not raw:
        for snippet in instance.snippet_set.all():
            sync_document(snippet)


@receiver(pre_delete, sender=Tag)
def tag_deleting(sender, instance, **kwargs):
    instance._search_snippet_ids = list(instance.snippet_set.values_list('pk', flat=True))


@receiver(post_delete, sender=Tag)
def tag_deleted(sender, instance, **kwargs):
    for snippet in Snippet.objects.filter(pk__in=getattr(instance, '_search_snippet_ids', [])):
        sync_document(snippet)
