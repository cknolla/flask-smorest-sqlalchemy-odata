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
from flask_smorest import Blueprint
from flask_smorest.utils import unpack_tuple_response
from webargs.flaskparser import FlaskParser
from werkzeug.urls import url_decode
from sqlalchemy import text, Column
from sqlalchemy.orm import Session
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
            default_orderby: Column = None,
    ):
        self.model = model
        self.query = session.query(self.model)
        self.order_by = None
        self.odata_filters = [
            OdataFilter(re.compile(r'contains\((\w+),\'(.+)\'\)'), self._parse_contains),
            OdataFilter(re.compile(r'(\S+)\s+(eq|ne)\s+(null|true|false)'), self._parse_eqbool),
            OdataFilter(re.compile(r'(\S+)\s+eq\s+\'?([^\']*)\'?'), self._parse_eq),
            OdataFilter(re.compile(r'(\S+)\s+ne\s+\'?([^\']*)\'?'), self._parse_ne),
            # OdataFilter(re.compile(r'indexof\((\S+),\'(\S+)\'\)\s+eq\s+-1'), self._parse_indexof),
            OdataFilter(re.compile(r'startswith\((\S+),\'(\S+)\'\)'), self._parse_startswith),
            OdataFilter(re.compile(r'endswith\((\S+),\'(\S+)\'\)'), self._parse_endswith),
            OdataFilter(re.compile(r'(\S+)\s+gt\s+(.+)'), self._parse_gt),
            OdataFilter(re.compile(r'(\S+)\s+lt\s+(.+)'), self._parse_lt),
            OdataFilter(re.compile(r'(\S+)\s+ge\s+(.+)'), self._parse_ge),
            OdataFilter(re.compile(r'(\S+)\s+le\s+(.+)'), self._parse_le),
        ]
        if filters := odata_parameters.get('filter'):
            self._filter_parser(filters)
        self.order_by = text(orderby) \
            if (orderby := odata_parameters.get('orderby')) \
            else default_orderby

    @staticmethod
    def _parse_value(property_name, value_string):
        try:
            dt = datetime.strptime(value_string, '%Y-%m-%dT%H:%M:%S')
            if property_name.endswith('_date'):
                # if the property is only a date (no time component),
                # then strip the time component for equality testing
                date = datetime.date(dt)
                return date
            return dt
        except ValueError:
            return value_string

    def _filter_parser(self, filter_string: str):
        # strip surrounding quotes if they exist
        if filter_string.startswith('('):
            filter_string = filter_string[1:-1]
        segments = filter_string.split('and')
        for segment in segments:
            segment = segment.strip()
            for odata_filter in self.odata_filters:
                if match := re.search(odata_filter.regex, segment):
                    odata_filter.func(match)
                    break

    def _parse_contains(self, match: re.Match):
        decoded_search = next(iter(url_decode(match.group(2), cls=dict)))
        logger.debug(f'decoded_search: {decoded_search}')
        self.query = self.query.filter(
            getattr(
                self.model,
                get_field(match.group(1)),
            ).contains('{}'.format(decoded_search))
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
                getattr(  # get the column
                    self.model,
                    get_field(match.group(1)),
                ),
                operator,
            )(value)  # example: User.username.is_(None)
        )

    def _parse_eq(self, match: re.Match):
        field = get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            getattr(
                self.model,
                field,
            ) == parsed_value
        )

    def _parse_ne(self, match: re.Match):
        field = get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            getattr(
                self.model,
                field,
            ) != parsed_value
        )

    # def _parse_indexof(self, match: re.Match):
    #     self.query = self.query.filter(
    #         getattr(
    #             self.model,
    #             get_field(match.group(1)),
    #         ).notlike(match.group(2))
    #     )

    def _parse_startswith(self, match: re.Match):
        self.query = self.query.filter(
            getattr(
                self.model,
                get_field(match.group(1)),
            ).startswith(match.group(2))
        )

    def _parse_endswith(self, match: re.Match):
        self.query = self.query.filter(
            getattr(
                self.model,
                get_field(match.group(1)),
            ).endswith(match.group(2))
        )

    def _parse_gt(self, match: re.Match):
        field = get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            getattr(
                self.model,
                field,
            ) > parsed_value
        )

    def _parse_lt(self, match: re.Match):
        field = get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            getattr(
                self.model,
                field,
            ) < parsed_value
        )

    def _parse_ge(self, match: re.Match):
        field = get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            getattr(
                self.model,
                field,
            ) >= parsed_value
        )

    def _parse_le(self, match: re.Match):
        field = get_field(match.group(1))
        parsed_value = self._parse_value(field, match.group(2))
        self.query = self.query.filter(
            getattr(
                self.model,
                field,
            ) <= parsed_value
        )


def get_field(field_input: str) -> str:
    """Clean raw user input and return likely field name."""
    return stringcase.snakecase(field_input.strip())


class OdataMixin:
    """Extend Blueprint to add Odata feature"""

    ODATA_ARGUMENTS_PARSER = FlaskParser()

    def odata(self, session):
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
                    OdataSchema, request, location='query')

                # Execute decorated function
                model, status, headers = unpack_tuple_response(
                    func(*args, **kwargs)
                )

                # Apply Odata
                query = Odata(session, model, odata_parameters=odata_params).query

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
    orderby = ma.fields.Integer()


class OdataBlueprint(Blueprint, OdataMixin):
    """Add OdataMixin to flask-smorest blueprint."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prepare_doc_cbks.append(self._prepare_odata_doc)
