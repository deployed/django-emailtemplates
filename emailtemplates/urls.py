from django.urls import re_path as url

from emailtemplates.views import (
    email_layout_preview_view,
    email_preview_view,
    send_mass_email_view,
)

urlpatterns = [
    url(r"^email-preview/(?P<pk>\d+)/$", email_preview_view, name="email_preview"),
    url(
        r"^email-layout-preview/(?P<pk>\d+)/$",
        email_layout_preview_view,
        name="email_layout_preview",
    ),
    url(
        r"^send-mass-email/(?P<pk>\d+)/$", send_mass_email_view, name="send_mass_email"
    ),
]
