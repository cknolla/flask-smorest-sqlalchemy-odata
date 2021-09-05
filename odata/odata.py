"""Odata library for flask-smorest and sqlalchemy."""

import logging
import re
from collections import OrderedDict, namedtuple
from copy import deepcopy
from functools import wraps
from http import HTTPStatus
from datetime import datetime

import stringcase
from flask import request
from flask_smorest import Blueprint as FSBlueprint
from flask_smorest.utils import unpack_tuple_response
from webargs.flaskparser import FlaskParser
from werkzeug.exceptions import BadRequest
from sqlalchemy import DateTime, Date
from sqlalchemy.orm import Session, RelationshipProperty, InstrumentedAttribute, aliased
import marshmallow as ma

logger = logging.getLogger('app.' + __name__)


OdataFilter = namedtuple('OdataFilter', ['regex', 'func'])


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
                re.compile(r'contains\((\w+),[\'\"]([^\'\"]*)[\'\"]\)'),
                self._parse_contains,
            ), OdataFilter(
                re.compile(r'(\S+)\s+(eq|ne)\s+(null|true|false)'),
                self._parse_eqbool,
            ), OdataFilter(
                re.compile(r'(\S+)\s+eq\s+[\'\"]?([^\'\"]*)[\'\"]?'),
                self._parse_eq,
            ), OdataFilter(
                re.compile(r'(\S+)\s+ne\s+[\'\"]?([^\'\"]*)[\'\"]?'),
                self._parse_ne,
            ), OdataFilter(
                re.compile(r'startswith\((\S+),\s*[\'\"]([^\'\"]*)[\'\"]\)'),
                self._parse_startswith,
            ), OdataFilter(
                re.compile(r'endswith\((\S+),\s*[\'\"]([^\'\"]*)[\'\"]\)'),
                self._parse_endswith,
            ), OdataFilter(
                re.compile(r'(\S+)\s+gt\s+(.+)'),
                self._parse_gt,
            ), OdataFilter(
                re.compile(r'(\S+)\s+lt\s+(.+)'),
                self._parse_lt,
            ), OdataFilter(
                re.compile(r'(\S+)\s+ge\s+(.+)'),
                self._parse_ge,
            ), OdataFilter(
                re.compile(r'(\S+)\s+le\s+(.+)'),
                self._parse_le,
            ), OdataFilter(
                re.compile(r'(\S+)\s+in\s+\(([^)]*)\)'),
                self._parse_in,
            )
        ]
        if filters := odata_parameters.get('filter'):
            logger.info(f'Parsing filter string [{filters}]')
            self._filter_parser(filters)
        if (orderby := odata_parameters.get('orderby', default_orderby)) is not None:
            logger.info(f'Parsing orderby string [{orderby}]')
            self._orderby_parser(orderby)

    @staticmethod
    def _parse_value(field: InstrumentedAttribute, value_string: str):
        if hasattr(field, 'property'):
            field_type = field.property.columns[0].type
            if isinstance(field_type, DateTime):
                return datetime.strptime(value_string, '%Y-%m-%dT%H:%M:%S')
            elif isinstance(field_type, Date):
                return datetime.date(datetime.strptime(value_string, '%Y-%m-%dT%H:%M:%S'))
        return value_string

    def get_field(self, field_input: str) -> InstrumentedAttribute:
        """Clean raw user input and return likely field name."""
        clean_fields = [stringcase.snakecase(field) for field in field_input.strip().split('/')]
        model = self.model
        for field_name in clean_fields:
            if (field := getattr(model, field_name, None)) is None:
                raise BadRequest(
                    description=f'{model.__name__} has no column named {field_name}',
                )
            if field_name != clean_fields[-1]:
                if not hasattr(field, 'property') or \
                        not isinstance(field.property, RelationshipProperty):
                    raise BadRequest(
                        description=f'{model.__name__} has no relationship property '
                                    f'named {field_name}',
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
        orderby_strs = orderby.split(' ')
        if len(orderby_strs) > 2:
            raise BadRequest(
                description='The orderby parameter should only contain [columnName direction]',
            )
        direction = 'asc'
        if len(orderby_strs) == 2:
            direction = orderby_strs[1].lower()
            if direction not in ('asc', 'desc',):
                raise BadRequest(
                    description='orderby direction can only be [asc] or [desc]',
                )
        field = self.get_field(orderby_strs[0])  # ensure field is valid and exists
        self.query = self.query.order_by(getattr(field, direction)())

    def _filter_parser(self, filter_string: str):
        # strip surrounding quotes if they exist
        if filter_string.startswith('('):
            filter_string = filter_string[1:-1]
        segments = filter_string.split(' and ')
        for segment in segments:
            segment = segment.strip()
            filter_found = False
            for odata_filter in self.odata_filters:
                if match := re.search(odata_filter.regex, segment):
                    odata_filter.func(match)
                    filter_found = True
                    break
            if not filter_found:
                raise BadRequest(
                    description=f'No available filter matches segment {segment}',
                )

    def _parse_contains(self, match: re.Match):
        # value = next(iter(url_decode(match.group(2), cls=dict)))
        self.query = self.query.filter(
            self.get_field(match.group(1)).contains(match.group(2)),
        )

    def _parse_eqbool(self, match: re.Match):
        operator = 'is_' if match.group(2) == 'eq' else 'isnot'
        value = {
            'null': None,
            'true': True,
            'false': False,
        }[match.group(3)]
        self.query = self.query.filter(
            getattr(  # get the operator function 'is_' or 'isnot' of the column
                self.get_field(match.group(1)),  # get the field to filter by
                operator,
            )(value)  # example: User.username.is_(None)
        )

    def _parse_eq(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            field == parsed_value
        )

    def _parse_ne(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            field != parsed_value
        )

    def _parse_startswith(self, match: re.Match):
        self.query = self.query.filter(
            self.get_field(match.group(1)).startswith(match.group(2)),
        )

    def _parse_endswith(self, match: re.Match):
        self.query = self.query.filter(
            self.get_field(match.group(1)).endswith(match.group(2)),
        )

    def _parse_gt(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            field > parsed_value
        )

    def _parse_lt(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            field < parsed_value
        )

    def _parse_ge(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            field >= parsed_value
        )

    def _parse_le(self, match: re.Match):
        field = self.get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            field <= parsed_value
        )

    def _parse_in(self, match: re.Match):
        field = self.get_field(match.group(1))
        values = [
            self._parse_value(field, value.strip(' \'"'))
            for value
            in match.group(2).split(',')
        ]
        self.query = self.query.filter(
            field.in_(values)
        )


class OdataMixin:
    """Extend Blueprint to add Odata feature"""

    ODATA_ARGUMENTS_PARSER = FlaskParser()

    def odata(self, session: Session, default_orderby: str = None):
        """Decorator adding odata capability to endpoint."""

        parameters = {
            'in': 'query',
            'schema': OdataSchema,
        }

        error_status_code = (
            self.ODATA_ARGUMENTS_PARSER.DEFAULT_VALIDATION_STATUS
        )

        def decorator(func):

            @wraps(func)
            def wrapper(*args, **kwargs):
                odata_params = self.ODATA_ARGUMENTS_PARSER.parse(
                    OdataSchema, request, location='query'
                )
                # Execute decorated function
                model, status, headers = unpack_tuple_response(
                    func(*args, **kwargs)
                )
                # Apply Odata
                query = Odata(
                    session=session,
                    model=model,
                    odata_parameters=odata_params,
                    default_orderby=default_orderby,
                ).query
                return query, status, headers

            # Add odata params to doc info in wrapper object
            wrapper._apidoc = deepcopy(getattr(wrapper, '_apidoc', {}))
            wrapper._apidoc['odata'] = {
                'parameters': parameters,
                'response': {
                    error_status_code:
                        HTTPStatus(error_status_code).name,
                }
            }

            return wrapper
        return decorator

    def _prepare_odata_doc(self, doc, doc_info, *, spec, **kwargs):
        operation = doc_info.get('odata')
        if operation:
            doc.setdefault('parameters', []).append(operation['parameters'])
            doc.setdefault('responses', {}).update(operation['response'])
        return doc


class OdataSchema(ma.Schema):
    """Deserializes pagination params into PaginationParameters"""

    class Meta:
        ordered = True
        unknown = ma.EXCLUDE

    filter = ma.fields.String()
    orderby = ma.fields.String()


class Blueprint(FSBlueprint, OdataMixin):
    """Add OdataMixin to flask-smorest blueprint."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prepare_doc_cbks.append(self._prepare_odata_doc)
