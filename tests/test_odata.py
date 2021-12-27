from http import HTTPStatus

import pytest
from flask.testing import FlaskClient

from tests.utils import parse_response


@pytest.mark.parametrize(
    "filters, ids",
    [
        ("usernameSupervisorId eq 'user31'", {3}),
        ("isSupervisor eq true", {1, 2, 4}),
        ("contains(username,'user')", {1, 2, 3}),
        ("id eq 1", {1}),
        ("isActive eq true", {1, 3, 4}),
        ("isActive eq false", {2}),
        ("note eq null", {3, 4}),
        ("note ne null", {1, 2}),
        ("startswith(username,'user')", {1, 2, 3}),
        ("endswith(username,'2')", {2}),
        ("logins lt 51", {1}),
        ("logins gt 51", {2, 4}),
        ("logins ge 51", {2, 3, 4}),
        ("logins le 51", {1, 3}),
        ("created gt 2020-05-01T01:00:00", {2, 3, 4}),
        ("created lt 2021-01-01T04:00:00", {1, 2}),
        ("id in (1,3)", {1, 3}),
        ('username in ("user2", "odd")', {4, 2}),
    ],
)
def test_user_filters_succeeds(client: FlaskClient, filters: str, ids: set[int]):
    response = client.get(
        "/user",
        query_string={
            "filter": filters,
        },
    )
    users = parse_response(response)
    assert response.status_code == HTTPStatus.OK
    assert {user["id"] for user in users} == ids


@pytest.mark.parametrize(
    "filters",
    [
        "(logins ge 51",
        "logins ge 51 and (logins le 31",
    ],
)
def test_mismatched_parens_fails(client: FlaskClient, filters: str):
    response = client.get(
        "/user",
        query_string={
            "filter": filters,
        },
    )
    body = parse_response(response)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert body["message"] == "Parentheses in filter string are mismatched."


@pytest.mark.parametrize(
    "filters",
    [
        'username eq "user',
        'username eq user"',
        "username eq \"user'",
        "username eq 'user\"",
    ],
)
def test_mismatched_quotes_fails(client: FlaskClient, filters: str):
    response = client.get(
        "/user",
        query_string={
            "filter": filters,
        },
    )
    body = parse_response(response)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert body["message"] == "Quotes in filter string are mismatched."


@pytest.mark.parametrize(
    "filters, ids",
    [
        ("isActive eq false or (startswith(username,'od') and id eq 4)", {2, 4}),
        (
            "username ne 'user1' and (id in (4) or username eq 'user3') and "
            "(logins gt 99 and logins lt 101)",
            set(),
        ),
        (
            "username ne 'user1' and (id in(4) or username eq 'user3') and "
            "(logins gt 99 or logins lt 101)",
            {3, 4},
        ),
        (
            "((username ne 'user1' and username ne 'user3') and "
            "(logins gt 99 and logins lt 101)) or "
            "(isActive eq true and username in ('user2','odd') and id eq 2)",
            {2},
        ),
        (
            "(username eq 'user2' and logins eq 100 and isActive eq false) or ("
            "logins gt 1 and username eq 'user3'"
            ") or contains(note,'backup') or ("
            "logins gt 1000 and username eq 'user4' and supervisor/id eq 1"
            ")",
            {2, 3},
        ),
        (
            "("
            "username eq 'user1' and ("
            "logins gt 1 or username ne '(user2'"
            ") and contains(note,'primary') and ("
            "logins gt 2 or username ne 'user2)'"
            ")"
            ")",
            {1},
        ),
    ],
)
def test_complex_filter_succeeds(client: FlaskClient, filters: str, ids: set[int]):
    """Really try to strain the segment and filter logic with lots of depth and and/or swaps."""
    response = client.get(
        "/user",
        query_string={
            "filter": filters,
        },
    )
    users = parse_response(response)
    assert response.status_code == HTTPStatus.OK
    assert {user["id"] for user in users} == ids


@pytest.mark.parametrize(
    "orderby, ids",
    [
        ("id", [1, 2, 3, 4]),
        ("id desc", [4, 3, 2, 1]),
        ("roles/id desc", [1, 3, 2, 4]),
    ],
)
def test_orderby_succeeds(client: FlaskClient, orderby: str, ids: list[int]):
    response = client.get(
        "/user",
        query_string={
            "orderby": orderby,
        },
    )
    users = parse_response(response)
    assert response.status_code == HTTPStatus.OK
    assert [user["id"] for user in users] == ids


@pytest.mark.parametrize(
    "orderby, err_segment",
    [
        ("id unknown", "orderby direction"),
    ],
)
def test_orderby_fails(client: FlaskClient, orderby: str, err_segment: str):
    response = client.get(
        "/user",
        query_string={
            "orderby": orderby,
        },
    )
    body = parse_response(response)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert err_segment in body["message"]


@pytest.mark.parametrize(
    "filters, orderby, page_size, page, ids",
    [
        ("endswith(body,'text')", "id", 1, 1, [1]),
        ("endswith(body,'text')", "id", 1, 2, [3]),
        ("endswith(body,'text')", "id", 2, 1, [1, 3]),
    ],
)
def test_with_paging_succeeds(
    client: FlaskClient,
    filters: str,
    orderby: str,
    page_size: int,
    page: int,
    ids: list[int],
):
    response = client.get(
        "/comment",
        query_string={
            "filter": filters,
            "orderby": orderby,
            "page_size": page_size,
            "page": page,
        },
    )
    comments = parse_response(response)
    assert response.status_code == HTTPStatus.OK
    assert [comment["id"] for comment in comments] == ids


@pytest.mark.parametrize(
    "filters, ids",
    [
        ('contains(user/username,"user1")', {1, 2, 3}),  # within contains
        ('user/username eq "user1"', {1, 2, 3}),  # one to many
        ('user/roles/name eq "admin"', {1, 2, 3, 4, 5}),  # many to many
        ('user/supervisor/username eq "user1"', {6}),  # self-referential
    ],
)
def test_joined_filter_succeeds(
    client: FlaskClient,
    filters: str,
    ids: list[int],
):
    response = client.get(
        "/comment",
        query_string={
            "filter": filters,
        },
    )
    comments = parse_response(response)
    assert response.status_code == HTTPStatus.OK
    assert {comment["id"] for comment in comments} == ids


@pytest.mark.parametrize(
    "filters, err_segment",
    [
        ("body/username eq 'user1'", "Comment has no relationship property named body"),
        ("user/body eq 'user1'", "User has no column named body"),
        (
            "user/usernameSupervisorId/body eq 'what'",
            "User has no relationship property named username_supervisor_id",
        ),
    ],
)
def test_joined_with_invalid_property_fails(
    client: FlaskClient,
    filters: str,
    err_segment: str,
):
    response = client.get(
        "/comment",
        query_string={
            "filter": filters,
        },
    )
    body = parse_response(response)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert err_segment in body["message"]


@pytest.mark.parametrize(
    "filters, ids",
    [
        ('username eq "user1" and logins lt 5', {1}),
        ('startswith(username,"user") and roles/name eq "operator"', {1, 3}),
    ],
)
def test_and_filter_succeeds(
    client: FlaskClient,
    filters: str,
    ids: set[int],
):
    response = client.get(
        "/user",
        query_string={
            "filter": filters,
        },
    )
    comments = parse_response(response)
    assert response.status_code == HTTPStatus.OK
    assert {comment["id"] for comment in comments} == ids


@pytest.mark.parametrize(
    "filters, ids",
    [
        ('username eq "user1" or logins gt 400', {1, 4}),
        ('endswith(username,"r3") or isActive eq false', {2, 3}),
        # TODO: join with outerjoin instead of inner join to get this expected result
        #   the join to supervisor is excluding user2 since it has no supervisor
        # ('startswith(supervisor/username,"user1") or isActive eq false', {2, 3}),
    ],
)
def test_or_filter_succeeds(
    client: FlaskClient,
    filters: str,
    ids: set[int],
):
    response = client.get(
        "/user",
        query_string={
            "filter": filters,
        },
    )
    users = parse_response(response)
    assert response.status_code == HTTPStatus.OK
    assert {user["id"] for user in users} == ids


def test_default_orderby_succeeds(client: FlaskClient):
    response = client.get(
        "/role",
    )
    roles = parse_response(response)
    assert response.status_code == HTTPStatus.OK
    assert [role["id"] for role in roles] == [2, 1]
