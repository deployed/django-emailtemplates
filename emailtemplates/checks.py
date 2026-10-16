# coding=utf-8
from importlib.util import find_spec

from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def check_rich_text_editor(app_configs, **kwargs):
    if getattr(settings, "EMAILTEMPLATES_RICH_TEXT", False) and not apps.is_installed(
        "tinymce"
    ):
        return [
            Warning(
                "EMAILTEMPLATES_RICH_TEXT is on, but django-tinymce is not installed. "
                "Email templates will be edited as HTML code.",
                hint="pip install django-emailtemplates[tinymce] and add 'tinymce' to "
                "INSTALLED_APPS.",
                id="emailtemplates.W001",
            )
        ]
    return []


@register()
def check_css_inliner(app_configs, **kwargs):
    if not getattr(settings, "EMAILTEMPLATES_INLINE_CSS", False):
        return []
    if find_spec("css_inline") is None:
        return [
            Error(
                "EMAILTEMPLATES_INLINE_CSS is set, but css-inline is not installed.",
                hint="pip install django-emailtemplates[inline]",
                id="emailtemplates.E001",
            )
        ]
    return []


@register()
def check_celery(app_configs, **kwargs):
    if (
        getattr(settings, "EMAILTEMPLATES_CELERY", False)
        and find_spec("celery") is None
    ):
        return [
            Error(
                "EMAILTEMPLATES_CELERY is set, but Celery is not installed.",
                hint="pip install django-emailtemplates[celery]",
                id="emailtemplates.E002",
            )
        ]
    return []
