django-emailtemplates
*********************

About
=====

Django app for sending emails rendered from Django templates. Developers ship a default
template for every email as a file; Site Admins can override its subject and content per
language in the Admin Panel, without a deployment. When no override exists in the
database, the file is used.

Site Admins edit the content in a rich text editor (or as HTML code) and insert the
variables of the email context from a toolbar menu. Every email is sent as HTML together
with its plain text version, generated from the HTML.

Requirements: Python 3.10+, Django 4.0+.

Installation
============

::

    pip install django-emailtemplates[tinymce]

The ``tinymce`` extra installs `django-tinymce`_ for the rich text editor; without it the
content is edited as HTML code. ``"tinymce"`` must be added to ``INSTALLED_APPS`` too, and
the editor turned on with ``EMAILTEMPLATES_RICH_TEXT = True``.

.. _django-tinymce: https://github.com/jazzband/django-tinymce

Add the app and its URLs (needed for the admin previews and the mass email button)::

    # settings.py
    INSTALLED_APPS = [
        ...
        "tinymce",
        "emailtemplates",
    ]

    # urls.py
    urlpatterns = [
        ...
        path("emailtemplates/", include("emailtemplates.urls")),
    ]

Then run ``python manage.py migrate``.

Usage
=====

1. Write the default template as a regular Django template, e.g.
   ``templates/emails/welcome.html``::

       <p>Hello {{ first_name }},</p>
       <p>your account at {{ site_name }} is ready.</p>

2. Register it, e.g. in ``AppConfig.ready()``. The path is the lookup key and cannot be
   changed later. ``subject`` is the default subject of templates created in the admin;
   ``help_context`` is shown in the admin and filled into the preview::

       from emailtemplates.registry import email_templates

       email_templates.register(
           "emails/welcome.html",
           name="Welcome email",
           subject="Welcome to {{ site_name }}",
           help_text="Sent after registration",
           help_context={
               "first_name": ("First name of the user", "Anna"),
               "site_name": "Name of the site",
           },
       )

   Sending an unregistered template raises ``NotRegistered``; pass
   ``registry_validation=False`` to ``EmailFromTemplate`` to skip the check.

3. Send it::

       from emailtemplates.email import EmailFromTemplate

       eft = EmailFromTemplate(
           name="emails/welcome.html", language="en", subject="Welcome to Example"
       )
       eft.context.update({"first_name": user.first_name, "site_name": "Example"})
       eft.send([user.email])  # returns the number of sent messages

   The template is looked up in the database by path and language, then in the template
   files. The ``subject`` passed here (or, without it, the ``subject`` of the
   registration) is used when the template comes from a file; a database template brings
   its own subject. Either way the subject is rendered with the same context as the
   content. The context always contains ``date``.

   ``send()`` takes extra ``EmailMessage`` kwargs (``cc``, ``bcc``, ``reply_to``, ...),
   ``attachment_paths`` and ``fail_silently`` (``True`` by default: SMTP errors are logged,
   not raised).

   The email is sent with two versions of the same content (``multipart/alternative``):
   the HTML rendered from the template, which email clients show, and a plain text version
   generated from it for clients that cannot show HTML, see `Plain text`_.

   To send the email some other way, e.g. through a mail queue, render it without
   sending::

       rendered = eft.render()  # RenderedEmail(subject, html, text)

4. To change the email without a deployment, add an *Email template* in the admin for the
   registered path and a language - or create the templates of all emails in a data
   migration, see `Creating email templates`_. Its content starts as a copy of the file.
   Files added as *Email attachments* and linked to the template are attached to every
   email, or, with *send as link*, passed to the context as ``default_attachments`` (name,
   URL pairs).

Default versions
----------------

The template file is the *default version* of an email; the content in the database is
the one sent. Changing the file never changes the content: Site Admins may have edited it.

Every email template keeps a snapshot of the file it was made from
(``EmailTemplate.default_content``). When developers change the file, the admin lists the
template as having a *New default version*, and its page links to a comparison: the
preview of the current content and of the default version side by side, with the changes
in the HTML. There the Site Admin may replace the content with the default version, and
restore the replaced content afterwards (``EmailTemplate.previous_content``). In code:
``has_new_default()``, ``replace_with_default()`` and ``restore_previous_content()``.

Templates created before 3.0.0 have no snapshot, so they never report a new default
version, but they can be compared and replaced all the same.

Creating email templates
------------------------

Projects create the email templates of their emails in a data migration, so that Site
Admins find every email in the admin right after the deployment, wrapped in the layout.
The migration copies the content of each template file once; from then on the content in
the database is the one sent and edited, and a later change of the file is offered as a
new default version (see `Default versions`_). A new email needs a migration adding it.
The migration depends on the migration of this app adding ``default_content``
(``0014_emailtemplate_preheader_default_content``) and on the one creating the layout::

    from django.db import migrations
    from django.template.loader import get_template
    from emailtemplates.registry import email_templates


    def create_email_templates(apps, schema_editor):
        EmailTemplate = apps.get_model("emailtemplates", "EmailTemplate")
        EmailLayout = apps.get_model("emailtemplates", "EmailLayout")
        layout = EmailLayout.objects.get(name="Standard")
        for item in email_templates.registration_items():
            content = get_template(item.path).template.source
            EmailTemplate.objects.get_or_create(
                title=item.path,
                language="en",
                defaults={
                    "subject": str(item.subject),
                    "preheader": str(item.preheader),
                    "content": content,
                    "default_content": content,  # the snapshot of the default version
                    "layout": layout,
                },
            )

Sending through django-post_office
----------------------------------

To send emails through the mail queue of `django-post_office`_ (priorities, retries,
logs), render them here and pass the result to ``mail.send()`` or ``mail.send_many()``
instead of a post_office template::

    from post_office import mail
    from emailtemplates.contrib.post_office import render_for_post_office

    mail.send(
        recipients=[user.email],
        priority="now",
        headers={"Reply-To": "office@example.com"},
        **render_for_post_office(
            "emails/welcome.html", {"first_name": user.first_name}, language="pl"
        )
    )

``render_for_post_office()`` returns ``subject``, ``message`` (the plain text),
``html_message`` and, when the template has attachments sent as files, ``attachments``.
The sender, the headers and the delivery options are passed to ``mail.send()`` directly.
post_office renders nothing, so its own ``EmailTemplate`` model is not used.

.. _django-post_office: https://github.com/ui/django-post_office

Settings
--------

* ``DEFAULT_FROM_EMAIL``, ``LANGUAGE_CODE``, ``LANGUAGES`` - default sender, default
  language and the languages available for templates.
* ``DEFAULT_REPLY_TO_EMAIL`` - optional ``Reply-To`` for every email.
* ``BASE_URL`` - optional, used to make attachment links absolute.
* ``MASS_EMAIL_RECIPIENTS`` - optional dotted path to a function returning the recipient
  emails of mass emails; all active users by default.
* ``EMAILTEMPLATES_RICH_TEXT`` - ``True`` turns on the rich text editor, see
  `Rich text editor`_; off by default, so that projects having django-tinymce for other
  reasons keep the HTML code editor.
* ``EMAILTEMPLATES_RICH_TEXT_CONFIG`` - TinyMCE options merged over the ones of the rich
  text editor, see `Rich text editor`_.
* ``EMAILTEMPLATES_INLINE_CSS`` - ``True`` moves the CSS of ``<style>`` tags (e.g. the
  ``styles`` of a layout) into the ``style`` attributes of the elements when an email is
  rendered, as many email clients ignore ``<style>``. Media queries stay in a ``<style>``
  tag. The admin preview shows the inlined email too. Requires the ``inline`` extra
  (`css-inline`_): ``pip install django-emailtemplates[inline]``.

.. _css-inline: https://github.com/Stranger6667/css-inline

Mass emails
-----------

A *Mass email message* created in the admin (subject, HTML content, attachments) is sent
with the button on its admin page, or with ``MassEmailMessage.send()``. It is sent
synchronously, so for many recipients send it from a task queue instead.

Email layouts
=============

An ``EmailLayout`` is a reusable frame for emails: everything that should surround the
content of an email template, e.g. a header with a logo and a footer with company data.
Layouts are created and edited in the Admin Panel, so Site Admins can change the look of
all emails at once, without a deployment.

A layout has a ``name``, ``header_content``, ``footer_content`` and ``styles``. Every
email template can optionally point to one layout (``EmailTemplate.layout``, empty by
default). When a layout is selected, the email is rendered as::

    <style>styles</style> + header_content + EmailTemplate.content + footer_content

``styles`` holds plain CSS without the ``<style>`` tag, which is added automatically;
empty ``styles`` adds no tag at all. When the header starts a whole HTML document, the
``<style>`` tag goes into its ``<head>``, before ``</head>``, so the doctype stays first.
Keeping the CSS in a field of its own means the header field holds markup only.

The parts are concatenated first and rendered afterwards, as a single Django template
with a single context. The header and the footer may therefore use the same context
variables as the email template itself, e.g.::

    styles:         .greeting { color: #c8524e; }
    header_content: <img src="https://{{ shop_domain }}/static/img/logo.png">
    content:        <p class="greeting">Hello {{ full_name }},</p>
    footer_content: <p>Sent by {{ shop_domain }}</p>

The context of the email holds ``subject`` (rendered) and ``preheader`` too, unless it
already has variables of these names, so the header may contain e.g.
``<title>{{ subject }}</title>`` and a hidden ``<span>{{ preheader }}</span>``. The
preheader is the text email clients show next to the subject in the inbox; every email
template has its own (``EmailTemplate.preheader``), and new ones start with the
``preheader`` passed to ``register()``. Both are plain text: they are not HTML escaped
when rendered, and escaped where the layout inserts them into HTML.

Because the parts are joined before being rendered, the header may open HTML tags that
the footer closes - that is the normal way of wrapping the content in a container.

Nothing changes for email templates without a layout - they are rendered exactly as
before, from the database or from the filesystem.

Layouts and ``{% extends %}``
-----------------------------

Template content that uses ``{% extends %}`` already brings its own frame, and the tag
must stay the first one in a template, so such content cannot be wrapped in a layout. The
admin form rejects that combination; if it is created another way, the layout is ignored
and a warning is logged. Use either ``{% extends %}`` (frame in the filesystem, for
developers) or a layout (frame in the database, for Site Admins).

Previews
--------

* *Show email preview* on an email template renders the template together with its
  layout, filled with the example context from the registry. Example values of
  ``help_context`` are fixed; for real objects pass ``preview_context`` to ``register()``,
  a dict or a callable returning one, called on every preview, e.g.
  ``preview_context=lambda: {"order": Order.objects.first()}``.
* *Show layout preview* on a layout renders the header, the footer and the styles with a
  placeholder in place of the email content. It has no context, so variables used in the
  header or the footer render empty.
* Next to the content editor of an email template, a live preview shows the email as it
  would be sent - in its layout, with the example context and the inlined CSS - with the
  content, subject, preheader and layout of the form, not saved yet. It is updated shortly
  after each change; while the content cannot be rendered (e.g. a template tag is being
  typed) the last preview stays, with the error below it.

The first two previews work on saved data. There is no live preview of a layout: its parts
only render correctly together - a header that opens the tags its footer closes is broken
HTML on its own - so a per-field preview reports errors that are not there.

Editor
------

``header_content`` and ``footer_content`` are not edited as two separate fields. The
admin shows them as a single *Frame* field: one box split by a divider standing for the
content of the email template, the header above it and the footer below. That is how they
are actually used - the header opens the tags the footer closes - and the form splits the
value back into the two model fields on save. See ``EmailFrameWidget`` and
``EmailFrameField``.

The frame and ``styles`` are edited with CodeMirror syntax highlighting, which the library
ships and wires up by default; projects need no widget configuration of their own.
``EmailTemplate.content`` is edited as HTML code in CodeMirror too, or as rich text, see
`Rich text editor`_. Any textarea with a ``data-code-editor`` attribute holding
CodeMirror options as JSON gets the same treatment; the easiest way to get one is
``emailtemplates.widgets.CodeEditorTextarea(mode="html")`` (or ``mode="css"``).

The editors run without line numbers and, for HTML, without mismatched-tag marking: in a
frame the closing tag of the header lives in the footer, so marking it as an error would
be wrong.

Rich text editor
================

With ``EMAILTEMPLATES_RICH_TEXT = True`` (and django-tinymce installed) the content of an
email template is edited as *Rich text* (TinyMCE) or as *HTML code* (CodeMirror), switched
with the buttons above the editor at any time, without saving. The rich text editor opens
unless the content would not survive it, see the limits below.

The rich text editor is meant for the text of an email: paragraphs, headings, lists,
links, simple tables and formatting. The frame of the email - logo, header, footer, CSS -
belongs in a layout, see `Email layouts`_. The toolbar starts with a *Variables* menu,
inserting the variables of the context described at registration (``help_context``), and
a *Blocks* menu, see `Blocks`_. Variables and template tags (``{% if %}``, ``{% for %}``,
...) are shown as chips, typed as text, but removed as a whole; the content keeps them as
plain ``{{ name }}`` and ``{% tag %}``.

The editor has its own TinyMCE configuration, made for emails
(``emailtemplates.rich_text.RICH_TEXT_CONFIG``): URLs are kept as typed, so links may point
at variables (``href="{{ activation_url }}"``), images cannot be pasted as data URIs and
formatting is saved as inline styles. ``TINYMCE_DEFAULT_CONFIG`` of the project is meant
for its website, so only ``license_key``, ``language`` and ``directionality`` are taken
from it. ``EMAILTEMPLATES_RICH_TEXT_CONFIG`` overrides any option, e.g.::

    EMAILTEMPLATES_RICH_TEXT_CONFIG = {"license_key": "gpl", "height": 700}

The live preview stands next to the editor when both fit, below it otherwise. The editor
takes at least 480px, or the ``width`` in pixels set in ``EMAILTEMPLATES_RICH_TEXT_CONFIG``
(e.g. ``"width": 1000``): a wider editor moves the preview below it on narrower screens.
The editor is never wider than its column, so it never runs into the preview.

The content is shown in the editor with the ``styles`` of the email layout of the
template. Classes of the layout, e.g. of a button, can be offered as TinyMCE
``style_formats``; with them the toolbar gets a *Formats* button::

    EMAILTEMPLATES_RICH_TEXT_CONFIG = {
        "body_class": "email-body",  # when the styles of the layout are scoped to it
        "style_formats": [
            {"title": "Button", "selector": "a", "classes": "btn"},
            {"title": "Callout", "block": "div", "classes": "callout", "wrapper": True},
        ],
    }

Limits of the rich text editor:

* A browser moves text out of places where HTML allows none, and so does the editor:
  template tags placed between table rows, table cells or list items would end up
  outside the table or the list. Such content opens in the HTML code editor and cannot be
  switched to rich text; the message above the editor names the tags.
* Content using ``{% extends %}`` cannot be edited as rich text either.
* The editor encodes ``>``, ``<`` and ``&`` typed as text; inside ``{% %}`` and ``{{ }}``
  they are decoded again on save, so ``{% if count > 1 %}`` keeps working.

Blocks
======

Some parts of an email are too complex for Site Admins to edit, e.g. a table with the
details of an order, but they still want to decide where it goes and write the text
around it. Register such a part as a block - a template file of its own - and the
content places it as a variable::

    email_templates.register(
        "emails/order_summary.html",
        help_context={"order": "The order"},
        blocks={
            "order_details": ("Order details", "emails/components/order_details.html"),
            "paid_order_details": (
                "Order details (paid)",
                "emails/components/order_details.html",
                {"paid": True},  # extra context, like {% include ... with paid=True %}
            ),
        },
    )

The block template gets the context of the email, updated with the extra context, if
given. It is rendered only when the content uses the block. A variable of the same name
passed in the context takes precedence over the block.

In the rich text editor the *Blocks* menu inserts a block as a grey, labeled box that
can be moved or removed, but not edited. A click on the box shows the block rendered with
the example context (``preview_context``), a second click hides it; the preview is never
saved. In the content a block is stored as::

    <div class="emailtemplates-block" data-label="Order details">{{ order_details }}</div>

The ``<div>`` keeps the block out of paragraphs; the default template files may use the
same markup. The admin lists the blocks of a template next to its context, and the email
preview renders them with the example context.

Plain text
==========

Every email is sent with a plain text version, the fallback for email clients that cannot
show HTML. It is generated from the rendered HTML by `inscriptis`_
(``emailtemplates.text.html_to_text()``), laid out as a browser shows the HTML, with links
followed by their address, e.g. ``[activate](https://example.com/activate/)``. Styles,
scripts, the document head and elements hidden with ``display: none`` (e.g. a preheader)
are left out.

.. _inscriptis: https://github.com/weblyzard/inscriptis

Development
===========

Run the tests with ``python runtests.py`` (``tox`` for every supported Python and Django).

Changelog
=========

3.0.0
-----
* Rich text editor (TinyMCE) for the content of email templates, switched with the HTML
  code editor without saving, with *Variables* and *Blocks* menus and variables shown as
  chips. The ``tinymce`` extra, ``EMAILTEMPLATES_RICH_TEXT`` (opt-in) and
  ``EMAILTEMPLATES_RICH_TEXT_CONFIG`` settings.
* Plain text version of every email, generated from the HTML one by inscriptis, a new
  dependency (``emailtemplates.text.html_to_text()``).
* ``EmailFromTemplate.render()`` returns ``RenderedEmail(subject, html, text)`` without
  sending, e.g. for sending through a mail queue. ``EmailFromTemplate.text`` holds the
  plain text after ``render_message()``.
* ``emailtemplates.contrib.post_office.render_for_post_office()`` for sending through
  the mail queue of django-post_office.
* ``EMAILTEMPLATES_INLINE_CSS`` setting and the ``inline`` extra: CSS inlined into the
  sent emails, so that the styles of a layout apply to the content written in the rich
  text editor.
* System checks: ``emailtemplates.W001`` warns of ``EMAILTEMPLATES_RICH_TEXT`` without
  django-tinymce, ``emailtemplates.E001`` of ``EMAILTEMPLATES_INLINE_CSS`` without
  css-inline.
* ``EmailTemplate.preheader`` and the ``preheader`` of ``register()``; ``subject`` and
  ``preheader`` in the context of the layout.
* The rich text editor shows the content with the styles of the layout and gets a
  *Formats* button when ``style_formats`` are configured.
* Layouts may be whole HTML documents: the styles go before ``</head>`` of the header.
* ``preview_context`` of ``register()``: context of the admin preview, e.g. with model
  instances.
* Live preview of the email next to the content editor, updated while editing, before
  saving.
* Default versions: email templates keep a snapshot of their template file; the admin
  shows when developers changed it, compares both versions side by side and lets Site
  Admins replace the content with the new default version, or restore the replaced
  content.
* Blocks: parts of an email rendered from template files of their own
  (``email_templates.register(..., blocks=...)``), placed by Site Admins with the *Blocks*
  menu of the rich text editor.
* The ``subject`` of the registration is used for templates coming from a file when
  ``EmailFromTemplate`` gets no ``subject``; the subject of a file template is rendered
  with the context too.
* A missing template file is logged at the debug level instead of as an error: email
  templates may live in the database only, and the admin asks for their file on every page.
* Creating an email template no longer switches the active language to the language of
  the template (``get_default_subject()`` activated it for the rest of the request).
* The subject is not HTML escaped any more: a variable holding ``Tom & Jerry`` is shown
  as it is, not as ``Tom &amp; Jerry``.
* **Backward incompatible**: emails are sent as ``EmailMultiAlternatives`` - the body
  (``msg.body``) is the plain text and the HTML is an alternative; previously the body was
  the HTML with ``content_subtype = "html"``. ``EmailFromTemplate.content_subtype`` is
  removed.

2.0.0
-----
* Email layouts: an optional, admin-editable header, footer and CSS shared by email
  templates. ``EmailLayout`` model, ``EmailTemplate.layout`` field, layout aware previews.
* Check syntax errors in the header and footer of an email layout (admin form).
* Syntax highlighting for the HTML and CSS fields in the admin, shipped with the library.
* Performance: ``EmailTemplate`` queries load the layout with ``select_related``, the
  layout admin list prefetches the email templates using each layout.
* Support for Django 5.2, 6.0 and 6.1 and Python 3.13 and 3.14.
* **Backward incompatible**: Django 4.0+ and Python 3.10+ are required; Python 2.7 and
  Django older than 4.0 are no longer supported.
* ``packaging`` is no longer a dependency, ``default_app_config`` is removed (Django picks
  up ``EmailtempatesConfig`` on its own).
* ``emailtemplates.__version__`` matches the package version again.

1.1.17
------
* Add support for django 4 - https://github.com/deployed/django-emailtemplates/pull/39

1.1.16
------
* change max_length from 100 to 255 in email attachments - https://github.com/deployed/django-emailtemplates/pull/38

1.1.15
------
* ordering in email template & default subject from registry - https://github.com/deployed/django-emailtemplates/pull/37

1.1.14
------
* Additional fields for email attachment - https://github.com/deployed/django-emailtemplates/pull/36

1.1.13
------
* Change default auto field to BigAutoField - https://github.com/deployed/django-emailtemplates/pull/35

1.1.12
-------
* 23614 german translations  - https://github.com/deployed/django-emailtemplates/pull/34

1.1.11
-------
* subject improvement - Now it is possible to use django templates as email subject

1.1.10
-------
* Fixed problem with duplicated kwargs in send method

1.1.9
-----
* absolute url of the attached files
* use attachment filename in the email context

1.1.8
-----
* send related attachments together with email templates

1.1.7
-----
* added missing translations [pl]
* added support for naming of the templates

1.1.6
-----
* Template loader fix
* Added missing migration - fixed language choices

1.1.5
-----
* Add default_app_config

1.1.4
-----
* Add verbose name, replace __unicode__ into __str__

1.1.3
-----
* Adding support for DEFAULT_REPLY_TO_EMAIL in django settings.

1.1.2
-----

* EmailFromTemplate.send_email - added new param: fail_silently
  - When it’s False, msg.send() will raise an smtplib.SMTPException if an error occurs.

1.1.1
-----

* Fix confusing logger stating that email was sent even though an error had occured
* cosmetic changes - logging messages possible to be aggregated by tools like sentry


1.1.0
-----

* Basic mass mailing feature. Just go to admin, create new MassEmailMessage object and fill its subject, HTML content and attachments.
  Click admin button to send it or use Django shell. Emails are be default sent to all active users of user model (it must have is_active and email fields).
  In case of many application users sending emails using admin button may require to implement sending from queue rather than synchronously.
  You can create custom recipients function returning list and specify reference to it in MASS_EMAIL_RECIPIENTS setting.
* `EmailFromTemplate.send()` now receives `attachments_paths` parameter of paths that can be used by `EmailMessage.attach_file()` django core method.

1.0.4
-----

* Django 1.11 compatibility fix

1.0.3
-----

* Django 1.11 compatibility

1.0.2
-----

* `help_context` parameter of `EmailRegistry.register()` may now contain tuple of description and example value shown in preview
* Changed EmailTemplateAdminForm title to use ChoiceField choices as lazy function. This way all registered templates are printed in admin form, independent of order Python loads application modules.

1.0.1
-----

* better admin panel
* show email preview action
* set default email content from related template

1.0.0
-----

* This version introduced **backward incompatible** EmailTemplateRegistry.
* All EmailTemplates must be registered using email_templates.register(path). Not registered email templates will raise NotRegistered exception. Registry validation can be avoid by creating email template with flag registry_validation set to False.
* Removed prefix from EmailFromTemplate. All templates must be located in {{templates}}/emailtemplates.

0.8.7.3
-------

* Set default email title if is not defined in the database.

0.8.7.1
-------

* Added missing migration

0.8.7
-----

* Check syntax errors in EmailTemplate's content (admin form)

0.8.6.2
-------

* Added missing migrations

0.8.6.1
-------

* Migrations dir fix

0.8.6
-----

* Compatibility with Django 1.10

0.8.5
-----

* Fixed template loader error - added default Engine

0.8.4
-----

* Django 1.8.8 required
