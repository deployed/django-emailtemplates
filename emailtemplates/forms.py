# coding=utf-8
import logging

from django import forms
from django.core.exceptions import ValidationError
from django.template import Template
from django.template import TemplateSyntaxError
from django.utils.safestring import mark_safe
from django.utils.functional import lazy

from emailtemplates.models import EmailTemplate, MassEmailAttachment, MassEmailMessage
from emailtemplates.registry import email_templates

logger = logging.getLogger(__name__)


class EmailTemplateAdminForm(forms.ModelForm):
    title = forms.ChoiceField(choices=lazy(email_templates.email_template_choices, list))

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
        self.fields['title'].help_text = mark_safe(email_templates.get_form_help_text(self.initial.get('title')))
        if self.instance.pk:
            self.fields['title'].widget = forms.TextInput(attrs={'readonly': 'readonly', 'style': 'width:480px'})
        else:
            self.fields['content'].widget = forms.HiddenInput()
            self.fields['content'].required = False
            self.fields['subject'].widget = forms.HiddenInput()

    def clean_content(self):
        content = self.cleaned_data['content']
        try:
            Template(content)
        except TemplateSyntaxError as e:
            raise ValidationError(u"Syntax error in custom email template: %s" % e)
        return content


class MassEmailAttachmentForm(forms.ModelForm):
    class Meta:
        model = MassEmailAttachment
        fields = ['attachment_file']


class MassEmailMessageForm(forms.ModelForm):
    class Meta:
        model = MassEmailMessage
        fields = [
            'subject',
            'content',
            'date_sent',
        ]
