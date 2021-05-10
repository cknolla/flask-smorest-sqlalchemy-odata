"""Define resource schemas."""
import stringcase
from marshmallow import Schema, fields
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema

from app import models


class CamelCaseSchema(Schema):
    # https://marshmallow.readthedocs.io/en/latest/examples.html#inflection-camel-casing-keys
    def on_bind_field(self, field_name, field_obj):
        field_obj.data_key = stringcase.camelcase((field_obj.data_key or field_name))


class CamelCaseSQLAlchemyAutoSchema(SQLAlchemyAutoSchema, CamelCaseSchema):
    pass


class Message(CamelCaseSchema):
    message = fields.String(dump_only=True)


class Comment(CamelCaseSQLAlchemyAutoSchema):
    class Meta:
        model = models.Comment


class User(CamelCaseSQLAlchemyAutoSchema):
    class Meta:
        model = models.User


class Role(CamelCaseSQLAlchemyAutoSchema):
    class Meta:
        model = models.Role
