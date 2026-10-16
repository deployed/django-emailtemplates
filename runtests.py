import os
import shutil
import sys
import tempfile

import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    settings.configure()
    settings.SECRET_KEY = "secret-key"
    settings.INSTALLED_APPS = (
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.admin",
        "django.contrib.messages",
        "tinymce",
        "emailtemplates",
    )
    settings.MIDDLEWARE = (
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    )
    settings.DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
    settings.STATIC_URL = "/static/"
    # attachments saved by the tests, deleted afterwards
    settings.MEDIA_ROOT = tempfile.mkdtemp()
    settings.ROOT_URLCONF = "emailtemplates.tests.urls"
    settings.TEMPLATES = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "APP_DIRS": True,
            "DIRS": [
                os.path.join(
                    os.path.dirname(__file__), "emailtemplates", "tests", "templates"
                )
            ],
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ],
            },
        }
    ]
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=3)
    try:
        failures = test_runner.run_tests(["emailtemplates"])
    finally:
        shutil.rmtree(settings.MEDIA_ROOT)
    sys.exit(bool(failures))
