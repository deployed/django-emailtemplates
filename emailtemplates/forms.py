# coding=utf-8
import logging

import os
from django import forms
from django.core.exceptions import ValidationError
from django.template import Context
from django.template import Engine
from django.template import Template
from django.template import TemplateSyntaxError
from django.template.loaders import app_directories
from django.utils.translation import ugettext_lazy as _

from .models import EmailTemplate

logger = logging.getLogger(__name__)


class TemplateSourceLoader(app_directories.Loader):
    def get_source(self, template_name):
        source, origin = self.load_template_source(template_name)
        return source


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
            engine = Engine.get_default()
            loader = TemplateSourceLoader(engine)
            try:
                self.fields['preview'].initial = loader.get_source(
                    os.path.join("emailtemplates", self.initial['title']))
            except Exception, e:
                logger.error('Load template error. Details: %s', e)

    def clean_content(self):
        content = self.cleaned_data['content']
        try:
            Template(content)
        except TemplateSyntaxError as e:
            raise ValidationError(u"Syntax error in custom email template: %s" % e)
        return content
