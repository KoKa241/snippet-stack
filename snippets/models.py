from django.conf import settings
from django.db import models

LANGUAGES = [('python', 'Python'), ('shell', 'Terminal'), ('javascript', 'JavaScript'), ('typescript', 'TypeScript'), ('sql', 'SQL'), ('html', 'HTML'), ('css', 'CSS'), ('json', 'JSON'), ('yaml', 'YAML'), ('other', 'Plain text')]

class Tag(models.Model):
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
