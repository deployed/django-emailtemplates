# coding=utf-8
import json

from django import forms


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
