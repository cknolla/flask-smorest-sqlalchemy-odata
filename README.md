# Odata filtering for Flask-Smorest with Flask-Sqlalchemy 

Add odata-like filtering and sorting on top of flask-smorest functionality

## Usage
The primary use case is as a wrapper around the flask-smorest Blueprint class.
It will add the odata `filter` and `orderby` query params and apply them to the returned model from a MethodView.

```python
from http import HTTPStatus
from flask_smorest import Api, Page
from flask.views import MethodView

from odata import Blueprint

api = Api(app)


class CursorPage(Page):
    @property
    def item_count(self):
        return self.collection.count()


resources = Blueprint(
    'resources',
    __name__,
    url_prefix='/',
    description='root resources',
)

@resources.route('/users')
class User(MethodView):

    @resources.response(HTTPStatus.OK, schemas.User(many=True))
    @resources.paginate(CursorPage)
    @resources.odata(db.session)
    def get(self):
        return models.User

api.register_blueprint(resources)
```

It will also add docs so the params will appear in Swagger/Redoc.

## Features

### Filter operators
Multiple filter operations can be joined with `and` and `or` 

|Operator Name|Syntax|Examples|
|---|---|---|
|Contains|contains(field,'value')|contains(description,'middle of a sentence')
|Equal|field eq value|id eq 1<br>isActive eq true<br>isActive eq false<br>serialNumber eq null<br>description eq 'very specific'|
|Not Equal|field ne value|isActive ne true|
|In|field in (comma,separated,values)|id in (1,3)<br>username in ("user1", "user2")
|Starts with|startswith(field,'value')|startswith(preamble,'We the people')|
|Ends with|endswith(field,'value')|endswith(preamble,'United States of America.')|
|Greater than|field gt value|fingers gt 5<br>created gt 2020-01-05T00:00:00|
|Less than|field lt value|fingers lt 5|
|Greater than or equal to|field ge value|fingers ge 5|
|Less than or equal to|field le value|fingers le 5|

### Filter by joined properties
It is possible to filter by a joined property, even if that property isn't returned in the payload.
Use a forward-slash (/) to indicate a join.

For example:
`/users?filter=roles/name eq "admin"` would return all users that have a related role with name 'admin'.

Works for one-to-many and many-to-many.

To search for empty or non-empty relations, use `eq null` or `ne null` respectively.
For example, to filter for users with no roles assigned:
`/users?filter=roles eq null`

### Ordering
Use the `orderby` query parameter to sort by a top-level property or joined property, ascending or descending.

Examples:

- `/users?orderby=id`
- `/users?orderby=id desc`
- `/users?orderby=supervisor/username`
- `/users?filter=isActive eq true&orderby=logins desc`

### AND / OR
Filters can be combined with `and` and `or`.
Nested filtering with parens is allowed.

Examples:

- `isActive eq true or isActive eq flase`
- `createdTime ge 2021-01-01T00:00:00 and createdTime le 2021-02-01T23:59:59 and userId eq 1`
- `(username eq 'user2' and logins eq 100 and isActive eq false) or (logins gt 1 and username eq 'user3') or contains(note,'backup') or (logins gt 1000 and username eq 'user4' and supervisor/id eq 1)`

