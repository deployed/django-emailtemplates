# coding=utf-8
from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .forms import (
    EmailLayoutAdminForm,
    EmailTemplateAdminForm,
    MassEmailAttachmentForm,
    MassEmailMessageForm,
)
from .models import (
    EmailAttachment,
    EmailLayout,
    EmailTemplate,
    MassEmailAttachment,
    MassEmailMessage,
)
from .views import (
    EmailTemplateBlocksView,
    EmailTemplateDefaultVersionView,
    EmailTemplatePreviewView,
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
        "default_status",
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
    readonly_fields = ["show_links", "default_version", "created", "modified"]
    inlines = [EmailTemplateAttachmentInline]

    def show_links(self, obj):
        if not obj.pk:
            return ""
        return mark_safe(
            '<a href="%s" target="_blank">%s</a>'
            % (reverse("email_preview", kwargs={"pk": obj.pk}), _("Show email preview"))
        )

    show_links.short_description = _("Actions")

    def default_status(self, obj):
        if obj.has_new_default():
            return format_html("<strong>{}</strong>", _("New default version"))
        return ""

    default_status.short_description = _("Default version")

    def default_version(self, obj):
        """
        Whether the content is the default version or developers updated it since, with a
        link to the comparison, see `EmailTemplateDefaultVersionView`.
        """
        if not obj.pk or not obj.get_default_content():
            return "-"
        if obj.has_new_default():
            status = format_html(
                "<strong>{}</strong>",
                _(
                    "A new default version is available. Your content stays as it is "
                    "until you replace it."
                ),
            )
        elif obj.differs_from_default():
            status = _("Your content differs from the default version.")
        else:
            status = _("The content is the default version.")
        return format_html(
            '{}<br><a href="{}">{}</a>',
            status,
            reverse(self.default_url_name(), args=[obj.pk]),
            _("Compare with the default version"),
        )

    default_version.short_description = _("Default version")

    def default_url_name(self):
        opts = self.model._meta
        return "admin:%s_%s_default" % (opts.app_label, opts.model_name)

    def get_urls(self):
        """
        Adds the comparison with the default version, the blocks rendered for the rich text
        editor and the live preview next to the editor, see
        `EmailTemplateDefaultVersionView`, `EmailTemplateBlocksView` and
        `EmailTemplatePreviewView`.
        """
        opts = self.model._meta

        def url(view_class, name):
            return path(
                "<path:object_id>/%s/" % name,
                self.admin_site.admin_view(view_class.as_view(model_admin=self)),
                name="%s_%s_%s" % (opts.app_label, opts.model_name, name),
            )

        return [
            url(EmailTemplateDefaultVersionView, "default"),
            url(EmailTemplateBlocksView, "blocks"),
            url(EmailTemplatePreviewView, "preview"),
        ] + super(EmailTemplateAdmin, self).get_urls()


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
