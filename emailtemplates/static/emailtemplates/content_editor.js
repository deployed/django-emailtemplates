/**
 * Editor of the content of an email template, see `emailtemplates.widgets.EmailContentEditor`:
 * rich text (TinyMCE) or HTML code (CodeMirror), switched with the buttons above it without
 * saving. The options come from the `data-content-editor` attribute the widget writes.
 *
 * Next to the editor, the live preview: the email as it would be sent, rendered by the
 * server with the unsaved content, subject, preheader and layout of the form.
 *
 * Also the "emailtemplates" TinyMCE plugin: the Variables and Blocks buttons, template tags
 * shown as chips removed as a whole, and blocks expanded into a preview with example data
 * when clicked.
 */
(function () {
    "use strict";

    // Django template tags and variables.
    var TEMPLATE_TAG_RE = /\{%[\s\S]*?%\}|\{\{[\s\S]*?\}\}/g;
    // The same lists as emailtemplates.rich_text: elements that may not contain text, where
    // the browser, and so the rich text editor, would move template tags out of their place.
    var NO_TEXT_ELEMENTS = ["table", "thead", "tbody", "tfoot", "tr", "ul", "ol"];
    var VOID_ELEMENTS = ["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"];
    var EXTENDS_TAG_RE = /\{%\s*extends[\s%]/;

    /** Template tags placed between table rows, cells or list items, see misplaced_template_tags(). */
    function misplacedTemplateTags(html) {
        var token = /<!--[\s\S]*?-->|<(\/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>|([^<]+)/g;
        var openElements = [];
        var misplaced = [];
        var match;
        while ((match = token.exec(html)) !== null) {
            if (match[2]) {
                var name = match[2].toLowerCase();
                if (match[1]) {
                    var index = openElements.lastIndexOf(name);
                    if (index !== -1) {
                        openElements.length = index;
                    }
                } else if (VOID_ELEMENTS.indexOf(name) === -1) {
                    openElements.push(name);
                }
            } else if (match[3] && NO_TEXT_ELEMENTS.indexOf(openElements[openElements.length - 1]) !== -1) {
                misplaced = misplaced.concat(match[3].match(TEMPLATE_TAG_RE) || []);
            }
        }
        return misplaced;
    }

    /** Why the content would not survive the rich text editor, see rich_text_problem(). */
    function richTextProblem(html, problems) {
        if (EXTENDS_TAG_RE.test(html)) {
            return problems.extends;
        }
        var misplaced = misplacedTemplateTags(html);
        return misplaced.length ? problems.misplaced.replace("%(tags)s", misplaced.join(", ")) : "";
    }

    function registerPlugin() {
        if (!window.tinymce || tinymce.PluginManager.get("emailtemplates")) {
            return;
        }
        tinymce.PluginManager.add("emailtemplates", function (editor) {
            var options = editor.options;
            options.register("emailtemplates_variables", {processor: "array", default: []});
            options.register("emailtemplates_blocks", {processor: "array", default: []});
            options.register("emailtemplates_blocks_url", {processor: "string", default: ""});
            options.register("emailtemplates_labels", {processor: "object", default: {}});
            var labels = options.get("emailtemplates_labels");

            var variables = options.get("emailtemplates_variables");
            if (variables.length) {
                editor.ui.registry.addMenuButton("emailtemplates_variables", {
                    text: labels.variables,
                    fetch: function (callback) {
                        callback(variables.map(function (variable) {
                            var tag = "{{ " + variable.name + " }}";
                            return {
                                type: "menuitem",
                                text: variable.description ? tag + " - " + variable.description : tag,
                                onAction: function () {
                                    editor.insertContent(editor.dom.encode(tag));
                                }
                            };
                        }));
                    }
                });
            }

            var blocks = options.get("emailtemplates_blocks");
            if (blocks.length) {
                editor.ui.registry.addMenuButton("emailtemplates_blocks", {
                    text: labels.blocks,
                    fetch: function (callback) {
                        callback(blocks.map(function (block) {
                            return {
                                type: "menuitem",
                                text: block.label,
                                onAction: function () {
                                    editor.insertContent(block.html);
                                }
                            };
                        }));
                    }
                });
            }

            // A click on a block shows it rendered with example data, a second click hides it.
            // The preview is data-mce-bogus="all": the editor leaves it out of the saved content.
            var blocksUrl = options.get("emailtemplates_blocks_url");
            var previews = null;
            editor.on("click", function (event) {
                var block = event.target.closest && event.target.closest("div.emailtemplates-block");
                if (!blocksUrl || !block || event.target.closest(".emailtemplates-block-preview")) {
                    return;
                }
                var shown = block.querySelector(".emailtemplates-block-preview");
                if (shown) {
                    editor.undoManager.ignore(function () {
                        shown.remove();
                    });
                    return;
                }
                var name = (block.textContent.match(/\{\{\s*(\w+)\s*\}\}/) || [])[1];
                var loaded = previews ? Promise.resolve(previews) : fetch(blocksUrl, {credentials: "same-origin"})
                    .then(function (response) {
                        return response.json();
                    })
                    .then(function (data) {
                        previews = data;
                        return data;
                    });
                loaded.then(function (data) {
                    editor.undoManager.ignore(function () {
                        var preview = editor.dom.create("div", {
                            "class": "emailtemplates-block-preview",
                            "data-mce-bogus": "all"
                        });
                        preview.innerHTML = data[name] || "";
                        block.appendChild(preview);
                    });
                });
            });
        });
    }

    // Fields of the form, besides the content, the preview is rendered with.
    var PREVIEW_FIELDS = ["subject", "preheader", "layout"];
    // How long the preview waits after the last change before it is updated.
    var PREVIEW_DELAY = 800;

    /**
     * The live preview of `container`: updated now and, through the returned function,
     * shortly after a change. While the content cannot be rendered, e.g. a template tag is
     * being typed, the last preview stays, with the error below it.
     */
    function livePreview(container, options, getContent, editorInput) {
        var pane = container.querySelector(".emailtemplates-content-editor__preview");
        var form = container.closest("form");
        if (!pane || !form || !options.previewUrl) {
            return function () {};
        }
        var iframe = pane.querySelector("iframe");
        var errorText = pane.querySelector(".emailtemplates-content-editor__preview-error");
        var timer = null;
        var latest = 0;

        function refresh() {
            var data = new FormData();
            data.append("content", getContent());
            data.append("content_editor", editorInput.value);
            data.append("csrfmiddlewaretoken", form.elements.csrfmiddlewaretoken.value);
            PREVIEW_FIELDS.forEach(function (name) {
                if (form.elements[name]) {
                    data.append(name, form.elements[name].value);
                }
            });
            var request = ++latest;
            fetch(options.previewUrl, {method: "POST", body: data, credentials: "same-origin"})
                .then(function (response) {
                    return response.json();
                })
                .then(function (result) {
                    if (request !== latest) {
                        return;  // a newer preview is on its way
                    }
                    errorText.textContent = result.error ? options.previewError + " " + result.error : "";
                    if (!result.error) {
                        iframe.srcdoc = result.html;
                    }
                });
        }

        function schedule() {
            clearTimeout(timer);
            timer = setTimeout(refresh, PREVIEW_DELAY);
        }

        form.addEventListener("input", function (event) {
            if (PREVIEW_FIELDS.indexOf(event.target.name) !== -1) {
                schedule();
            }
        });
        form.addEventListener("change", function (event) {
            if (PREVIEW_FIELDS.indexOf(event.target.name) !== -1) {
                schedule();
            }
        });
        refresh();
        return schedule;
    }

    function ContentEditor(container) {
        var options = JSON.parse(container.dataset.contentEditor);
        var textarea = container.querySelector("textarea");
        var editorInput = container.querySelector("input[type=hidden]");
        var buttons = container.querySelectorAll("[data-editor]");
        var problemText = container.querySelector(".emailtemplates-content-editor__problem");
        var codeMirror = null;
        var updatePreview = function () {};

        function getContent() {
            var editor = window.tinymce && tinymce.get(textarea.id);
            if (editor && editor.initialized) {
                return editor.getContent();
            }
            return codeMirror ? codeMirror.getValue() : textarea.value;
        }

        function startCode() {
            codeMirror = CodeMirror.fromTextArea(textarea, options.code);
            codeMirror.on("change", function () {
                updatePreview();
            });
        }

        function stopCode() {
            if (codeMirror) {
                codeMirror.toTextArea();
                codeMirror = null;
            }
        }

        function startRichText() {
            // template tags are shown as chips, removed as a whole and kept as typed
            tinymce.init(Object.assign({}, options.richText, {
                target: textarea,
                noneditable_regexp: [TEMPLATE_TAG_RE]
            })).then(function (editors) {
                editors[0].on("input change undo redo ExecCommand", function () {
                    updatePreview();
                });
            });
        }

        function stopRichText() {
            var editor = tinymce.get(textarea.id);
            if (editor) {
                editor.save();
                editor.remove();
            }
        }

        function show(name, problem) {
            editorInput.value = name;
            buttons.forEach(function (button) {
                button.setAttribute("aria-pressed", String(button.dataset.editor === name));
            });
            if (problemText) {
                problemText.textContent = problem || "";
            }
        }

        function switchTo(name) {
            if (name === editorInput.value) {
                return;
            }
            if (name === "rich") {
                stopCode();
                var problem = richTextProblem(textarea.value, options.problems);
                if (problem) {
                    startCode();
                    show("html", problem);
                    return;
                }
                startRichText();
            } else {
                stopRichText();
                startCode();
            }
            show(name);
            updatePreview();
        }

        buttons.forEach(function (button) {
            button.addEventListener("click", function () {
                switchTo(button.dataset.editor);
            });
        });
        if (container.dataset.start === "rich") {
            startRichText();
        } else {
            startCode();
        }
        show(container.dataset.start, container.dataset.problem);
        updatePreview = livePreview(container, options, getContent, editorInput);
    }

    function init() {
        registerPlugin();
        document.querySelectorAll("[data-content-editor]").forEach(ContentEditor);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
