# Generated by Django 3.1.2 on 2020-11-20 10:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emailtemplates', '0007_auto_20201113_1354'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailattachment',
            name='send_as_link',
            field=models.BooleanField(default=True, verbose_name='Send as link'),
        ),
        migrations.AddField(
            model_name='massemailattachment',
            name='send_as_link',
            field=models.BooleanField(default=True, verbose_name='Send as link'),
        ),
    ]
