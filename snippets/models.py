from django.conf import settings
from django.db import models
from django.core.validators import RegexValidator
from .tag_colors import random_color
from django.utils.translation import gettext_lazy as _

LANGUAGES = [
    ('python', 'Python'), ('shell', _('Terminal')), ('powershell', 'PowerShell'),
    ('javascript', 'JavaScript'), ('typescript', 'TypeScript'),
    ('jsx', 'JSX / React'), ('tsx', 'TSX / React'),
    ('c', 'C'), ('cpp', 'C++'), ('csharp', 'C#'), ('java', 'Java'),
    ('go', 'Go'), ('rust', 'Rust'), ('php', 'PHP'), ('ruby', 'Ruby'),
    ('swift', 'Swift'), ('kotlin', 'Kotlin'), ('dart', 'Dart'), ('lua', 'Lua'), ('r', 'R'),
    ('sql', 'SQL'), ('html', 'HTML'), ('css', 'CSS'), ('scss', 'SCSS'),
    ('json', 'JSON'), ('yaml', 'YAML'), ('toml', 'TOML'), ('xml', 'XML'),
    ('markdown', 'Markdown'), ('docker', 'Dockerfile'), ('nginx', 'Nginx'),
    ('other', _('Plain text')),
]

COMMAND_LANGUAGES = ('shell', 'powershell')

class Tag(models.Model):
    color = models.CharField(max_length=7, default=random_color, validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$")])
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=32)
    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['owner', 'name'], name='unique_owner_tag')]
    def __str__(self):
        return self.name

class Snippet(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    code = models.TextField(max_length=100000)
    language = models.CharField(max_length=16, choices=LANGUAGES, default='python')
    favorite = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-updated_at', '-pk']
        indexes = [models.Index(fields=['owner', '-updated_at']), models.Index(fields=['owner', 'language'])]


class SearchDocument(models.Model):
    """Derived search data; safe to rebuild from Snippet and its tags."""
    snippet = models.OneToOneField(Snippet, on_delete=models.CASCADE, primary_key=True)
    title = models.TextField()
    description = models.TextField()
    code = models.TextField()
    tags = models.TextField()
    content_hash = models.CharField(max_length=64)
    embedding = models.BinaryField(null=True, editable=False)
    embedding_model = models.CharField(max_length=200, blank=True)


class UserPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True)
    language = models.CharField(max_length=2, choices=settings.LANGUAGES, default='en')


class APIKey(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=60)
    prefix = models.CharField(max_length=11)
    digest = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    window_started_at = models.DateTimeField(null=True, editable=False)
    window_requests = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_active(self):
        from django.utils import timezone
        return self.revoked_at is None and self.expires_at > timezone.now()
