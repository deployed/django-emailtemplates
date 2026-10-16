# coding=utf-8
import json
import re

from django import forms
from django.utils.translation import gettext_lazy as _

from emailtemplates.rich_text import (
    CHANGED_PROBLEM,
    EXTENDS_PROBLEM,
    MISPLACED_PROBLEM,
    rich_text_problem,
    tinymce_js_url,
)

PREVIEW_ERROR = _("The preview could not be updated:")


class CodeEditorTextarea(forms.Textarea):
    """
    Textarea with syntax highlighting. `mode` is "html" or "css".

    Everything the editor does is decided here: `OPTIONS` and `MODES` are handed to
    CodeMirror as they are, `code_editor.js` only reads them off the rendered attribute.

    No line numbers, no gutter and no error marking: the header and the footer are two
    halves of one document, so a tag that looks unclosed in one of them is closed in the
    other and marking it red would be wrong.
    """

    OPTIONS = {
        "lineNumbers": False,
        "lineWrapping": True,
        "indentUnit": 2,
        "tabSize": 2,
    }
    MODES = {
        "html": {"name": "xml", "htmlMode": True, "matchClosing": False},
        "css": {"name": "css"},
    }

    def __init__(self, mode="html", attrs=None):
        options = dict(self.OPTIONS, mode=self.MODES[mode])
        defaults = {"rows": 12, "data-code-editor": json.dumps(options)}
        defaults.update(attrs or {})
        super(CodeEditorTextarea, self).__init__(attrs=defaults)

    class Media:
        css = {
            "all": (
                "emailtemplates/codemirror/codemirror.min.css",
                "emailtemplates/code_editor.css",
            )
        }
        js = (
            "emailtemplates/codemirror/codemirror.min.js",
            "emailtemplates/codemirror/mode/xml/xml.min.js",
            "emailtemplates/codemirror/mode/css/css.min.js",
            "emailtemplates/code_editor.js",
        )


class EmailFrameWidget(forms.MultiWidget):
    """
    Header and footer edited as a single field: two editors drawn as one box, split by a
    divider standing for the content of the email template. What is above the divider is
    saved as the header, what is below it as the footer.
    """

    template_name = "emailtemplates/widgets/email_frame.html"

    def __init__(self, attrs=None):
        widgets = [CodeEditorTextarea(), CodeEditorTextarea(attrs={"rows": 6})]
        super(EmailFrameWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        return list(value) if value else ["", ""]


class EmailContentEditor(CodeEditorTextarea):
    """
    Content of an email template, edited as rich text or as HTML code, switched with the
    buttons above the editor without saving (``content_editor.js``).

    `rich_text_config` - TinyMCE configuration, see `emailtemplates.rich_text`; without it
    the content is edited as HTML code only. Content that would not survive the rich text
    editor, see `rich_text_problem()`, starts in the HTML code editor and cannot be
    switched to rich text.
    `preview_url` - URL rendering the email as it would be sent, shown next to the editor
    and updated while the content is edited, see `EmailTemplatePreviewView`.
    """

    template_name = "emailtemplates/widgets/content_editor.html"

    def __init__(self, rich_text_config=None, preview_url="", attrs=None):
        super(EmailContentEditor, self).__init__(
            attrs=dict({"rows": 24}, **attrs or {})
        )
        # the code editor is started by content_editor.js, not by code_editor.js
        self.code_editor_options = self.attrs.pop("data-code-editor")
        self.rich_text_config = rich_text_config
        self.preview_url = preview_url

    def get_context(self, name, value, attrs):
        context = super(EmailContentEditor, self).get_context(name, value, attrs)
        rich_text = self.rich_text_config is not None
        # the value rendered, e.g. the submitted one when the form has errors
        problem = rich_text_problem(value) if rich_text else ""
        context["editor"] = {
            "rich_text": rich_text,
            "start": "rich" if rich_text and not problem else "html",
            "problem": problem,
            "preview_url": self.preview_url,
            "width": self.get_editor_width(),
            "options": json.dumps(
                {
                    "code": json.loads(self.code_editor_options),
                    "richText": self.rich_text_config,
                    "previewUrl": self.preview_url,
                    "previewError": str(PREVIEW_ERROR),
                    "problems": {
                        "extends": str(EXTENDS_PROBLEM),
                        "misplaced": str(MISPLACED_PROBLEM),
                        "changed": str(CHANGED_PROBLEM),
                    },
                }
            ),
        }
        return context

    def get_editor_width(self):
        """
        The width in pixels set for the rich text editor (``"width": 1000`` or ``"1000px"`` in
        EMAILTEMPLATES_RICH_TEXT_CONFIG): the least width of the editor column, so that the
        preview goes below the editor when both do not fit side by side. None otherwise,
        e.g. for ``"100%"``.
        """
        width = (self.rich_text_config or {}).get("width")
        if isinstance(width, (int, float)) and not isinstance(width, bool):
            return int(width)
        if isinstance(width, str) and re.fullmatch(r"\s*\d+(\.\d+)?\s*px\s*", width):
            return int(float(width.strip()[:-2]))
        return None

    @property
    def media(self):
        js = list(CodeEditorTextarea.Media.js)
        js.remove("emailtemplates/code_editor.js")
        if self.rich_text_config is not None:
            js.insert(0, tinymce_js_url())
        return forms.Media(
            css=CodeEditorTextarea.Media.css,
            js=js + ["emailtemplates/content_editor.js"],
        )
