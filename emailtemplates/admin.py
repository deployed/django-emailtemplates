# coding=utf-8
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from .forms import (
    EmailLayoutAdminForm,
    EmailTemplateAdminForm,
    MassEmailAttachmentForm,
    MassEmailMessageForm,
)
from .email import resend
from .models import (
    EmailAttachment,
    EmailLayout,
    EmailTemplate,
    MassEmailAttachment,
    EmailLog,
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


class EmailLogAdmin(admin.ModelAdmin):
    """
    The history of sent emails, read only; failed emails can be sent again, see
    `EmailLog.can_resend()`. Entries are written by the email backend, see
    `emailtemplates.backends`.
    """

    date_hierarchy = "created"
    list_display = (
        "created",
        "template",
        "source",
        "show_recipients",
        "subject",
        "show_status",
        "attempts",
        "sent_at",
        "show_resend",
    )
    list_filter = ("status", "template", "source")
    search_fields = ("recipients", "subject", "template", "source", "source_id")
    actions = ["resend_selected"]
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "show_status",
                    "created",
                    "modified",
                    "sent_at",
                    "attempts",
                    "last_error",
                ]
            },
        ),
        (
            _("Email"),
            {
                "fields": [
                    "template",
                    "language",
                    "from_email",
                    "recipients",
                    "cc",
                    "bcc",
                    "reply_to",
                    "subject",
                    "attachments",
                ]
            },
        ),
        (_("Content"), {"fields": ["show_html", "text"]}),
        (
            _("Source"),
            {
                "fields": ["source", "source_id", "source_seq", "source_context"],
                "classes": ["collapse"],
            },
        ),
        (_("Headers"), {"fields": ["headers"], "classes": ["collapse"]}),
    ]
    readonly_fields = [
        field for _name, options in fieldsets for field in options["fields"]
    ]

    class Media:
        css = {"all": ("emailtemplates/email_log.css",)}

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_resend_permission(self, request):
        opts = self.opts
        return request.user.has_perm("%s.change_%s" % (opts.app_label, opts.model_name))

    def get_list_display(self, request):
        list_display = list(super(EmailLogAdmin, self).get_list_display(request))
        if not self.has_resend_permission(request):
            list_display.remove("show_resend")
        return list_display

    @admin.display(description=_("recipients"))
    def show_recipients(self, obj):
        return ", ".join(obj.recipients)

    @admin.display(description=_("status"), ordering="status")
    def show_status(self, obj):
        return format_html(
            '<span class="emailtemplates-status emailtemplates-status--{}">{}</span>',
            obj.status,
            obj.get_status_display(),
        )

    @admin.display(description=_("HTML"))
    def show_html(self, obj):
        if not obj.html:
            return "-"
        return format_html(
            '<iframe class="emailtemplates-email-log-html" srcdoc="{}" sandbox '
            'title="{}"></iframe>',
            obj.html,
            _("HTML"),
        )

    @admin.display(description=_("send now"))
    def show_resend(self, obj):
        """
        A button submitting the form of the change list - a form cannot be nested in it -
        with its CSRF token to the view sending the email again, see `resend_view()`.
        """
        if not obj.can_resend():
            return "-"
        return format_html(
            '<button type="submit" class="button" formaction="{}">{}</button>',
            reverse(self.resend_url_name(), args=[obj.pk]),
            _("Send now"),
        )

    def resend_url_name(self):
        opts = self.opts
        return "admin:%s_%s_resend" % (opts.app_label, opts.model_name)

    def get_urls(self):
        opts = self.opts
        return [
            path(
                "<path:object_id>/resend/",
                self.admin_site.admin_view(require_POST(self.resend_view)),
                name="%s_%s_resend" % (opts.app_label, opts.model_name),
            ),
        ] + super(EmailLogAdmin, self).get_urls()

    def resend_view(self, request, object_id):
        email_log = self.get_object(request, object_id)
        if email_log is None:
            raise Http404
        if not self.has_resend_permission(request):
            raise PermissionDenied
        self.resend(request, [email_log])
        opts = self.opts
        return HttpResponseRedirect(
            reverse("admin:%s_%s_changelist" % (opts.app_label, opts.model_name))
        )

    @admin.action(description=_("Send selected emails now"), permissions=["resend"])
    def resend_selected(self, request, queryset):
        self.resend(request, queryset)

    def resend(self, request, email_logs):
        sent, skipped = 0, 0
        for email_log in email_logs:
            if email_log.can_resend() and (email_log.html or email_log.text):
                resend(email_log)
                sent += 1
            else:  # not failed, or without the content, see EMAILTEMPLATES_EMAIL_LOG_CONTENT
                skipped += 1
        if sent:
            self.message_user(
                request,
                ngettext(
                    "%d email is being sent again.",
                    "%d emails are being sent again.",
                    sent,
                )
                % sent,
                messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                ngettext(
                    "%d email was skipped: only failed emails with their content kept can "
                    "be sent again.",
                    "%d emails were skipped: only failed emails with their content kept "
                    "can be sent again.",
                    skipped,
                )
                % skipped,
                messages.WARNING,
            )


admin.site.register(EmailLog, EmailLogAdmin)
