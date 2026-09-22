/**
 * Starts CodeMirror on every textarea rendered by `CodeEditorTextarea`.
 *
 * The options are read from the `data-code-editor` attribute the widget writes, so how the
 * editors behave is decided in `widgets.py` and nothing here has to change for it.
 */
(function () {
    "use strict";

    function init() {
        document.querySelectorAll("textarea[data-code-editor]").forEach(function (textarea) {
            CodeMirror.fromTextArea(textarea, JSON.parse(textarea.dataset.codeEditor));
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
