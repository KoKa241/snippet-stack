from django import forms
from .models import Snippet, Tag

class SnippetForm(forms.ModelForm):
    code = forms.CharField(label="Код", strip=False, max_length=100000, widget=forms.Textarea(attrs={"spellcheck": "false", "rows": 16, "placeholder": "# Ваш следующий полезный сниппет"}))
    tag_names = forms.CharField(label='Теги', required=False, max_length=328, help_text='До 10 тегов через запятую', widget=forms.TextInput(attrs={'placeholder': 'python, api, utilities'}))
    class Meta:
        model = Snippet
        fields = ['title', 'description', 'language', 'code', 'tag_names']
        labels = {'title': 'Название', 'description': 'Описание', 'language': 'Язык', 'code': 'Код'}
        widgets = {'code': forms.Textarea(attrs={'spellcheck': 'false', 'rows': 16, 'placeholder': '# Ваш следующий полезный сниппет'}), 'description': forms.TextInput(attrs={'placeholder': 'Для чего пригодится этот сниппет?'}), 'title': forms.TextInput(attrs={'placeholder': 'Например, HTTP-запрос с повторными попытками'})}
    def clean_tag_names(self):
        names = sorted(set(n.strip().lower() for n in self.cleaned_data['tag_names'].split(',') if n.strip()))
        if len(names) > 10 or any(len(n) > 32 for n in names):
            raise forms.ValidationError('Не больше 10 тегов, каждый до 32 символов.')
        return names
    def save_for(self, user):
        snippet = super().save(commit=False)
        snippet.owner = user
        snippet.save()
        snippet.tags.set([Tag.objects.get_or_create(owner=user, name=name)[0] for name in self.cleaned_data['tag_names']])
        return snippet
