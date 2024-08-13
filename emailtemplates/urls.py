import django
from packaging.version import parse


django_version = parse(django.get_version())

if django_version < parse('4.0'):
    from django.conf.urls import url
else:
    from django.urls import re_path as url

from emailtemplates.views import email_preview_view, send_mass_email_view

urlpatterns = [
    url(r"^email-preview/(?P<pk>\d+)/$", email_preview_view, name="email_preview"),
    url(
        r"^send-mass-email/(?P<pk>\d+)/$", send_mass_email_view, name="send_mass_email"
    ),
]
