# coding=utf-8
from django.contrib import admin
from .forms import EmailTemplateAdminForm
from .models import EmailTemplate


class EmailTemplateAdmin(admin.ModelAdmin):
    """
    Admin view of EmailTemplate
    """
    list_display = ('title', 'language', 'subject',)
    list_display_links = ('title',)
    list_filter = ('title', 'language',)
    search_fields = ('title', 'subject')
    form = EmailTemplateAdminForm
    save_on_top = True
    save_as = True

admin.site.register(EmailTemplate, EmailTemplateAdmin)
