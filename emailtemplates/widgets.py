# coding=utf-8
import json

from django import forms

from emailtemplates.rich_text import (
    EXTENDS_PROBLEM,
    MISPLACED_PROBLEM,
    tinymce_js_url,
)


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
    the content is edited as HTML code only.
    `rich_text_problem` - why the content would not survive the rich text editor, which
    then starts as the HTML code editor and cannot be switched to rich text.

    The editor the submitted content comes from is sent as ``<name>_editor``, see
    `submitted_editor()`.
    """

    template_name = "emailtemplates/widgets/content_editor.html"

    def __init__(self, rich_text_config=None, rich_text_problem="", attrs=None):
        super(EmailContentEditor, self).__init__(
            attrs=dict({"rows": 24}, **attrs or {})
        )
        # the code editor is started by content_editor.js, not by code_editor.js
        self.code_editor_options = self.attrs.pop("data-code-editor")
        self.rich_text_config = rich_text_config
        self.rich_text_problem = rich_text_problem

    def get_context(self, name, value, attrs):
        context = super(EmailContentEditor, self).get_context(name, value, attrs)
        rich_text = self.rich_text_config is not None
        context["editor"] = {
            "rich_text": rich_text,
            "start": "rich" if rich_text and not self.rich_text_problem else "html",
            "problem": self.rich_text_problem,
            "options": json.dumps(
                {
                    "code": json.loads(self.code_editor_options),
                    "richText": self.rich_text_config,
                    "problems": {
                        "extends": str(EXTENDS_PROBLEM),
                        "misplaced": str(MISPLACED_PROBLEM),
                    },
                }
            ),
        }
        return context

    @staticmethod
    def submitted_editor(data, name):
        """
        "rich" or "html": the editor the submitted content of the field `name` comes from.
        """
        return "rich" if data.get("%s_editor" % name) == "rich" else "html"

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
