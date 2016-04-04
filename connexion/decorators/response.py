"""
Copyright 2015 Zalando SE

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific
 language governing permissions and limitations under the License.
"""

# Decorators to change the return type of endpoints
from flask import json
import functools
import logging
from ..exceptions import NonConformingResponseBody, NonConformingResponseHeaders
from ..problem import problem
from ..utils import produces_json
from .validation import ResponseBodyValidator
from .decorator import BaseDecorator
from jsonschema import ValidationError


logger = logging.getLogger('connexion.decorators.response')


class ResponseValidator(BaseDecorator):
    def __init__(self, operation,  mimetype):
        """
        :type operation: Operation
        :type mimetype: str
        """
        self.operation = operation
        self.mimetype = mimetype

    def validate_response(self, data, status_code, headers):
        """
        Validates the Response object based on what has been declared in the specification.
        Ensures the response body matches the declated schema.
        :type data: dict
        :type status_code: int
        :type headers: dict
        :rtype bool | None
        """
        response_definitions = self.operation.operation["responses"]
        response_definition = response_definitions.get(str(status_code), {})
        response_definition = self.operation.resolve_reference(response_definition)
        # TODO handle default response definitions

        if response_definition and "schema" in response_definition \
           and (produces_json([self.mimetype]) or
                self.mimetype == 'text/plain'):  # text/plain can also be validated with json schema
            schema = response_definition.get("schema")
            v = ResponseBodyValidator(schema)
            try:
                # For cases of custom encoders, we need to encode and decode to
                # transform to the actual types that are going to be returned.
                data = json.dumps(data)
                data = json.loads(data)

                v.validate_schema(data)
            except ValidationError as e:
                raise NonConformingResponseBody(message=str(e))

        if response_definition and response_definition.get("headers"):
            response_definition_header_keys = response_definition.get("headers").keys()
            if not all(item in headers.keys() for item in response_definition_header_keys):
                raise NonConformingResponseHeaders(
                    message="Keys in header don't match response specification. Difference: %s"
                    % list(set(headers.keys()).symmetric_difference(set(response_definition_header_keys))))
        return True

    def __call__(self, function):
        """
        :type function: types.FunctionType
        :rtype: types.FunctionType
        """
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            result = function(*args, **kwargs)
            try:
                data, status_code, headers = self.get_full_response(result)
                self.validate_response(data, status_code, headers)
            except NonConformingResponseBody as e:
                return problem(500, e.reason, e.message)
            except NonConformingResponseHeaders as e:
                return problem(500, e.reason, e.message)
            return result

        return wrapper

    def __repr__(self):
        """
        :rtype: str
        """
        return '<ResponseValidator>'
