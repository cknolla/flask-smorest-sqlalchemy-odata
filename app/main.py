import logging.config

from app import create_app

logger = logging.getLogger(__name__)
application = create_app()


if __name__ == '__main__':
    application.run(
        host=application.config['FLASK_RUN_HOST'],
        port=application.config['FLASK_RUN_PORT'],
    )
