import os
from setuptools import setup, find_packages

README = open(os.path.join(os.path.dirname(__file__), 'README.rst')).read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

install_requires = [
    'Django>=1.8.8',
]

tests_require = [
    'mock',
]

setup(
    name='django-emailtemplates',
    version='0.8.7.3',
    packages=find_packages(),
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
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    install_requires=install_requires,
    tests_require=tests_require
)
