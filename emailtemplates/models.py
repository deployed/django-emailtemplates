# coding=utf-8
import os
from django.conf import settings
from django.db import models
from django.template.utils import get_app_template_dirs
from django.utils.translation import ugettext_lazy as _

try:
    from django.utils.timezone import now
except ImportError:
    from datetime import datetime

    now = datetime.now


def get_template_choices(templates_dir_name='emailtemplates', suffix='.html'):
    """
    returns list of html templates from emailtemplates/*/
    """
    templates_list = []

    try:
        # for Django < 1.8
        template_dirs = settings.TEMPLATE_DIRS
    except AttributeError:
        # for Django >= 1.8
        template_dirs = []

        for template_setting in settings.TEMPLATES:
            template_dirs += template_setting['DIRS']

        template_dirs = tuple(template_dirs)

    for template_dir_path in (template_dirs + get_app_template_dirs('templates')):
        path = os.path.join(template_dir_path, templates_dir_name)

        for root, dirs, files in os.walk(path):
            for name in files:
                filename = os.path.join(root, name).replace(path, '')
                if filename.endswith(suffix):
                    templates_list.append(filename[1:])

    return [(template_name, template_name) for template_name in list(set(templates_list))]


class EmailTemplate(models.Model):
    """
    Model to store email template.
    """
    title = models.CharField(_(u'template'), max_length=255, choices=get_template_choices())
    subject = models.CharField(_(u'subject'), max_length=255, blank=True)
    content = models.TextField(_(u'content'))
    language = models.CharField(_(u'language'), max_length=10, choices=settings.LANGUAGES,
                                default=settings.LANGUAGE_CODE)
    created = models.DateTimeField(default=now)
    modified = models.DateTimeField(default=now)

    class Meta:
        unique_together = (('title', 'language'),)

    def __unicode__(self):
        return u'%s -> %s' % (self.title, self.language)
