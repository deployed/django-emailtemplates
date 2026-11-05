# coding=utf-8
from importlib.util import find_spec

from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Warning, register
from django.utils.module_loading import import_string

from emailtemplates.backends import EmailLogBackendMixin

LOCMEM_EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


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


@register()
def check_email_backend(app_configs, **kwargs):
    """
    The history of sent emails (Email logs) is written by the email backend; a project
    setting EMAIL_BACKEND again, e.g. in the settings of one environment, may leave it out
    by mistake. The backend for tests, which the test runner sets before the checks, keeps
    no history on purpose.
    """
    if settings.EMAIL_BACKEND == LOCMEM_EMAIL_BACKEND:
        return []
    try:
        backend = import_string(settings.EMAIL_BACKEND)
    except Exception:
        return []  # reported when an email is sent
    if isinstance(backend, type) and issubclass(backend, EmailLogBackendMixin):
        return []
    return [
        Warning(
            "EMAIL_BACKEND does not record the sent emails in Email logs.",
            hint="Set EMAIL_BACKEND = 'emailtemplates.backends.EmailBackend' and the "
            "backend delivering the emails as EMAILTEMPLATES_EMAIL_BACKEND, or mix "
            "emailtemplates.backends.EmailLogBackendMixin in the backend. Silence "
            "emailtemplates.W002 to keep no history.",
            id="emailtemplates.W002",
        )
    ]
