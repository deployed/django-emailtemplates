# coding=utf-8
from django.contrib import admin
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from .forms import EmailTemplateAdminForm, MassEmailMessageForm, MassEmailAttachmentForm
from .models import EmailTemplate, MassEmailMessage, MassEmailAttachment


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
    readonly_fields = ['show_links', 'created', 'modified']

    def show_links(self, obj):
        if not obj.pk:
            return ''
        return u'<a href="%s" target="_blank">%s</a>' % (
            reverse('email_preview', kwargs={'pk': obj.pk}), _('Show email preview')
        )

    show_links.allow_tags = True
    show_links.short_description = _('Actions')


admin.site.register(EmailTemplate, EmailTemplateAdmin)


class MassEmailAttachmentInline(admin.TabularInline):
    model = MassEmailAttachment
    form = MassEmailAttachmentForm


class MassEmailMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'date_sent')
    readonly_fields = ['date_sent']
    form = MassEmailMessageForm
    inlines = [MassEmailAttachmentInline]


admin.site.register(MassEmailMessage, MassEmailMessageAdmin)
