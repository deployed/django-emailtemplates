# coding=utf-8
from __future__ import unicode_literals
from django.urls import reverse

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template import Template, Context
from django.views import View
from django.utils.translation import gettext as _

from emailtemplates.models import EmailTemplate, MassEmailMessage
from emailtemplates.registry import email_templates


class EmailPreviewView(View):

    def get_email_template(self):
        return get_object_or_404(EmailTemplate, pk=self.kwargs['pk'])

    def get_context_data(self):
        email_template = self.get_email_template()
        return email_templates.get_help_content(email_template.title)

    def get(self, request, *args, **kwargs):
        email_template = self.get_email_template()
        email_content = Template(email_template.content)
        return HttpResponse(
            email_content.render(Context(self.get_context_data())),
            content_type='text/html; charset=utf-8'
        )


email_preview_view = staff_member_required(EmailPreviewView.as_view())


class SendMassEmailView(View):

    def get_mass_email_message(self):
        return get_object_or_404(MassEmailMessage, pk=self.kwargs['pk'])

    def redirect_back(self):
        return HttpResponseRedirect(
            reverse('admin:emailtemplates_massemailmessage_change', args=(self.get_mass_email_message().pk,)),
        )

    def get(self, request, *args, **kwargs):
        mass_email_message = self.get_mass_email_message()
        if mass_email_message.sent:
            messages.success(request, _("Mass email was already sent. "
                                        "Create new mail message or force sending from shell."))
            return self.redirect_back()
        sent = mass_email_message.send()
        if sent:
            messages.success(request, _("Mass email sent successfully"))
        else:
            messages.warning(request, _("Error occurred when trying to send mass email message."))
        return self.redirect_back()


send_mass_email_view = SendMassEmailView.as_view()
