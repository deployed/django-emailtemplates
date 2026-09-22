/**
 * Syntax highlighting for the HTML and CSS fields of the admin.
 *
 * No line numbers, no gutter and no error marking: the header and the footer are two
 * halves of one document, so a tag that looks unclosed in one of them is closed in the
 * other and marking it red would be wrong.
 */
(function () {
    "use strict";

    var MODES = {
        html: {name: "xml", htmlMode: true, matchClosing: false},
        css: "css"
    };

    function init() {
        if (typeof CodeMirror === "undefined") {
            return;
        }
        var textareas = document.querySelectorAll("textarea[data-editor-mode]");
        Array.prototype.forEach.call(textareas, function (textarea) {
            CodeMirror.fromTextArea(textarea, {
                mode: MODES[textarea.dataset.editorMode] || MODES.html,
                lineNumbers: false,
                lineWrapping: true,
                indentUnit: 2,
                tabSize: 2
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
