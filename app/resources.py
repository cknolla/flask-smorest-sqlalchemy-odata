"""Some resources to test with."""
from http import HTTPStatus

from flask.views import MethodView

from app.db import db
from app import schemas, models
from app.api import CursorPage
from odata import Blueprint

resources = Blueprint(
    "resources",
    __name__,
    url_prefix="/",
    description="root resources",
)


@resources.route("/")
class Create(MethodView):
    @resources.response(HTTPStatus.OK, schemas.Message)
    def get(self):
        db.drop_all()
        db.create_all()
        return {
            "message": "Database recreated.",
        }


@resources.route("/users")
class User(MethodView):
    @resources.response(HTTPStatus.OK, schemas.User(many=True))
    @resources.paginate(CursorPage)
    @resources.odata(db.session)
    def get(self):
        return models.User


@resources.route("/comments")
class Comment(MethodView):
    @resources.response(HTTPStatus.OK, schemas.Comment(many=True))
    @resources.paginate(CursorPage)
    @resources.odata(db.session)
    def get(self):
        return models.Comment


@resources.route("/roles")
class Role(MethodView):
    @resources.response(HTTPStatus.OK, schemas.Role(many=True))
    @resources.paginate(CursorPage)
    @resources.odata(db.session, default_orderby="id desc")
    def get(self):
        return models.Role
