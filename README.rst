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
