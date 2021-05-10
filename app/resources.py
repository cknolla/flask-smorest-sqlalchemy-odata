"""Some resources to test with."""
from http import HTTPStatus

from flask.views import MethodView

from app.models import seed
from app.db import db
from app import schemas, models
from app.api import CursorPage
from odata.odata import OdataBlueprint

resources = OdataBlueprint(
    'resources',
    __name__,
    url_prefix='/',
    description='root resources',
)


@resources.route('/')
class Create(MethodView):

    @resources.response(HTTPStatus.OK, schemas.Message)
    def get(self):
        db.drop_all()
        db.create_all()
        seed()
        return {
            'message': 'Database recreated.',
        }


@resources.route('/user')
class User(MethodView):

    @resources.response(HTTPStatus.OK, schemas.User(many=True))
    @resources.paginate(CursorPage)
    @resources.odata(db.session)
    def get(self):
        return models.User
