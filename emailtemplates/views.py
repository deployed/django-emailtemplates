# coding=utf-8
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template import Template, Context
from django.views import View

from emailtemplates.models import EmailTemplate
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
