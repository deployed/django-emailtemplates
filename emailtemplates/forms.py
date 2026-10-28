# coding=utf-8
import logging

from django import forms
from django.core.exceptions import ValidationError
from django.template import Template, TemplateSyntaxError
from django.urls import NoReverseMatch, reverse
from django.utils.functional import lazy
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from emailtemplates.models import (
    EXTENDS_TAG_RE,
    EmailLayout,
    EmailTemplate,
    MassEmailAttachment,
    MassEmailMessage,
)
from emailtemplates.registry import NotRegistered, email_templates
from emailtemplates.rich_text import (
    rich_text_available,
    rich_text_config,
    unescape_template_tags,
)
from emailtemplates.widgets import (
    CodeEditorTextarea,
    EmailContentEditor,
    EmailFrameWidget,
)

logger = logging.getLogger(__name__)


class EmailFrameField(forms.MultiValueField):
    """
    `header_content` and `footer_content` as one field, see `EmailFrameWidget`.
    """

    widget = EmailFrameWidget

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("require_all_fields", False)
        super(EmailFrameField, self).__init__(
            fields=(
                forms.CharField(required=False),
                forms.CharField(required=False),
            ),
            **kwargs
        )

    def compress(self, data_list):
        return data_list or ["", ""]


class EmailLayoutAdminForm(forms.ModelForm):
    frame = EmailFrameField(
        label=_("Frame"),
        help_text=_(
            "Everything above the divider is sent before the content of the email "
            "template, everything below it after. Tags opened above may be closed below."
        ),
    )

    class Meta:
        model = EmailLayout
        fields = ["name", "styles"]
        widgets = {"styles": CodeEditorTextarea(mode="css")}

    def __init__(self, *args, **kwargs):
        super(EmailLayoutAdminForm, self).__init__(*args, **kwargs)
        self.initial["frame"] = [
            self.instance.header_content,
            self.instance.footer_content,
        ]

    def clean_frame(self):
        header_content, footer_content = self.cleaned_data["frame"]
        # header and footer are rendered as one template around the email content (see
        # EmailLayout.wrap_content()), so a tag opened in the header may be closed in the
        # footer - they can only be validated together
        try:
            Template(header_content + footer_content)
        except TemplateSyntaxError as e:
            raise ValidationError("Syntax error in email layout: %s" % e)
        return [header_content, footer_content]

    def save(self, commit=True):
        layout = super(EmailLayoutAdminForm, self).save(commit=False)
        layout.header_content, layout.footer_content = self.cleaned_data["frame"]
        if commit:
            layout.save()
        return layout


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
            "preheader",
            "content",
            "language",
            "ordering",
            "created",
            "modified",
        ]
        widgets = {"content": EmailContentEditor()}

    def __init__(self, *args, **kwargs):
        super(EmailTemplateAdminForm, self).__init__(*args, **kwargs)
        self.fields["title"].help_text = mark_safe(
            email_templates.get_form_help_text(self.initial.get("title"))
        )
        if self.instance.pk:
            self.fields["title"].widget = forms.TextInput(
                attrs={"readonly": "readonly", "style": "width:480px"}
            )
            self.fields["content"].widget = EmailContentEditor(
                rich_text_config=self.get_rich_text_config(),
                preview_url=self.get_admin_url("preview"),
            )
        else:
            self.fields["content"].widget = forms.HiddenInput()
            self.fields["content"].required = False
            self.fields["subject"].widget = forms.HiddenInput()
            self.fields["preheader"].widget = forms.HiddenInput()

    def get_rich_text_config(self):
        """
        TinyMCE configuration of the content, None when the rich text editor is off.
        """
        if not rich_text_available():
            return None
        layout = self.instance.layout
        return rich_text_config(
            variables=self.get_variables(),
            blocks=self.get_blocks(),
            styles=layout.styles if layout else "",
            blocks_url=self.get_admin_url("blocks"),
        )

    def get_admin_url(self, name):
        """
        URL of an admin view of this template added by `EmailTemplateAdmin.get_urls()`:
        "blocks" (rendered with example data) or "preview" (the live preview).
        """
        try:
            return reverse(
                "admin:emailtemplates_emailtemplate_%s" % name, args=[self.instance.pk]
            )
        except NoReverseMatch:  # the admin is registered on another site
            return ""

    def get_variables(self):
        """
        (name, description) pairs of the context of this template, from the registry.
        """
        try:
            help_context = email_templates.get_help_context(self.instance.title)
        except NotRegistered:
            return []
        return sorted(help_context.items())

    def get_blocks(self):
        """
        Blocks this template may use, from the registry.
        """
        try:
            return email_templates.get_blocks(self.instance.title)
        except NotRegistered:
            return []

    def clean_content(self):
        # from either editor: template tags typed in the rich text editor come encoded
        content = unescape_template_tags(self.cleaned_data["content"])
        try:
            Template(content)
        except TemplateSyntaxError as e:
            raise ValidationError("Syntax error in custom email template: %s" % e)
        return content

    def clean(self):
        cleaned_data = super(EmailTemplateAdminForm, self).clean()
        if not cleaned_data.get("layout"):
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
