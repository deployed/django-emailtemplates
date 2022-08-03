# Generated by Django 3.1.2 on 2020-11-10 11:15

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("emailtemplates", "0004_auto_20180523_1608"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="emailtemplate",
            options={
                "verbose_name": "Email template",
                "verbose_name_plural": "Email templates",
            },
        ),
        migrations.AlterModelOptions(
            name="massemailmessage",
            options={
                "verbose_name": "Mass email message",
                "verbose_name_plural": "Mass email messages",
            },
        ),
        migrations.AlterField(
            model_name="massemailattachment",
            name="attachment_file",
            field=models.FileField(upload_to="", verbose_name="Attachment file"),
        ),
        migrations.AlterField(
            model_name="massemailattachment",
            name="mass_email_message",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="attachments",
                to="emailtemplates.massemailmessage",
            ),
        ),
    ]
