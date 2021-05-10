import pytest
from flask.testing import FlaskClient

from tests.utils import parse_response


@pytest.mark.parametrize('filters, ids', [
    ('contains(username,\'user\')', [1, 2, 3]),
    ('id eq 1', [1]),
    ('isActive eq true', [1, 3]),
    ('isActive eq false', [2]),
    ('isActive eq null', []),
    ('isActive ne null', [1, 2, 3]),
    ('startswith(username,\'user\')', [1, 2, 3]),
    ('endswith(username,\'2\')', [2]),
    ('logins lt 51', [1]),
    ('logins gt 51', [2]),
    ('logins ge 51', [2, 3]),
    ('logins le 51', [1, 3]),
    ('created gt 2020-05-01T01:00:00', [2, 3]),
    ('created lt 2021-01-01T04:00:00', [1, 2]),
])
def test_user_filters(client: FlaskClient, filters, ids):
    response = client.get(
        '/user',
        query_string={
            'filter': filters,
        }
    )
    response = parse_response(response)
    assert len(ids) == len(response)
    assert ids == [user['id'] for user in response]
