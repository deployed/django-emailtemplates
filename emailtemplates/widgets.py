# coding=utf-8
from django import forms


class CodeEditorTextarea(forms.Textarea):
    """
    Textarea with syntax highlighting. `mode` is "html" or "css".
    """

    def __init__(self, mode="html", attrs=None):
        defaults = {"rows": 12, "data-editor-mode": mode}
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
