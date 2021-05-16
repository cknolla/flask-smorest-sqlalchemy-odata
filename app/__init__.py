"""Test application for odata filtering."""
import logging

from flask import Flask
from werkzeug.exceptions import HTTPException

from .db import db
from .api import api
from config import Config
from .resources import resources

logger = logging.getLogger(__name__)


def create_app(is_test: bool = False):
    """Initial application creation and configuration load."""
    logger.info('Initializing app')
    app = Flask(__name__)
    app_config = Config()
    app.config.from_object(app_config)
    app.config['TEST_MODE'] = is_test

    # Module bootstrap
    db.init_app(app)
    api.init_app(app)

    # register api blueprints
    api.register_blueprint(resources)

    @app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):
        body = {
            'code': err.code,
            'status': err.name,
            'message': err.description,
            'errors': {},
        }
        if hasattr(err, 'data') and err.data:
            body['errors'] = err.data.get('messages')
        return body, err.code

    return app
