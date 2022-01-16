"""Odata library for flask-smorest and sqlalchemy."""

import logging
import re
from collections import OrderedDict, namedtuple
from copy import deepcopy
from dataclasses import dataclass, field
from functools import wraps
from http import HTTPStatus
from datetime import datetime
from typing import Callable

import stringcase
from flask import request
from flask_smorest import Blueprint as FSBlueprint
from flask_smorest.utils import unpack_tuple_response
from sqlalchemy.sql import expression
from sqlalchemy.sql.elements import BooleanClauseList
from webargs.flaskparser import FlaskParser
from werkzeug.exceptions import BadRequest
from sqlalchemy import DateTime, Date, and_, or_
from sqlalchemy.orm import Session, RelationshipProperty, InstrumentedAttribute, aliased
import marshmallow as ma

logger = logging.getLogger("app." + __name__)


OdataFilter = namedtuple("OdataFilter", ["regex", "func"])
_DEFAULT_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d"


@dataclass
class Segment:
    """A nesting layer of expression segments."""

    depth: int = 0
    segments: list["Segment"] = field(default_factory=list)
    junction: Callable = None
    expression: expression = None
    string: str = ""


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
        self.paren_depth = 0
        self.filter_string = ""
        self.filter_string_iterator = None
        self.odata_filters = [
            OdataFilter(
                re.compile(r"contains\(([^,]+),\s*[\'\"]([^\'\"]*)[\'\"]\)"),
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
                re.compile(r"(\S+)\s+in\s*\(([^)]*)\)"),
                self._parse_in,
            ),
        ]
        if filter_string := odata_parameters.get("filter"):
            logger.info(f"Parsing filter string [{filter_string}]")
            self.filter_string = filter_string
            self.filter_string_iterator = enumerate(self.filter_string)
            self._filter_parser()
        if (orderby := odata_parameters.get("orderby", default_orderby)) is not None:
            logger.info(f"Parsing orderby string [{orderby}]")
            self._orderby_parser(orderby)
        logger.info(
            f"Final query:\n{self.query.statement.compile(compile_kwargs={'literal_binds': True})}"
        )

    @staticmethod
    def _parse_value(field: InstrumentedAttribute, value_string: str):
        if hasattr(field, "property"):
            field_type = field.property.columns[0].type
            if isinstance(field_type, DateTime):
                return datetime.strptime(value_string, _DEFAULT_DATETIME_FORMAT)
            elif isinstance(field_type, Date):
                return datetime.date(
                    datetime.strptime(value_string, _DEFAULT_DATE_FORMAT)
                )
        return value_string

    def _get_field(self, field_input: str) -> InstrumentedAttribute:
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
                    self.query = self.query.outerjoin(field.of_type(model))
                else:
                    model = field_class
                    self.query = self.query.outerjoin(field)
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
        field = self._get_field(orderby_strs[0])  # ensure field is valid and exists
        self.query = self.query.order_by(getattr(field, direction)())
        logger.debug(
            "Query after orderby:\n"
            f"{self.query.statement.compile(compile_kwargs={'literal_binds': True})}"
        )

    def _filter_parser(self):
        segments = self._parse_segments()
        logger.info(f"{segments=}")
        filters = self._build_filters(segments)[0]
        self.query = self.query.filter(*filters)
        logger.debug(
            "Query after filter:\n"
            f"{self.query.statement.compile(compile_kwargs={'literal_binds': True})}"
        )

    def _parse_segments(self, last_junction=and_) -> list["Segment"]:
        """Validate parens in filter string and convert and/or operators into more parseable forms."""  # noqa
        in_quotes = ""
        skipping = 0
        filter_function = False
        expression_str = ""
        segments: list["Segment"] = [
            Segment(
                depth=self.paren_depth,
                junction=last_junction,
                expression=None,
                string="",
            )
        ]
        last_junction = None

        def _is_filter_function():
            """Determine whether paren belongs to filter function or not."""
            nonlocal index
            try:
                # must search from shortest to longest to avoid missing on index error
                if (
                    self.filter_string[index - 2 : index] == "in"
                    or self.filter_string[index - 3 : index] == "in "
                    or self.filter_string[index - 8 : index] in ("contains", "endswith")
                    or self.filter_string[index - 10 : index] == "startswith"
                ):
                    return True
            except IndexError:
                return False
            return False

        def _close_expression():
            """Add expression to segment if not empty and reset."""
            nonlocal expression_str
            if expression_str:
                segments.append(
                    Segment(
                        depth=self.paren_depth,
                        junction=last_junction,
                        expression=self._parse_expression(expression_str),
                        string=expression_str,
                    )
                )
            expression_str = ""

        def _validate_clean_segment():
            """Check for dangling parens or quotes and error if found."""
            if in_quotes:
                raise BadRequest(
                    description="Quotes in filter string are mismatched.",
                )
            if self.paren_depth != segments[0].depth or filter_function:
                raise BadRequest(
                    description="Parentheses in filter string are mismatched."
                )

        for index, char in self.filter_string_iterator:
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
                if not (filter_function := _is_filter_function()):
                    if segments[-1].segments:
                        segments.append(
                            Segment(
                                depth=self.paren_depth,
                                junction=last_junction,
                                expression=None,
                                string="",
                            )
                        )
                    self.paren_depth += 1
                    segments[-1].segments = self._parse_segments(last_junction)
                    continue
            elif not in_quotes and char == ")":
                if filter_function:
                    filter_function = False
                else:
                    _close_expression()
                    _validate_clean_segment()
                    self.paren_depth -= 1
                    return segments
            elif not in_quotes and self.filter_string[index : index + 5] == " and ":
                _close_expression()
                last_junction = and_
                skipping = 4
                continue
            elif not in_quotes and self.filter_string[index : index + 4] == " or ":
                _close_expression()
                last_junction = or_
                skipping = 3
                continue
            expression_str += char
        _validate_clean_segment()
        if expression_str:
            _close_expression()
        return segments

    def _build_filters(
        self, segments: list["Segment"]
    ) -> tuple[list[BooleanClauseList], Callable]:
        """Build SQLAlchemy filters from parsed segments."""
        filters = []
        expressions = []
        junction = None
        outer_junction = and_
        for segment in segments:
            if segment.expression is not None:
                if junction is None:
                    junction = segment.junction
                elif junction != segment.junction and expressions:
                    filters.append(
                        junction(
                            *expressions,
                        )
                    )
                    junction = segment.junction
                    expressions = []
                expressions.append(segment.expression)
            if segment.segments:
                inner_filters, inner_junction = self._build_filters(segment.segments)
                if (
                    junction_target := (expressions.pop() if expressions else None)
                ) is not None:
                    expressions.append(
                        inner_junction(
                            junction_target,
                            *inner_filters,
                        )
                    )
                else:
                    expressions.append(
                        inner_junction(
                            *inner_filters,
                        )
                    )
        if expressions:
            outer_junction = (
                segments[0].junction if segments[0].junction is not None else and_
            )
            if not junction:
                junction = (
                    segments[-1].junction
                    if segments and segments[-1].junction
                    else and_
                )
            filters.append(
                junction(
                    *expressions,
                )
            )
        return filters, outer_junction

    def _parse_expression(self, expression_str: str) -> expression:
        """Parse SQLAlchemy expression from string."""
        for odata_filter in self.odata_filters:
            if match := re.search(odata_filter.regex, expression_str):
                return odata_filter.func(match)
        raise BadRequest(
            description=f"No available filter matches segment {expression_str}",
        )

    def _parse_contains(self, match: re.Match) -> expression:
        # self.query can get modified within get_field, so don't embed that call within filter
        return self._get_field(match.group(1)).contains(match.group(2))

    def _parse_eqbool(self, match: re.Match) -> expression:
        operator = "__eq__" if match.group(2) == "eq" else "__ne__"
        value = {
            "null": None,
            "true": True,
            "false": False,
        }[match.group(3)]
        field = self._get_field(match.group(1))  # get the field to filter by
        return getattr(  # get the operator function 'is_' or 'isnot' of the column
            field,
            operator,
        )(
            value
        )  # example: User.username.is_(None)

    def _parse_eq(self, match: re.Match) -> expression:
        field = self._get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field == parsed_value

    def _parse_ne(self, match: re.Match):
        field = self._get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field != parsed_value

    def _parse_startswith(self, match: re.Match):
        return self._get_field(match.group(1)).startswith(match.group(2))

    def _parse_endswith(self, match: re.Match):
        return self._get_field(match.group(1)).endswith(match.group(2))

    def _parse_gt(self, match: re.Match):
        field = self._get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field > parsed_value

    def _parse_lt(self, match: re.Match):
        field = self._get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field < parsed_value

    def _parse_ge(self, match: re.Match):
        field = self._get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field >= parsed_value

    def _parse_le(self, match: re.Match):
        field = self._get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        return field <= parsed_value

    def _parse_in(self, match: re.Match):
        field = self._get_field(match.group(1))
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
        dateformat = _DEFAULT_DATE_FORMAT
        ordered = True
        unknown = ma.EXCLUDE

    filter = ma.fields.String()
    orderby = ma.fields.String()


class Blueprint(FSBlueprint, OdataMixin):
    """Add OdataMixin to flask-smorest blueprint."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prepare_doc_cbks.append(self._prepare_odata_doc)
