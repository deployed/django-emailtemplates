# coding=utf-8
import os

from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from .models import EmailTemplate


class EmailTemplateAdminForm(forms.ModelForm):
    preview = forms.CharField(required=False,
                              label=_(u'default template preview'),
                              help_text=_(u'Preview of the default template is available after selecting a template '
                                          u'and saving changes (Save and continue editing)'))

    class Meta:
        model = EmailTemplate

    def __init__(self, *args, **kwargs):
        super(EmailTemplateAdminForm, self).__init__(*args, **kwargs)
        self.fields['preview'].widget = forms.Textarea(attrs={'readonly': 'readonly', 'rows': 30, 'cols': 120})
        if self.initial:
            path = os.path.join(settings.TEMPLATE_DIRS[0], "emailtemplates", self.initial['title'])
            self.fields['preview'].initial = open(path).read()
