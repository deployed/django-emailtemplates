# coding=utf-8
from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .forms import (
    EmailLayoutAdminForm,
    EmailTemplateAdminForm,
    MassEmailMessageForm,
    MassEmailAttachmentForm,
)
from .models import (
    EmailLayout,
    EmailTemplate,
    MassEmailMessage,
    MassEmailAttachment,
    EmailAttachment,
)


class EmailLayoutAdmin(admin.ModelAdmin):
    """
    Admin view of EmailLayout
    """

    form = EmailLayoutAdminForm
    list_display = (
        "name",
        "show_email_templates",
        "modified",
    )
    search_fields = ("name",)
    readonly_fields = ["show_links", "created", "modified"]
    fields = [
        "name",
        "frame",
        "styles",
        "show_links",
        "created",
        "modified",
    ]
    save_on_top = True

    def show_links(self, obj):
        if not obj.pk:
            return ""
        return mark_safe(
            '<a href="%s" target="_blank">%s</a>'
            % (
                reverse("email_layout_preview", kwargs={"pk": obj.pk}),
                _("Show layout preview"),
            )
        )

    show_links.short_description = _("Actions")

    def get_queryset(self, request):
        return (
            super(EmailLayoutAdmin, self)
            .get_queryset(request)
            .prefetch_related("email_templates")
        )

    def show_email_templates(self, obj):
        titles = [template.title for template in obj.email_templates.all()]
        return ", ".join(titles) or _("not used")

    show_email_templates.short_description = _("Email templates")


admin.site.register(EmailLayout, EmailLayoutAdmin)


class EmailTemplateAttachmentInline(admin.TabularInline):
    model = EmailTemplate.attachments.through
    extra = 1
    verbose_name = _("Attachment")
    verbose_name_plural = _("Attachments")


class EmailTemplateAdmin(admin.ModelAdmin):
    """
    Admin view of EmailTemplate
    """

    list_display = (
        "title",
        "layout",
        "language",
        "subject",
    )
    list_display_links = ("title",)
    list_select_related = ("layout",)
    list_filter = (
        "title",
        "layout",
        "language",
    )
    search_fields = ("title", "subject")
    form = EmailTemplateAdminForm
    save_on_top = True
    save_as = True
    readonly_fields = ["show_links", "created", "modified"]
    inlines = [EmailTemplateAttachmentInline]

    def show_links(self, obj):
        if not obj.pk:
            return ""
        return mark_safe(
            '<a href="%s" target="_blank">%s</a>'
            % (reverse("email_preview", kwargs={"pk": obj.pk}), _("Show email preview"))
        )

    show_links.allow_tags = True
    show_links.short_description = _("Actions")


admin.site.register(EmailTemplate, EmailTemplateAdmin)


class EmailAttachmentAdmin(admin.ModelAdmin):
    list_display = ["name", "comment", "ordering"]
    search_fields = ["name", "comment"]


admin.site.register(EmailAttachment, EmailAttachmentAdmin)


class MassEmailAttachmentInline(admin.TabularInline):
    model = MassEmailAttachment
    form = MassEmailAttachmentForm


class MassEmailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "date_sent")
    readonly_fields = ["date_sent"]
    form = MassEmailMessageForm
    inlines = [MassEmailAttachmentInline]


admin.site.register(MassEmailMessage, MassEmailMessageAdmin)
