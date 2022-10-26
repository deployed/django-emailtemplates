# Generated by Django 3.1.13 on 2022-08-03 12:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("emailtemplates", "0009_auto_20220111_1011"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="emailattachment",
            options={
                "ordering": ["ordering"],
                "verbose_name": "Attachment",
                "verbose_name_plural": "Attachments",
            },
        ),
        migrations.AlterModelOptions(
            name="massemailattachment",
            options={
                "ordering": ["ordering"],
                "verbose_name": "Attachment",
                "verbose_name_plural": "Attachments",
            },
        ),
        migrations.AddField(
            model_name="emailattachment",
            name="comment",
            field=models.TextField(
                blank=True, verbose_name="Comment", help_text="visible only in admin"
            ),
        ),
        migrations.AddField(
            model_name="emailattachment",
            name="ordering",
            field=models.PositiveIntegerField(default=0, verbose_name="Ordering"),
        ),
        migrations.AddField(
            model_name="massemailattachment",
            name="comment",
            field=models.TextField(
                blank=True, verbose_name="Comment", help_text="visible only in admin"
            ),
        ),
        migrations.AddField(
            model_name="massemailattachment",
            name="ordering",
            field=models.PositiveIntegerField(default=0, verbose_name="Ordering"),
        ),
    ]