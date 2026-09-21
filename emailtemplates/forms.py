# coding=utf-8
import logging

from django import forms
from django.core.exceptions import ValidationError
from django.template import Template
from django.template import TemplateSyntaxError
from django.utils.functional import lazy
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from emailtemplates.models import (
    EXTENDS_TAG_RE,
    EmailTemplate,
    MassEmailAttachment,
    MassEmailMessage,
)
from emailtemplates.registry import email_templates

logger = logging.getLogger(__name__)


class EmailTemplateAdminForm(forms.ModelForm):
    title = forms.ChoiceField(
        choices=lazy(email_templates.email_template_choices, list), label=_("template")
    )

    class Meta:
        model = EmailTemplate
        fields = [
            "title",
            "layout",
            "subject",
            "content",
            "language",
            "ordering",
            "created",
            "modified",
        ]

    def __init__(self, *args, **kwargs):
        super(EmailTemplateAdminForm, self).__init__(*args, **kwargs)
        self.fields["title"].help_text = mark_safe(
            email_templates.get_form_help_text(self.initial.get("title"))
        )
        if self.instance.pk:
            self.fields["title"].widget = forms.TextInput(
                attrs={"readonly": "readonly", "style": "width:480px"}
            )
        else:
            self.fields["content"].widget = forms.HiddenInput()
            self.fields["content"].required = False
            self.fields["subject"].widget = forms.HiddenInput()

    def clean_content(self):
        content = self.cleaned_data["content"]
        try:
            Template(content)
        except TemplateSyntaxError as e:
            raise ValidationError("Syntax error in custom email template: %s" % e)
        return content

    def clean(self):
        cleaned_data = super(EmailTemplateAdminForm, self).clean()
        layout = cleaned_data.get("layout")
        if not layout:
            return cleaned_data

        content = cleaned_data.get("content")
        if not content:
            # empty content is replaced with the file template on save, see
            # EmailTemplate.save()
            content = EmailTemplate(
                title=cleaned_data.get("title") or ""
            ).get_default_content()

        if EXTENDS_TAG_RE.search(content or ""):
            self.add_error(
                "layout",
                _(
                    "This content uses the {% extends %} tag, so it already brings its own "
                    "frame and cannot be placed inside a layout. Remove the {% extends %} "
                    "tag from the content or leave the layout empty."
                ),
            )
        return cleaned_data


class MassEmailAttachmentForm(forms.ModelForm):
    class Meta:
        model = MassEmailAttachment
        fields = ["attachment_file"]


class MassEmailMessageForm(forms.ModelForm):
    class Meta:
        model = MassEmailMessage
        fields = [
            "subject",
            "content",
            "date_sent",
        ]
