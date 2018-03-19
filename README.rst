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
