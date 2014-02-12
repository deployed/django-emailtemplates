# coding=utf-8
from .email import EmailFromTemplate


def send_email(name, ctx_dict, send_to=None, subject=u'Subject', prefix='emailtemplates', **kwargs):
    """
    Shortcut function for EmailFromTemplate class

    @return: None
    """
    eft = EmailFromTemplate(prefix=prefix, name=name)
    eft.subject = subject
    eft.context = ctx_dict
    eft.get_object()
    eft.render_message()
    eft.send_email(send_to=send_to, **kwargs)
