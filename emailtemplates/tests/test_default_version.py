# coding=utf-8
import mock
from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse

from ..models import EmailTemplate
from ..registry import email_templates
from ..views import diff_rows

TITLE = "default_version.html"
LANGUAGE = "pl"


class FileTestCase(TestCase):
    """The template file is `self.files[TITLE]`, changed by the tests."""

    def setUp(self):
        if not email_templates.is_registered(TITLE):
            email_templates.register(TITLE, subject="Hi")
        self.files = {TITLE: "<p>Version 1</p>"}
        patcher = mock.patch(
            "emailtemplates.models.TemplateSourceLoader.get_source",
            side_effect=lambda name: self.files[name],
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.email_template = EmailTemplate.objects.create(
            title=TITLE, language=LANGUAGE
        )


class DefaultContentTest(FileTestCase):
    def test_new_template_keeps_a_snapshot_of_the_file(self):
        self.assertEqual(self.email_template.content, "<p>Version 1</p>")
        self.assertEqual(self.email_template.default_content, "<p>Version 1</p>")
        self.assertFalse(self.email_template.has_new_default())
        self.assertFalse(self.email_template.differs_from_default())

    def test_edits_of_the_content_are_not_a_new_default(self):
        self.email_template.content = "<p>Mine</p>"
        self.email_template.save()
        self.assertFalse(self.email_template.has_new_default())
        self.assertTrue(self.email_template.differs_from_default())

    def test_a_changed_file_is_a_new_default_but_the_content_stays(self):
        self.files[TITLE] = "<p>Version 2</p>"
        self.email_template.refresh_from_db()
        self.assertTrue(self.email_template.has_new_default())
        self.assertEqual(self.email_template.content, "<p>Version 1</p>")

    def test_whitespace_changes_of_the_file_are_not_a_new_default(self):
        self.files[TITLE] = "<p>Version 1</p>\r\n\n"
        self.assertFalse(self.email_template.has_new_default())

    def test_templates_without_snapshot_never_report_a_new_default(self):
        EmailTemplate.objects.filter(pk=self.email_template.pk).update(
            default_content=""
        )
        self.email_template.refresh_from_db()
        self.files[TITLE] = "<p>Version 2</p>"
        self.assertFalse(self.email_template.has_new_default())
        self.assertTrue(self.email_template.differs_from_default())

    def test_replace_with_default_keeps_the_replaced_content(self):
        self.email_template.content = "<p>Mine</p>"
        self.email_template.save()
        self.files[TITLE] = "<p>Version 2</p>"

        self.email_template.replace_with_default()
        self.email_template.refresh_from_db()

        self.assertEqual(self.email_template.content, "<p>Version 2</p>")
        self.assertEqual(self.email_template.default_content, "<p>Version 2</p>")
        self.assertEqual(self.email_template.previous_content, "<p>Mine</p>")
        self.assertFalse(self.email_template.has_new_default())

    def test_restore_previous_content(self):
        self.email_template.content = "<p>Mine</p>"
        self.email_template.save()
        self.files[TITLE] = "<p>Version 2</p>"
        self.email_template.replace_with_default()

        self.email_template.restore_previous_content()
        self.email_template.refresh_from_db()

        self.assertEqual(self.email_template.content, "<p>Mine</p>")
        self.assertEqual(self.email_template.previous_content, "<p>Version 2</p>")


@override_settings(ROOT_URLCONF="emailtemplates.tests.urls")
class DefaultVersionAdminTest(FileTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_superuser("admin", "admin@example.com", "x")
        self.client.force_login(self.user)
        self.url = reverse(
            "admin:emailtemplates_emailtemplate_default", args=[self.email_template.pk]
        )
        self.change_url = reverse(
            "admin:emailtemplates_emailtemplate_change", args=[self.email_template.pk]
        )

    def edit_and_update_the_file(self):
        self.email_template.content = "<p>Mine</p>"
        self.email_template.save()
        self.files[TITLE] = "<p>Version 2</p>"

    def test_changelist_marks_templates_with_a_new_default(self):
        changelist = reverse("admin:emailtemplates_emailtemplate_changelist")
        self.assertNotContains(self.client.get(changelist), "New default version")
        self.files[TITLE] = "<p>Version 2</p>"
        self.assertContains(self.client.get(changelist), "New default version")

    def test_change_page_links_to_the_comparison(self):
        self.files[TITLE] = "<p>Version 2</p>"
        response = self.client.get(self.change_url)
        self.assertContains(response, "A new default version is available.")
        self.assertContains(response, self.url)

    def test_comparison_shows_both_versions_and_the_changes(self):
        self.edit_and_update_the_file()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Developers updated the default version")
        self.assertContains(response, "&lt;p&gt;Mine&lt;/p&gt;")  # in srcdoc
        self.assertContains(response, "&lt;p&gt;Version 2&lt;/p&gt;")
        # the changed line side by side: the content on the left, the default on the right
        self.assertContains(
            response, '<td class="changed">&lt;p&gt;Mine&lt;/p&gt;</td>'
        )
        self.assertContains(
            response, '<td class="changed">&lt;p&gt;Version 2&lt;/p&gt;</td>'
        )
        self.assertContains(response, "Replace my content with the default version")
        self.assertNotContains(response, "Restore the content")

    def test_viewing_the_comparison_changes_nothing(self):
        self.edit_and_update_the_file()
        self.client.get(self.url)
        self.email_template.refresh_from_db()
        self.assertEqual(self.email_template.content, "<p>Mine</p>")

    def test_replace_and_restore(self):
        self.edit_and_update_the_file()

        response = self.client.post(self.url, {"action": "replace"})
        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
        self.email_template.refresh_from_db()
        self.assertEqual(self.email_template.content, "<p>Version 2</p>")
        self.assertContains(self.client.get(self.url), "Restore the content")

        self.client.post(self.url, {"action": "restore"})
        self.email_template.refresh_from_db()
        self.assertEqual(self.email_template.content, "<p>Mine</p>")

    def test_broken_default_is_shown_as_an_error(self):
        self.files[TITLE] = "{% if %}"
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_staff_without_change_permission_is_denied(self):
        staff = User.objects.create_user(
            "staff", "staff@example.com", "x", is_staff=True
        )
        staff.user_permissions.add(
            Permission.objects.get(codename="view_emailtemplate")
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.post(self.url, {"action": "replace"}).status_code, 403
        )


class DiffRowsTest(TestCase):
    def test_lines_side_by_side(self):
        rows = diff_rows("a\nb\nc\nd", "a\nB\nc\nnew\nd")
        self.assertEqual(
            rows,
            [
                ((1, "a", ""), (1, "a", "")),
                ((2, "b", "changed"), (2, "B", "changed")),
                ((3, "c", ""), (3, "c", "")),
                ((None, "", ""), (4, "new", "added")),
                ((4, "d", ""), (5, "d", "")),
            ],
        )
