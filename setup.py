"""Odata package configuration."""

from setuptools import setup

setup(
    name="flask-smorest-sqlalchemy-odata",
    version=open("VERSION").readline().strip(),
    author="Casey Knolla",
    author_email="cknolla@gmail.com",
    description="Odata filtering and sorting with flask-smorest",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/cknolla/flask-smorest-sqlalchemy-odata",
    license="MIT",
    packages=["odata"],
    python_requires=">=3.9",
    include_package_data=True,
    install_requires=[
        "apispec>=5.1.0",
        "Flask>=2.0.0",
        "flask-smorest>=0.35.0",
        "Flask-SQLAlchemy>=2.5.1",
        "marshmallow>=3.14.1",
        "marshmallow-sqlalchemy>=0.27.0",
        "sqlalchemy>=1.4.0",
        "stringcase>=1.2.0",
        "webargs>=8.0.0",
        "Werkzeug>=2.0.0",
    ],
)
