"""Odata library for flask-smorest and sqlalchemy."""

import logging
import re
from collections import OrderedDict, namedtuple
from copy import deepcopy
from functools import wraps
from http import HTTPStatus
from datetime import datetime
from operator import or_

import stringcase
from flask import request
from flask_smorest import Blueprint as FSBlueprint
from flask_smorest.utils import unpack_tuple_response
from sqlalchemy.sql import expression
from webargs.flaskparser import FlaskParser
from werkzeug.exceptions import BadRequest
from sqlalchemy import DateTime, Date, and_
from sqlalchemy.orm import Session, RelationshipProperty, InstrumentedAttribute, aliased
import marshmallow as ma

logger = logging.getLogger("app." + __name__)


OdataFilter = namedtuple("OdataFilter", ["regex", "func"])
_DEFAULT_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class Odata:
    """Class which will apply sorting and filtering."""

    def __init__(
        self,
        session: Session,
        model,
        odata_parameters: OrderedDict,
        default_orderby: str = None,
    ):
        self.model = model
        self.query = session.query(self.model)
        self.odata_filters = [
            OdataFilter(
                re.compile(r"contains\(([^,]+),[\'\"]([^\'\"]*)[\'\"]\)"),
                self._parse_contains,
            ),
            OdataFilter(
                re.compile(r"(\S+)\s+(eq|ne)\s+(null|true|false)"),
                self._parse_eqbool,
            ),
            OdataFilter(
                re.compile(r"(\S+)\s+eq\s+[\'\"]?([^\'\"]*)[\'\"]?"),
                self._parse_eq,
            ),
            OdataFilter(
                re.compile(r"(\S+)\s+ne\s+[\'\"]?([^\'\"]*)[\'\"]?"),
                self._parse_ne,
            ),
            OdataFilter(
                re.compile(r"startswith\((\S+),\s*[\'\"]([^\'\"]*)[\'\"]\)"),
                self._parse_startswith,
            ),
            OdataFilter(
                re.compile(r"endswith\((\S+),\s*[\'\"]([^\'\"]*)[\'\"]\)"),
                self._parse_endswith,
            ),
            OdataFilter(
                re.compile(r"(\S+)\s+gt\s+(.+)"),
                self._parse_gt,
            ),
            OdataFilter(
                re.compile(r"(\S+)\s+lt\s+(.+)"),
                self._parse_lt,
            ),
            OdataFilter(
                re.compile(r"(\S+)\s+ge\s+(.+)"),
                self._parse_ge,
            ),
            OdataFilter(
                re.compile(r"(\S+)\s+le\s+(.+)"),
                self._parse_le,
            ),
            OdataFilter(
                re.compile(r"(\S+)\s+in\s+\(([^)]*)\)"),
                self._parse_in,
            ),
        ]
        if filters := odata_parameters.get("filter"):
            logger.info(f"Parsing filter string [{filters}]")
            self._filter_parser(filters)
        if (orderby := odata_parameters.get("orderby", default_orderby)) is not None:
            logger.info(f"Parsing orderby string [{orderby}]")
            self._orderby_parser(orderby)

    @staticmethod
    def _parse_value(field: InstrumentedAttribute, value_string: str):
        if hasattr(field, "property"):
            field_type = field.property.columns[0].type
            if isinstance(field_type, DateTime):
                return datetime.strptime(value_string, _DEFAULT_DATETIME_FORMAT)
            elif isinstance(field_type, Date):
                return datetime.date(
                    datetime.strptime(value_string, _DEFAULT_DATETIME_FORMAT)
                )
        return value_string

    def get_field(self, field_input: str) -> InstrumentedAttribute:
        """Clean raw user input and return likely field name."""
        clean_fields = [
            stringcase.snakecase(field) for field in field_input.strip().split("/")
        ]
        model = self.model
        for field_name in clean_fields:
            if (field := getattr(model, field_name, None)) is None:
                raise BadRequest(
                    description=f"{model.__name__} has no column named {field_name}",
                )
            if field_name != clean_fields[-1]:
                if not hasattr(field, "property") or not isinstance(
                    field.property, RelationshipProperty
                ):
                    raise BadRequest(
                        description=f"{model.__name__} has no relationship property "
                        f"named {field_name}",
                    )
                field_class = field.property.mapper.class_
                if field_class == model:
                    # handle self-referential joins
                    model = aliased(field_class)
                    # noqa https://docs.sqlalchemy.org/en/14/orm/self_referential.html#self-referential-query-strategies
                    self.query = self.query.join(field.of_type(model))
                else:
                    model = field_class
                    self.query = self.query.join(field)
            else:
                return field

    def _orderby_parser(self, orderby: str):
        orderby_strs = orderby.split(" ")
        if len(orderby_strs) > 2:
            raise BadRequest(
                description="The orderby parameter should only contain [columnName direction]",
            )
        direction = "asc"
        if len(orderby_strs) == 2:
            direction = orderby_strs[1].lower()
            if direction not in (
                "asc",
                "desc",
            ):
                raise BadRequest(
                    description="orderby direction can only be [asc] or [desc]",
                )
        field = self.get_field(orderby_strs[0])  # ensure field is valid and exists
        self.query = self.query.order_by(getattr(field, direction)())

    @staticmethod
    def _tokenize_filter_string(filter_string: str) -> str:
        """Validate parens in filter string and convert and/or operators into more parseable forms."""  # noqa
        in_quotes = ""
        paren_depth = 0
        skipping = 0
        altered_filter_string = ""
        for index, char in enumerate(filter_string):
            altered_char = char
            if skipping > 0:
                skipping -= 1
                continue
            if (in_quotes and char == in_quotes) or (
                not in_quotes and char in ("'", '"')
            ):
                in_quotes = (
                    "" if in_quotes else char
                )  # only reset to false if same quote type
            elif not in_quotes and char == "(":
                paren_depth += 1
                # altered_char = '[_(_]'
            elif not in_quotes and char == ")":
                paren_depth -= 1
                # altered_char = '[_)_]'
            elif not in_quotes and filter_string[index : index + 5] == " and ":
                altered_char = " [_AND_] "
                skipping = 4
            elif not in_quotes and filter_string[index : index + 4] == " or ":
                altered_char = " [_OR_] "
                skipping = 3
            altered_filter_string += altered_char
        if in_quotes:
            raise BadRequest(
                description="Quotes in filter string are mismatched.",
            )
        if paren_depth != 0:
            raise BadRequest(description="Parentheses in filter string are mismatched.")
        return altered_filter_string

    def _filter_parser(self, filter_string: str):
        filter_expressions = []
        filter_string = self._tokenize_filter_string(filter_string)
        if " [_AND_] " in filter_string and " [_OR_] " in filter_string:
            raise BadRequest(
                description="Currently, AND and OR cannot be mixed in filters."
            )
        elif " [_OR_] " in filter_string:
            operator = or_
            segments = filter_string.split(" [_OR_] ")
        else:
            operator = and_
            segments = filter_string.split(" [_AND_] ")
        for segment in segments:
            segment = segment.strip()
            filter_found = False
            for odata_filter in self.odata_filters:
                if match := re.search(odata_filter.regex, segment):
                    filter_expressions.append(odata_filter.func(match))
                    filter_found = True
                    break
            if not filter_found:
                raise BadRequest(
                    description=f"No available filter matches segment {segment}",
                )
        self.query = self.query.filter(
            operator(
                *filter_expressions,
            )
        )

    def _parse_contains(self, match: re.Match) -> expression:
        # self.query can get modified within get_field, so don't embed that call within filter
        return self.get_field(match.group(1)).contains(match.group(2))

    def _parse_eqbool(self, match: re.Match) -> expression:
        operator = "is_" if match.group(2) == "eq" else "isnot"
        value = {
            "null": None,
            "true": True,
            "false": False,
        }[match.group(3)]
        field = self.get_field(match.group(1))  # get the field to filter by
        return getattr(  # get the operator function 'is_' or 'isnot' of the column
            field,
            operator,
        )(
            value
        )  # example: User.username.is_(None)

    def _parse_eq(self, match: re.Match) -> expression:
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field == parsed_value

    def _parse_ne(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field != parsed_value

    def _parse_startswith(self, match: re.Match):
        return self.get_field(match.group(1)).startswith(match.group(2))

    def _parse_endswith(self, match: re.Match):
        return self.get_field(match.group(1)).endswith(match.group(2))

    def _parse_gt(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field > parsed_value

    def _parse_lt(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field < parsed_value

    def _parse_ge(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field >= parsed_value

    def _parse_le(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field <= parsed_value

    def _parse_in(self, match: re.Match):
        field = self.get_field(match.group(1))
        values = [
            self._parse_value(field, value.strip(" '\""))
            for value in match.group(2).split(",")
        ]
        return field.in_(values)


class OdataMixin:
    """Extend Blueprint to add Odata feature"""

    ODATA_ARGUMENTS_PARSER = FlaskParser()

    def odata(self, session: Session, default_orderby: str = None):
        """Decorator adding odata capability to endpoint."""

        parameters = {
            "in": "query",
            "schema": OdataSchema,
        }

        error_status_code = self.ODATA_ARGUMENTS_PARSER.DEFAULT_VALIDATION_STATUS

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                odata_params = self.ODATA_ARGUMENTS_PARSER.parse(
                    OdataSchema, request, location="query"
                )
                # Execute decorated function
                model, status, headers = unpack_tuple_response(func(*args, **kwargs))
                # Apply Odata
                query = Odata(
                    session=session,
                    model=model,
                    odata_parameters=odata_params,
                    default_orderby=default_orderby,
                ).query
                return query, status, headers

            # Add odata params to doc info in wrapper object
            wrapper._apidoc = deepcopy(getattr(wrapper, "_apidoc", {}))
            wrapper._apidoc["odata"] = {
                "parameters": parameters,
                "response": {
                    error_status_code: HTTPStatus(error_status_code).name,
                },
            }

            return wrapper

        return decorator

    def _prepare_odata_doc(self, doc, doc_info, *, spec, **kwargs):
        operation = doc_info.get("odata")
        if operation:
            doc.setdefault("parameters", []).append(operation["parameters"])
            doc.setdefault("responses", {}).update(operation["response"])
        return doc


class OdataSchema(ma.Schema):
    """Deserializes pagination params into PaginationParameters"""

    class Meta:
        datetimeformat = _DEFAULT_DATETIME_FORMAT
        ordered = True
        unknown = ma.EXCLUDE

    filter = ma.fields.String()
    orderby = ma.fields.String()


class Blueprint(FSBlueprint, OdataMixin):
    """Add OdataMixin to flask-smorest blueprint."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prepare_doc_cbks.append(self._prepare_odata_doc)
