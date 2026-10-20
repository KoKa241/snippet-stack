from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from .models import Snippet, Tag


class PreferencesForm(forms.Form):
    language = forms.ChoiceField(label=_('Interface language'), choices=settings.LANGUAGES)


class SnippetForm(forms.ModelForm):
    code = forms.CharField(
        label=_('Code'), strip=False, max_length=100000,
        widget=forms.Textarea(attrs={
            'spellcheck': 'false', 'rows': 16,
            'placeholder': _('# Your next useful snippet'),
        }),
    )
    tag_names = forms.CharField(
        label=_('Tags'), required=False, max_length=328,
        help_text=_('Up to 10 comma-separated tags'),
        widget=forms.TextInput(attrs={'placeholder': 'python, api, utilities'}),
    )

    class Meta:
        model = Snippet
        fields = ['title', 'description', 'language', 'code', 'tag_names']
        labels = {
            'title': _('Title'), 'description': _('Description'),
            'language': _('Language'), 'code': _('Code'),
        }
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': _('What is this snippet useful for?')}),
            'title': forms.TextInput(attrs={'placeholder': _('For example, an HTTP request with retries')}),
        }

    def clean_tag_names(self):
        names = sorted(set(n.strip().lower() for n in self.cleaned_data['tag_names'].split(',') if n.strip()))
        if len(names) > 10 or any(len(n) > 32 for n in names):
            raise forms.ValidationError(_('Use up to 10 tags, each at most 32 characters long.'))
        return names

    def save_for(self, user):
        snippet = super().save(commit=False)
        snippet.owner = user
        snippet.save()
        snippet.tags.set([Tag.objects.get_or_create(owner=user, name=name)[0] for name in self.cleaned_data['tag_names']])
        return snippet


class APIKeyForm(forms.Form):
    name = forms.CharField(label=_('Key name'), max_length=60,
                           widget=forms.TextInput(attrs={'placeholder': _('For example, terminal or editor')}))
    lifetime = forms.TypedChoiceField(label=_('Expires after'), coerce=int, initial=90,
                                     choices=[(30, _('30 days')), (90, _('90 days')), (365, _('1 year'))])


class APISearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=200)
    language = forms.ChoiceField(required=False, choices=[('', 'All'), *Snippet._meta.get_field('language').choices])
    tag = forms.CharField(required=False, max_length=32)
    favorite = forms.ChoiceField(required=False, choices=[('', 'All'), ('true', 'True'), ('false', 'False')])
    sort = forms.ChoiceField(required=False, choices=[('relevance', 'Relevance'), ('updated', 'Updated'), ('title', 'Title')])
    page = forms.IntegerField(required=False, min_value=1)
    page_size = forms.IntegerField(required=False, min_value=1, max_value=50)


class ExportForm(forms.Form):
    password = forms.CharField(label=_('Archive password'), min_length=12, max_length=256, strip=False,
                               widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    confirm_password = forms.CharField(label=_('Confirm archive password'), max_length=256, strip=False,
                                       widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password') != data.get('confirm_password'):
            self.add_error('confirm_password', _('Passwords do not match.'))
        return data


class ImportForm(forms.Form):
    archive = forms.FileField(label=_('Encrypted archive'), widget=forms.FileInput(attrs={'accept': '.ssbackup'}))
    password = forms.CharField(label=_('Archive password'), max_length=256, strip=False,
                               widget=forms.PasswordInput(attrs={'autocomplete': 'off'}))

    def clean_archive(self):
        from .backups import MAX_BYTES
        archive = self.cleaned_data['archive']
        if archive.size > MAX_BYTES:
            raise forms.ValidationError(_('The archive must not exceed 10 MiB.'))
        return archive
