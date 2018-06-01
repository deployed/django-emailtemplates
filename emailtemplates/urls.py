from django.conf.urls import url

from emailtemplates.views import email_preview_view, send_mass_email_view

urlpatterns = [
    url(r'^email-preview/(?P<pk>\d+)/$', email_preview_view, name='email_preview'),
    url(r'^send-mass-email/(?P<pk>\d+)/$', send_mass_email_view, name='send_mass_email'),
]
