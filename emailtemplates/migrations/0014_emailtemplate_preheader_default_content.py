from django.db import migrations, models
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import get_template


def snapshot_default_content(apps, schema_editor):
    """
    Existing templates get their template file as it is now as the default content, so that
    later changes of the file are offered as a new default version.
    """
    EmailTemplate = apps.get_model("emailtemplates", "EmailTemplate")
    for email_template in EmailTemplate.objects.filter(default_content=""):
        try:
            source = get_template(email_template.title).template.source
        except (TemplateDoesNotExist, TemplateSyntaxError):
            continue  # the template lives in the database only
        EmailTemplate.objects.filter(pk=email_template.pk).update(
            default_content=source
        )


class Migration(migrations.Migration):
    dependencies = [
        ("emailtemplates", "0013_emaillayout_emailtemplate_layout"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailtemplate",
            name="preheader",
            field=models.CharField(
                blank=True,
                help_text="Short text shown by email clients next to the subject in the inbox, available to the layout as {{ preheader }}. You can use variables from table.",
                max_length=255,
                verbose_name="preheader",
            ),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="default_content",
            field=models.TextField(
                blank=True,
                editable=False,
                help_text="The template file as it was when the content was created or last replaced with it. A different file means a new default version is available.",
                verbose_name="default content",
            ),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="previous_content",
            field=models.TextField(
                blank=True,
                editable=False,
                help_text="The content before it was last replaced with the default version.",
                verbose_name="previous content",
            ),
        ),
        migrations.RunPython(snapshot_default_content, migrations.RunPython.noop),
    ]
