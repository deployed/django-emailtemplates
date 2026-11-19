from django.contrib.auth.models import Permission, User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from ..models import EmailAttachment, EmailLayout, EmailTemplate, MassEmailMessage
from ..registry import email_templates

SCRIPT = "<script>alert(1)</script>"


def staff(*perms):
    user = User.objects.create_user("staff", "staff@example.com", "x", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=perms))
    return user


email_templates.register("security.html")


class SecurityTest(TestCase):
    def assert_sandboxed(self, response):
        self.assertContains(response, "<iframe sandbox srcdoc=")
        self.assertNotContains(response, SCRIPT)

    def test_anonymous_get_does_not_send_a_mass_email(self):
        User.objects.create_user("user", "user@example.com", "x")
        message = MassEmailMessage.objects.create(subject="Draft", content="Draft")
        self.client.get(reverse("send_mass_email", kwargs={"pk": message.pk}))
        self.assertEqual(mail.outbox, [])

    def test_email_preview_runs_no_script_of_the_content(self):
        template = EmailTemplate.objects.create(title="security.html", content=SCRIPT)
        self.client.force_login(User.objects.create_superuser("admin", "", "x"))
        url = reverse("email_preview", kwargs={"pk": template.pk})
        self.assert_sandboxed(self.client.get(url))

    def test_layout_preview_runs_no_script_breaking_out_of_the_styles(self):
        layout = EmailLayout.objects.create(name="xss", styles="</style>" + SCRIPT)
        self.client.force_login(User.objects.create_superuser("admin", "", "x"))
        url = reverse("email_layout_preview", kwargs={"pk": layout.pk})
        self.assert_sandboxed(self.client.get(url))

    def test_previews_require_the_view_permission(self):
        template = EmailTemplate.objects.create(title="security.html", content="x")
        layout = EmailLayout.objects.create(name="secret")
        self.client.force_login(staff())
        for url in (
            reverse("email_preview", kwargs={"pk": template.pk}),
            reverse("email_layout_preview", kwargs={"pk": layout.pk}),
        ):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_live_preview_requires_the_change_permission(self):
        template = EmailTemplate.objects.create(title="security.html", content="x")
        user = staff("view_emailtemplate")
        self.client.force_login(user)
        url = reverse("admin:emailtemplates_emailtemplate_preview", args=[template.pk])
        self.assertEqual(self.client.post(url, {"content": "x"}).status_code, 403)
        user.user_permissions.add(
            Permission.objects.get(codename="change_emailtemplate")
        )
        self.assertEqual(self.client.post(url, {"content": "x"}).status_code, 200)

    def test_attachments_cannot_be_files_running_scripts(self):
        for name in ("terms.html", "logo.svg", "data.xml"):
            attachment = EmailAttachment(
                attachment_file=SimpleUploadedFile(name, SCRIPT.encode())
            )
            with self.assertRaises(ValidationError, msg=name):
                attachment.full_clean()
        EmailAttachment(
            attachment_file=SimpleUploadedFile("terms.pdf", b"%PDF")
        ).full_clean()
