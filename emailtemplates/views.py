# coding=utf-8
from __future__ import unicode_literals
from django.urls import reverse

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template import Template, Context
from django.views import View
from django.utils.html import escape
from django.utils.translation import gettext as _

from emailtemplates.models import EmailLayout, EmailTemplate, MassEmailMessage
from emailtemplates.registry import email_templates


class EmailPreviewView(View):
    def get_email_template(self):
        return get_object_or_404(EmailTemplate, pk=self.kwargs["pk"])

    def get_context_data(self):
        email_template = self.get_email_template()
        return email_templates.get_help_content(email_template.title)

    def get(self, request, *args, **kwargs):
        email_template = self.get_email_template()
        # `get_content()` so that the preview shows exactly what will be sent, including
        # the header and the footer of the selected layout.
        email_content = Template(email_template.get_content())
        return HttpResponse(
            email_content.render(Context(self.get_context_data())),
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
