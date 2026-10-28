# coding=utf-8
import logging

from django.template.loader import get_template, render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class AlreadyRegistered(Exception):
    pass


class NotRegistered(Exception):
    pass


class HelpContext(object):
    """
    Provides helpers methods for displaying help context keys (descriptions) and values (examples).
    """

    def __init__(self, help_context):
        self.help_context = help_context or {}

    def get_help_keys(self):
        """
        Returns dict of help_context keys (description texts used in `EmailRegistry.register()` method).
        """
        help_keys = {}
        for k, v in self.help_context.items():
            if isinstance(v, tuple):
                help_keys[k] = v[0]
            else:
                help_keys[k] = v
        return help_keys

    def get_help_values(self):
        """
        Returns dict of help_context values (example values submitted in `EmailRegistry.register()` method).
        """
        help_values = {}
        for k, v in self.help_context.items():
            if isinstance(v, tuple) and len(v) == 2:
                help_values[k] = v[1]
            else:
                help_values[k] = "<%s>" % k
        return help_values


class Block(object):
    """
    Part of an email rendered from a template file of its own, e.g. a table with order
    details. Site Admins place it in the content as ``{{ name }}`` and cannot change it.

    The block template gets the context of the email, updated with `context`.
    """

    def __init__(self, name, label, template_name, context=None):
        self.name = name
        self.label = label
        self.template_name = template_name
        self.context = context or {}

    def render(self, context):
        return mark_safe(
            get_template(self.template_name).render(dict(context, **self.context))
        )

    def as_html(self):
        """
        How the block is placed in the content: the variable in a <div>, so that it never
        ends up inside a paragraph, labeled for the rich text editor.
        """
        return format_html(
            '<div class="emailtemplates-block" data-label="{}">{{{{ {} }}}}</div>',
            self.label,
            self.name,
        )


class RegistrationItem(object):
    def __init__(
        self,
        path,
        help_text="",
        help_context=None,
        name="",
        subject="",
        blocks=None,
        preview_context=None,
        preheader="",
    ):
        self.name = name or path
        self.path = path
        self.help_text = help_text
        self.subject = subject
        self.preheader = preheader
        self.help_context_obj = HelpContext(help_context)
        self.blocks = [
            Block(block_name, *definition)
            for block_name, definition in (blocks or {}).items()
        ]
        self.preview_context = preview_context

    def get_blocks_context(self, context):
        """
        The blocks for the context of an email: rendered with `context` when the template
        uses them - a callable in the context is called only when the template uses it.
        Variables already in `context` are not overridden.
        """

        def renderer(block):
            return lambda: block.render(context)

        return {
            block.name: renderer(block)
            for block in self.blocks
            if block.name not in context
        }

    @property
    def help_context(self):
        return self.help_context_obj.get_help_keys()

    def _context_key(self, key):
        return "<b>{{ %s }}</b>" % key

    def context_description(self):
        help_text_item = lambda k, v: (
            "%s - %s" % (self._context_key(k), v) if v else "%s" % self._context_key(k)
        )
        return "<br/>".join(
            [
                help_text_item(k, v)
                for (k, v) in sorted(self.help_context_obj.get_help_keys().items())
            ]
        )

    def blocks_description(self):
        return "<br/>".join(
            "%s - %s" % (self._context_key(block.name), block.label)
            for block in self.blocks
        )

    def as_form_help_text(self):
        item_help_text = (
            _("<b>USAGE: %s</b>") % self.help_text if self.help_text else ""
        )
        item_help_context = (
            _("<b>CONTEXT:</b><br/>%s") % self.context_description()
            if self.help_context_obj.get_help_keys()
            else ""
        )
        parts = [item_help_text, item_help_context]
        if self.blocks:
            parts.append(_("<b>BLOCKS:</b><br/>%s") % self.blocks_description())
        return "<br/>".join(parts)

    def as_form_choice(self):
        return self.path, self.name

    def get_help_content(self):
        return self.help_context_obj.get_help_values()

    def get_preview_context(self):
        """
        Context of the email preview: the example values of `help_context`, updated with
        `preview_context` (a dict, or a callable returning one).
        """
        context = self.get_help_content()
        preview_context = self.preview_context
        if callable(preview_context):
            preview_context = preview_context()
        context.update(preview_context or {})
        return context


class EmailTemplateRegistry(object):
    def __init__(self):
        self._registry = {}

    def register(
        self,
        path,
        name="",
        help_text=None,
        help_context=None,
        subject="",
        blocks=None,
        preview_context=None,
        preheader="",
    ):
        """
        Registers email template.

        Example usage:
            email_templates.register('hello_template.html', help_text='Hello template',
                help_context={'username': 'Name of user in hello expression'})

        :param name: Template name [optional]
        :param path: Template file path. It will become immutable registry lookup key.
        :param help_text: Help text to describe template in admin site
        :param help_context: Dictionary of possible keys used in the context and description of their content
        :param subject: Default subject of email [optional]
        :param preheader: Default preheader of email - the text shown next to the subject
            in the inbox, see `EmailTemplate.preheader` [optional]
        :param blocks: Dictionary of blocks the template may use, see `Block` [optional]
        :param preview_context: Context of the email preview in the admin, a dict or a
            callable returning one, e.g. lambda: {'order': Order.objects.first()}. Updates
            the example values of `help_context` [optional]

        `help_context` items values may be strings or tuples of two strings. If strings, then email template preview
        will use variable names to fill context, otherwise the second tuple element will become example value.

        `blocks` maps a name to a tuple (label, template name) or (label, template name,
        extra context), e.g. {'order_details': ('Order details', 'emails/order.html')}.
        The template is rendered with the context of the email and placed in it as
        ``{{ order_details }}``.

        If an email template is already registered, this will raise AlreadyRegistered.
        """
        if path in self._registry:
            raise AlreadyRegistered("The template %s is already registered" % path)
        self._registry[path] = RegistrationItem(
            path,
            help_text,
            help_context,
            name=name,
            subject=subject,
            blocks=blocks,
            preview_context=preview_context,
            preheader=preheader,
        )
        logger.debug("Registered email template %s", path)

    def is_registered(self, path):
        return path in self._registry

    def get_registration(self, path):
        """
        Returns registration item for specified path.

        If an email template is not registered, this will raise NotRegistered.
        """
        if not self.is_registered(path):
            raise NotRegistered("Email template not registered")
        return self._registry[path]

    def get_name(self, path):
        return self.get_registration(path).name

    def get_help_text(self, path):
        return self.get_registration(path).help_text

    def get_help_context(self, path):
        return self.get_registration(path).help_context

    def get_help_content(self, path):
        return self.get_registration(path).get_help_content()

    def get_preview_context(self, path):
        return self.get_registration(path).get_preview_context()

    def get_subject(self, path):
        return self.get_registration(path).subject

    def get_preheader(self, path):
        return self.get_registration(path).preheader

    def get_blocks(self, path):
        return self.get_registration(path).blocks

    def get_blocks_context(self, path, context):
        """
        Blocks of a template for its context, see `RegistrationItem.get_blocks_context()`.
        Empty for unregistered templates.
        """
        if not self.is_registered(path):
            return {}
        return self.get_registration(path).get_blocks_context(context)

    def registration_items(self):
        return self._registry.values()

    def email_template_choices(self):
        """
        Returns list of choices that can be used in email template form field choices.
        """
        return [item.as_form_choice() for item in self.registration_items()]

    def get_form_help_text(self, path):
        """
        Returns text that can be used as form help text for creating email templates.
        """
        try:
            form_help_text = render_to_string(
                "admin/emailtemplates/_helptext.html",
                context={"registration_item": self.get_registration(path)},
            )
        except NotRegistered:
            form_help_text = ""
        return form_help_text


# Global object for singleton registry of email templates
email_templates = EmailTemplateRegistry()
