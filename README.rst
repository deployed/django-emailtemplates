django-emailtemplates
*********************

About
=====

Django app that enables developers to create default templates for emails
and Site Admins to easily override the templates via Admin Panel.

Assumptions
===========

* Site Admins should know context for each template.
* Site Admins should be familiar with Django Template System.

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
empty ``styles`` adds no tag at all. Keeping the CSS in a field of its own means the
header field holds markup only.

The parts are concatenated first and rendered afterwards, as a single Django template
with a single context. The header and the footer may therefore use the same context
variables as the email template itself, e.g.::

    styles:         .greeting { color: #c8524e; }
    header_content: <img src="https://{{ shop_domain }}/static/img/logo.png">
    content:        <p class="greeting">Hello {{ full_name }},</p>
    footer_content: <p>Sent by {{ shop_domain }}</p>

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
  layout, filled with the example context from the registry.
* *Show layout preview* on a layout renders the header, the footer and the styles with a
  placeholder in place of the email content. It has no context, so variables used in the
  header or the footer render empty.

Both previews work on saved data, so save the template after picking a layout to see the
whole email.

There is deliberately no live preview while typing. The parts of a layout only render
correctly together - a header that opens the tags its footer closes is broken HTML on its
own - so a per-field preview reports errors that are not there.

Editor
------

``header_content`` and ``footer_content`` are not edited as two separate fields. The
admin shows them as a single *Frame* field: one box split by a divider standing for the
content of the email template, the header above it and the footer below. That is how they
are actually used - the header opens the tags the footer closes - and the form splits the
value back into the two model fields on save. See ``EmailFrameWidget`` and
``EmailFrameField``.

The frame, ``styles`` and ``EmailTemplate.content`` are edited with CodeMirror syntax
highlighting, which the library ships and wires up by default; projects need no widget
configuration of their own. Any textarea with a ``data-code-editor`` attribute holding
CodeMirror options as JSON gets the same treatment; the easiest way to get one is
``emailtemplates.widgets.CodeEditorTextarea(mode="html")`` (or ``mode="css"``).

The editors run without line numbers and, for HTML, without mismatched-tag marking: in a
frame the closing tag of the header lives in the footer, so marking it as an error would
be wrong.

Changelog
=========

1.2.0
-----
* Email layouts: an optional, admin-editable header, footer and CSS shared by email
  templates. ``EmailLayout`` model, ``EmailTemplate.layout`` field, layout aware previews.
* Check syntax errors in the header and footer of an email layout (admin form).
* Syntax highlighting for the HTML and CSS fields in the admin, shipped with the library.
* **Backward incompatible**: Python 3.10+ is required, Python 2.7 and Django 3.2 are no
  longer supported.

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
