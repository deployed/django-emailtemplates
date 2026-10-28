import os
from setuptools import setup, find_packages

README = open(os.path.join(os.path.dirname(__file__), 'README.rst')).read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

install_requires = [
    'Django>=4.0',
    'inscriptis>=2.0',  # the plain text version of emails, see emailtemplates.text
]

tests_require = [
    'mock',
]

setup(
    name='django-emailtemplates',
    version='3.0.0-alpha',
    packages=find_packages(),
    package_data={'emailtemplates': ['locale/*/LC_MESSAGES/*.po', 'locale/*/LC_MESSAGES/*.mo']},
    include_package_data=True,
    license='MIT License',
    description='A simple Django app to create emails based on database or filesystem templates.',
    long_description=README,
    url='https://github.com/deployed/django-emailtemplates',
    author='Wiktor Kolodziej',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    python_requires='>=3.10',
    install_requires=install_requires,
    extras_require={
        'tinymce': ['django-tinymce>=4.0'],  # bundles TinyMCE 6+, whose API content_editor.js uses
        'inline': ['css-inline>=0.17'],  # keep_at_rules
        'celery': ['celery>=5.0'],  # sending in the background, see emailtemplates.tasks
    },
    tests_require=tests_require
)
