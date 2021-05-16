import sys
import os
from datetime import datetime

import pytest as pytest
from flask.testing import FlaskClient

path = os.path.join(
    os.path.abspath(
        os.path.dirname(
            os.path.dirname(__file__)
        )
    ),
)

sys.path.append(path)

from app import create_app, db, models  # noqa


@pytest.fixture(scope='module')
def app():
    app = create_app(is_test=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        user1 = models.User(
            username='user1',
            logins=2,
            created=datetime.strptime('2020-01-01T01:01:00', '%Y-%m-%dT%H:%M:%S'),
        )
        user2 = models.User(
            username='user2',
            is_active=False,
            logins=100,
            created=datetime.strptime('2021-01-01T01:01:00', '%Y-%m-%dT%H:%M:%S'),
        )
        user3 = models.User(
            username='user3',
            logins=51,
            created=datetime.strptime('2021-01-01T06:01:00', '%Y-%m-%dT%H:%M:%S'),
        )
        admin_role = models.Role(
            name='admin',
            users=[
                user1,
                user2,
            ],
        )
        operator_role = models.Role(
            name='operator',
            users=[
                user1,
                user3,
            ],
        )
        comment1 = models.Comment(
            user=user1,
            body='some text',
        )
        comment2 = models.Comment(
            user=user1,
            body='a response',
        )
        comment3 = models.Comment(
            user=user1,
            body='additional text',
        )
        comment4 = models.Comment(
            user=user2,
            body='keep going',
        )
        comment5 = models.Comment(
            user=user2,
            body='ongoing discussion',
        )
        comment6 = models.Comment(
            user=user3,
            body='talking to myself',
        )
        db.session.add_all([
            user1,
            user2,
            user3,
            admin_role,
            operator_role,
            comment1,
            comment2,
            comment3,
            comment4,
            comment5,
            comment6,
        ])
        db.session.flush()
        db.session.commit()
    yield app


@pytest.fixture(scope='module')
def client(app) -> FlaskClient:
    yield app.test_client()
