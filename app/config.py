"""Config class for flask app."""
from os import getenv


class Config:
    """Flask config object."""

    # Flask
    FLASK_RUN_HOST = getenv("FLASK_RUN_HOST", "0.0.0.0")
    FLASK_RUN_PORT = getenv("FLASK_RUN_PORT", "5999")

    # Flask-Smorest
    API_TITLE = getenv("API_TITLE", "Odata API")
    API_VERSION = getenv("API_VERSION", "v1")
    OPENAPI_VERSION = getenv("OPENAPI_VERSION", "3.0.2")
    OPENAPI_URL_PREFIX = getenv("OPENAPI_URL_PREFIX", "/docs")
    OPENAPI_REDOC_PATH = getenv("OPENAPI_REDOC_PATH", "/redoc")
    OPENAPI_REDOC_URL = getenv(
        "OPENAPI_REDOC_URL",
        "https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )
    OPENAPI_SWAGGER_UI_PATH = getenv("OPENAPI_SWAGGER_UI_PATH", "/swagger")
    OPENAPI_SWAGGER_UI_URL = getenv(
        "OPENAPI_SWAGGER_UI_URL",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@3.25.0/",
    )

    # SQLAlchemy
    SQLALCHEMY_COMMIT_ON_TEARDOWN = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///data.db")
