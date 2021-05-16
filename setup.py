"""Odata package configuration."""

from setuptools import setup

setup(
    name='flask-smorest-sqlalchemy-odata',
    version=open('VERSION').readline().strip(),
    author='Casey Knolla',
    author_email='cknolla@gmail.com',
    description='Odata filtering and sorting with flask-smorest',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/cknolla/flask-smorest-sqlalchemy-odata',
    license='MIT',
    packages=['odata'],
    python_requires='>=3.8',
    include_package_data=True,
    install_requires=[
        'flask>=1.0',
        'flask-smorest>=0.30.0',
        'Flask-SQLAlchemy>=2.5.1',
        'marshmallow>=3.11.1',
        'marshmallow-sqlalchemy>=0.25.0',
        'sqlalchemy>=1.3.8',
        'stringcase>=1.2.0',
        'webargs>=8.0.0',
        'Werkzeug>=1.0.1',
    ],
)
