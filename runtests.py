import sys

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
        "emailtemplates",
    )
    settings.MIDDLEWARE = (
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    )
    settings.DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
    settings.TEMPLATES = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "OPTIONS": {
                "context_processors": [
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ],
            },
        }
    ]
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=3)
    failures = test_runner.run_tests(["emailtemplates"])
    sys.exit(bool(failures))
