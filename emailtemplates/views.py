# coding=utf-8
from __future__ import unicode_literals

import copy
import difflib

import django
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.template import Context, Template
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views import View

from emailtemplates.email import EmailFromTemplate
from emailtemplates.models import EmailLayout, EmailTemplate, MassEmailMessage
from emailtemplates.registry import email_templates
from emailtemplates.rich_text import unescape_template_tags


def render_preview(email_template, content=None):
    """
    HTML of the preview of an email template: `content` (by default the content of the
    template) rendered by `EmailFromTemplate` as the email is sent - in the layout, with the
    subject, the preheader and the blocks - filled with the example context of the registry.
    """
    if content is not None:
        email_template = copy.copy(email_template)
        email_template.content = content
    eft = EmailFromTemplate(
        name=email_template.title,
        language=email_template.language,
        template_object=email_template,
        registry_validation=False,
    )
    eft.context.update(email_templates.get_preview_context(email_template.title))
    return eft.render().html


class EmailPreviewView(View):
    def get_email_template(self):
        return get_object_or_404(
            EmailTemplate.objects.select_related("layout"), pk=self.kwargs["pk"]
        )

    def get(self, request, *args, **kwargs):
        return HttpResponse(
            render_preview(self.get_email_template()),
            content_type="text/html; charset=utf-8",
        )


email_preview_view = staff_member_required(EmailPreviewView.as_view())


class EmailLayoutPreviewView(View):
    """
    Shows a layout with a placeholder in place of the email template content.
    """

    placeholder = (
        '<div style="padding:30px;margin:10px 0;border:2px dashed #b0b0b0;'
        'text-align:center;color:#707070;font-family:sans-serif;">%s</div>'
    )

    def get_layout(self):
        return get_object_or_404(EmailLayout, pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        layout = self.get_layout()
        content = layout.wrap_content(
            self.placeholder % _("Content of the email template goes here")
        )
        try:
            html = Template(content).render(Context({}))
        except Exception as e:
            # header and footer may use context variables this preview does not provide,
            # show the problem instead of a 500
            html = '<p style="color:red">%s</p>' % escape(e)
        return HttpResponse(html, content_type="text/html; charset=utf-8")


email_layout_preview_view = staff_member_required(EmailLayoutPreviewView.as_view())


class SendMassEmailView(View):
    def get_mass_email_message(self):
        return get_object_or_404(MassEmailMessage, pk=self.kwargs["pk"])

    def redirect_back(self):
        return HttpResponseRedirect(
            reverse(
                "admin:emailtemplates_massemailmessage_change",
                args=(self.get_mass_email_message().pk,),
            ),
        )

    def get(self, request, *args, **kwargs):
        mass_email_message = self.get_mass_email_message()
        if mass_email_message.sent:
            messages.success(
                request,
                _(
                    "Mass email was already sent. "
                    "Create new mail message or force sending from shell."
                ),
            )
            return self.redirect_back()
        sent = mass_email_message.send()
        if sent:
            messages.success(request, _("Mass email sent successfully"))
        else:
            messages.warning(
                request, _("Error occurred when trying to send mass email message.")
            )
        return self.redirect_back()


send_mass_email_view = SendMassEmailView.as_view()


class EmailTemplateAdminView(View):
    """
    Base of the admin views of one email template, added by `EmailTemplateAdmin.get_urls()`,
    which passes `model_admin`. Requires the `permission` ("view" or "change") of the
    model admin for the template.
    """

    model_admin = None
    permission = "change"

    def dispatch(self, request, object_id):
        self.object = self.model_admin.get_object(request, object_id)
        if self.object is None:
            raise Http404
        has_permission = getattr(
            self.model_admin, "has_%s_permission" % self.permission
        )
        if not has_permission(request, self.object):
            raise PermissionDenied
        return super(EmailTemplateAdminView, self).dispatch(request, object_id)

    def get_change_url(self):
        opts = self.model_admin.opts
        return reverse(
            "admin:%s_%s_change" % (opts.app_label, opts.model_name),
            args=[self.object.pk],
        )


class EmailTemplateDefaultVersionView(EmailTemplateAdminView):
    """
    Compares the content of an email template with its default version - the template
    file - and, on request, replaces the content with it or restores the content the last
    replacement replaced.
    """

    template_name = "admin/emailtemplates/emailtemplate/default_version.html"

    def get(self, request, object_id):
        return TemplateResponse(request, self.template_name, self.get_context_data())

    def post(self, request, object_id):
        action = request.POST.get("action")
        if action == "replace" and self.object.get_default_content():
            self.object.replace_with_default()
            messages.success(
                request, _("The content was replaced with the default version.")
            )
        elif action == "restore" and self.object.previous_content:
            self.object.restore_previous_content()
            messages.success(request, _("The previous content was restored."))
        return HttpResponseRedirect(self.get_change_url())

    def get_context_data(self):
        default = self.object.get_default_content()
        return dict(
            self.model_admin.admin_site.each_context(self.request),
            title=_("Default version of %s") % self.object,
            opts=self.model_admin.opts,
            original=self.object,
            change_url=self.get_change_url(),
            # the markup of the breadcrumbs of the admin, a list since Django 6.0
            breadcrumbs_list=django.VERSION >= (6, 0),
            has_default=bool(default),
            has_new_default=self.object.has_new_default(),
            differs=self.object.differs_from_default(),
            diff_table=diff_table(self.object.content, default),
            current_preview=safe_preview(self.object),
            default_preview=safe_preview(self.object, default),
        )


class EmailTemplateBlocksView(EmailTemplateAdminView):
    """
    The blocks of an email template rendered with the example context, as JSON
    {name: HTML}, shown in the rich text editor when a block is clicked.
    """

    permission = "view"

    def get(self, request, object_id):
        context = email_templates.get_preview_context(self.object.title)
        blocks = {}
        for block in email_templates.get_blocks(self.object.title):
            try:
                blocks[block.name] = block.render(context)
            except Exception as e:
                blocks[block.name] = format_html('<p style="color:red">{}</p>', e)
        return JsonResponse(blocks)


class EmailTemplatePreviewView(EmailTemplateAdminView):
    """
    The live preview next to the editor: the email as it would be sent with the content,
    the subject, the preheader and the layout posted from the form - not saved - filled
    with the example context, as JSON ``{"html": ...}``, or ``{"error": ...}`` when it
    cannot be rendered, e.g. while a template tag is being typed.
    """

    permission = "view"

    def post(self, request, object_id):
        try:
            return JsonResponse({"html": render_preview(self.get_email_template())})
        except Exception as e:
            return JsonResponse({"error": str(e)})

    def get_email_template(self):
        """
        The email template with the values of the form, not saved.
        """
        data = self.request.POST
        email_template = copy.copy(self.object)
        email_template.content = unescape_template_tags(data.get("content", ""))
        email_template.subject = data.get("subject", email_template.subject)
        email_template.preheader = data.get("preheader", email_template.preheader)
        layout_id = data.get("layout", "")
        email_template.layout = (
            EmailLayout.objects.filter(pk=layout_id).first()
            if layout_id.isdigit()
            else None
        )
        return email_template


def diff_table(current, default):
    """
    The lines of the content and of the default version side by side, with line numbers and
    the changes marked, as the HTML table of `difflib.HtmlDiff`.
    """
    return mark_safe(
        difflib.HtmlDiff(wrapcolumn=60).make_table(
            (current or "").splitlines(),
            (default or "").splitlines(),
            _("Your content"),
            _("Default version"),
        )
    )


def safe_preview(email_template, content=None):
    """
    `render_preview()`, or the error preventing it, so that a broken version can still be
    replaced.
    """
    try:
        return render_preview(email_template, content)
    except Exception as e:
        return format_html('<p style="color:red">{}</p>', e)
