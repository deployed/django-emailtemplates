# coding=utf-8
"""
Rich text editor for email templates: TinyMCE, bundled with django-tinymce (an optional
dependency: ``pip install django-emailtemplates[tinymce]``, ``"tinymce"`` in
``INSTALLED_APPS`` and ``EMAILTEMPLATES_RICH_TEXT = True``).

The editor is started by ``content_editor.js``, which switches the content between it and
the HTML code editor without saving, see `emailtemplates.widgets.EmailContentEditor`. This
module builds its TinyMCE configuration and checks which content it can edit.
"""

import html
import re
from html.parser import HTMLParser

from django.conf import settings
from django.templatetags.static import static
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from emailtemplates.models import EXTENDS_TAG_RE

try:
    import tinymce.settings as tinymce_settings
    from tinymce.widgets import TinyMCE
except ImportError:  # the optional dependency is missing, see `rich_text_available()`
    tinymce_settings = TinyMCE = None


def rich_text_available():
    """
    The rich text editor is opted into with ``EMAILTEMPLATES_RICH_TEXT = True`` and needs
    django-tinymce. Without it the content is edited as HTML code only, so projects having
    django-tinymce for other reasons keep that editor.
    """
    return getattr(settings, "EMAILTEMPLATES_RICH_TEXT", False) and TinyMCE is not None


# Django template tags and variables.
TEMPLATE_TAG_RE = re.compile(r"{%.*?%}|{{.*?}}", re.DOTALL)
# Elements that may not contain text. A browser moves text found there out of the element,
# so the rich text editor would move template tags written there, e.g. a {% for %} loop
# between table rows ends up before the table.
NO_TEXT_ELEMENTS = {"table", "thead", "tbody", "tfoot", "tr", "ul", "ol"}
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}

# Why content would not survive the rich text editor, see `rich_text_problem()`; the same
# messages are shown by content_editor.js when switching to the editor.
EXTENDS_PROBLEM = gettext_lazy(
    "The content uses the {% extends %} tag, which the rich text editor cannot keep. "
    "Edit it as HTML code."
)
MISPLACED_PROBLEM = gettext_lazy(
    "The rich text editor would move %(tags)s out of their place: they sit between table "
    "rows, table cells or list items. Edit it as HTML code."
)
# shown by content_editor.js only, when the editor changed template tags while loading
CHANGED_PROBLEM = gettext_lazy(
    "The rich text editor would change %(tags)s. Edit it as HTML code."
)

# What the editor is allowed to produce, chosen for emails: no images pasted as data URIs
# (most email clients block them), formatting as inline styles, URLs kept as typed.
RICH_TEXT_CONFIG = {
    "height": 500,
    # the width of the editor column, which changes with the window; TinyMCE would keep
    # the width of the textarea it replaces and run into the preview next to it
    "width": "100%",
    "menubar": False,
    "branding": False,
    "promotion": False,
    "plugins": "autolink,lists,link,table,code,emailtemplates",
    # the variables and the blocks first, and no button hidden behind "..."
    "toolbar": (
        "emailtemplates_variables emailtemplates_blocks | undo redo | blocks | bold "
        "italic underline forecolor | alignleft aligncenter alignright | bullist numlist "
        "| link table | removeformat code"
    ),
    "toolbar_mode": "wrap",
    "block_formats": "Paragraph=p; Heading 1=h1; Heading 2=h2; Heading 3=h3",
    # links may point at variables, e.g. href="{{ activation_url }}", which TinyMCE would
    # otherwise rewrite as relative to the admin page
    "convert_urls": False,
    "relative_urls": False,
    "remove_script_host": False,
    # encode only <, > and &, so quotes and national characters stay readable
    "entity_encoding": "raw",
    "paste_data_images": False,
    # blocks (see `emailtemplates.registry.Block`) are moved or removed as a whole
    "noneditable_class": "emailtemplates-block",
}

# Styles of the content of the editor: the look of blocks and of template tags shown as
# chips; restyled by overriding the static file or with "content_css" in
# EMAILTEMPLATES_RICH_TEXT_CONFIG.
CONTENT_CSS = "emailtemplates/rich_text_content.css"

# Options of the project's TINYMCE_DEFAULT_CONFIG kept in the email editor. Everything else
# there is meant for the editors of the website, not for emails.
PROJECT_OPTIONS = ("license_key", "language", "directionality")


def rich_text_config(variables=(), blocks=(), styles="", blocks_url=""):
    """
    TinyMCE configuration of the email editor, see `RICH_TEXT_CONFIG`.

    `variables` - (name, description) pairs of the template context, offered by the
    "Variables" button, which inserts them as ``{{ name }}``.
    `blocks` - `emailtemplates.registry.Block` objects, offered by the "Blocks" button.
    `styles` - CSS of the email layout, so that the content looks as it does in the email.
    `blocks_url` - URL of the blocks rendered with example data, shown when a block in
    the editor is clicked.

    Settings: ``EMAILTEMPLATES_RICH_TEXT_CONFIG`` - TinyMCE options merged over
    `RICH_TEXT_CONFIG`. When they define ``style_formats`` (e.g. a "Button" format adding
    the class of buttons of the layout to a link), the toolbar gets the "Formats" button.
    """
    config = dict(
        RICH_TEXT_CONFIG, **getattr(settings, "EMAILTEMPLATES_RICH_TEXT_CONFIG", {})
    )
    if config.get("style_formats") and "styles" not in config["toolbar"]:
        config["toolbar"] = config["toolbar"].replace(
            "| blocks |", "| blocks styles |", 1
        )
    config.setdefault("content_css", ["default", static(CONTENT_CSS)])
    if styles:
        config["content_style"] = config.get("content_style", "") + styles
    # the language as django-tinymce works it out; the rest of the project's
    # TINYMCE_DEFAULT_CONFIG is meant for the editors of the website
    project_config = TinyMCE().get_mce_config({"id": "emailtemplates"})
    for key in PROJECT_OPTIONS:
        if key in project_config and key not in config:
            config[key] = project_config[key]
    config.update(
        emailtemplates_variables=[
            {"name": name, "description": str(description or "")}
            for name, description in variables
        ],
        emailtemplates_blocks=[
            {"name": block.name, "label": str(block.label), "html": block.as_html()}
            for block in blocks
        ],
        emailtemplates_blocks_url=blocks_url,
        emailtemplates_labels={
            "variables": _("Variables"),
            "blocks": _("Blocks"),
        },
    )
    return config


def tinymce_js_url():
    return tinymce_settings.get_js_url()


def unescape_template_tags(content):
    """
    Reverts what the rich text editor does to Django template syntax typed as text: it
    encodes ``>``, ``<``, ``&`` and non-breaking spaces, so ``{% if count > 1 %}`` would be
    saved as ``{% if count &gt; 1 %}``, which is not a valid template.

    Applied to the content from either editor: Django template syntax needs no HTML
    entities, so the content does not depend on which editor it was saved from.
    """

    def unescape(match):
        return html.unescape(match.group()).replace("\xa0", " ")

    return TEMPLATE_TAG_RE.sub(unescape, content)


class _MisplacedTemplateTagsFinder(HTMLParser):
    def __init__(self):
        super(_MisplacedTemplateTagsFinder, self).__init__(convert_charrefs=True)
        self.open_elements = []
        self.misplaced = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_ELEMENTS:
            self.open_elements.append(tag)

    def handle_endtag(self, tag):
        if tag in self.open_elements:
            while self.open_elements.pop() != tag:
                pass

    def handle_data(self, data):
        if self.open_elements and self.open_elements[-1] in NO_TEXT_ELEMENTS:
            self.misplaced.extend(TEMPLATE_TAG_RE.findall(data))


def misplaced_template_tags(content):
    """
    Template tags the rich text editor would move: those placed directly in a table, a table
    row or a list, between the cells or the list items, see `NO_TEXT_ELEMENTS`.
    """
    finder = _MisplacedTemplateTagsFinder()
    finder.feed(content or "")
    finder.close()
    return finder.misplaced


def rich_text_problem(content):
    """
    Why the content would not survive the rich text editor, or an empty string. The
    editor opens on content without problems; content_editor.js checks the same when
    switching to it.
    """
    if EXTENDS_TAG_RE.search(content or ""):
        return str(EXTENDS_PROBLEM)
    misplaced = misplaced_template_tags(content)
    if misplaced:
        return str(MISPLACED_PROBLEM) % {"tags": ", ".join(misplaced)}
    return ""
