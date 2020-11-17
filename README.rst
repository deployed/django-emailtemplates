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

Changelog
=========

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
