# coding=utf-8
import logging

import os
from django import forms
from django.template import loader, TemplateDoesNotExist
from django.utils.translation import ugettext_lazy as _

from .models import EmailTemplate

logger = logging.getLogger(__name__)


class EmailTemplateAdminForm(forms.ModelForm):
    preview = forms.CharField(required=False,
                              label=_(u'default template preview'),
                              help_text=_(u'Preview of the default template is available after selecting a template '
                                          u'and saving changes (Save and continue editing)'))

    class Meta:
        model = EmailTemplate
        fields = [
            'title',
            'subject',
            'content',
            'language',
            'created',
            'modified',
        ]

    def __init__(self, *args, **kwargs):
        super(EmailTemplateAdminForm, self).__init__(*args, **kwargs)
        self.fields['preview'].widget = forms.Textarea(attrs={'readonly': 'readonly', 'rows': 30, 'cols': 120})
        if self.initial:
            try:
                template = loader.get_template(os.path.join("emailtemplates", self.initial['title']))
            except TemplateDoesNotExist, e:
                logger.error('TemplateDoesNotExist. Details: %s', e)
            else:
                self.fields['preview'].initial = template.origin.reload()
