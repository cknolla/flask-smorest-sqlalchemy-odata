from http import HTTPStatus
from typing import List

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
def test_user_filters_succeeds(client: FlaskClient, filters, ids):
    response = client.get(
        '/user',
        query_string={
            'filter': filters,
        }
    )
    response = parse_response(response)
    assert len(ids) == len(response)
    assert ids == [user['id'] for user in response]


@pytest.mark.parametrize('orderby, ids', [
    ('id', [1, 2, 3]),
    ('id desc', [3, 2, 1]),
])
def test_orderby_succeeds(client: FlaskClient, orderby: str, ids: List[int]):
    response = client.get(
        '/user',
        query_string={
            'orderby': orderby,
        }
    )
    status_code, response = response.status_code, parse_response(response)
    assert status_code == HTTPStatus.OK
    assert ids == [user['id'] for user in response]


@pytest.mark.parametrize('orderby, err_segment', [
    ('id unknown', 'orderby direction'),
])
def test_orderby_fails(client: FlaskClient, orderby: str, err_segment: str):
    response = client.get(
        '/user',
        query_string={
            'orderby': orderby,
        }
    )
    status_code, response = response.status_code, parse_response(response)
    assert status_code == HTTPStatus.BAD_REQUEST
    assert err_segment in response['message']


@pytest.mark.parametrize('filters, orderby, page_size, page, ids', [
    ('endswith(body,\'text\')', 'id', 1, 1, [1]),
    ('endswith(body,\'text\')', 'id', 1, 2, [3]),
    ('endswith(body,\'text\')', 'id', 2, 1, [1, 3]),
])
def test_with_paging_succeeds(
        client: FlaskClient,
        filters: str,
        orderby: str,
        page_size: int,
        page: int,
        ids: List[int]):
    response = client.get(
        '/comment',
        query_string={
            'filter': filters,
            'orderby': orderby,
            'page_size': page_size,
            'page': page,
        }
    )
    status_code, response = response.status_code, parse_response(response)
    assert status_code == HTTPStatus.OK
    assert ids == [comment['id'] for comment in response]


@pytest.mark.parametrize('filters, ids', [
    ('user/username eq "user1"', [1, 2, 3]),
    ('user/roles/name eq "admin"', [1, 2, 3, 4, 5])
])
def test_joined_filter_succeeds(
        client: FlaskClient,
        filters: str,
        ids: List[int]):
    response = client.get(
        '/comment',
        query_string={
            'filter': filters,
        }
    )
    status_code, response = response.status_code, parse_response(response)
    assert status_code == HTTPStatus.OK
    assert ids == [comment['id'] for comment in response]


@pytest.mark.parametrize('filters, err_segment', [
    ('body/username eq \'user1\'', 'Comment has no relationship property named body'),
    ('user/body eq \'user1\'', 'User has no column named body'),
])
def test_joined_with_invalid_property_fails(
        client: FlaskClient,
        filters: str,
        err_segment: str):
    response = client.get(
        '/comment',
        query_string={
            'filter': filters,
        }
    )
    status_code, response = response.status_code, parse_response(response)
    assert status_code == HTTPStatus.BAD_REQUEST
    assert err_segment in response['message']


@pytest.mark.parametrize('filters, ids', [
    ('username eq "user1 and logins lt 5"', [1]),
    ('startswith(username,"user") and roles/name eq "operator"', [1, 3])
])
def test_and_filter_succeeds(
        client: FlaskClient,
        filters: str,
        ids: List[int]):
    response = client.get(
        '/user',
        query_string={
            'filter': filters,
        }
    )
    status_code, response = response.status_code, parse_response(response)
    assert status_code == HTTPStatus.OK
    assert ids == [comment['id'] for comment in response]
