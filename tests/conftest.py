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
    dt_format = '%Y-%m-%dT%H:%M:%S'
    app = create_app(is_test=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        user1 = models.User(
            id=1,
            username='user1',
            logins=2,
            note='primary admin',
            created=datetime.strptime('2020-01-01T01:01:00', dt_format),
        )
        user2 = models.User(
            id=2,
            username='user2',
            is_active=False,
            logins=100,
            note='backup admin',
            created=datetime.strptime('2021-01-01T01:01:00', dt_format),
        )
        user3 = models.User(
            id=3,
            username='user3',
            logins=51,
            created=datetime.strptime('2021-01-01T06:01:00', dt_format),
            supervisor=user1,
        )
        odduser = models.User(
            id=4,
            username='odd',
            logins=500,
            created=datetime.strptime('2021-03-05T07:30:00', dt_format)
        )
        admin_role = models.Role(
            id=1,
            name='admin',
            users=[
                user1,
                user2,
            ],
        )
        operator_role = models.Role(
            id=2,
            name='operator',
            users=[
                user1,
                user3,
            ],
        )
        comment1 = models.Comment(
            id=1,
            user=user1,
            body='some text',
            created=datetime.strptime('2021-03-05T07:30:00', dt_format),
        )
        comment2 = models.Comment(
            id=2,
            user=user1,
            body='a response',
            created=datetime.strptime('2021-03-06T07:30:00', dt_format),
        )
        comment3 = models.Comment(
            id=3,
            user=user1,
            body='additional text',
            created=datetime.strptime('2021-03-07T07:30:00', dt_format),
        )
        comment4 = models.Comment(
            id=4,
            user=user2,
            body='keep going',
            created=datetime.strptime('2021-03-08T07:30:00', dt_format),
        )
        comment5 = models.Comment(
            id=5,
            user=user2,
            body='ongoing discussion',
            created=datetime.strptime('2021-03-09T07:30:00', dt_format),
        )
        comment6 = models.Comment(
            id=6,
            user=user3,
            body='talking to myself',
            created=datetime.strptime('2021-03-10T07:30:00', dt_format),
        )
        db.session.add_all([
            user1,
            user2,
            user3,
            odduser,
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
