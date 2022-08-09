# -*- coding: utf-8 -*-
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EmailtempatesConfig(AppConfig):
    name = "emailtemplates"
    verbose_name = _("E-MAIL TEMPLATES")
    default_auto_field = "django.db.models.BigAutoField"
