import logging
import re
import sys

import connexion.utils as utils
from connexion.exceptions import ResolverError

logger = logging.getLogger('connexion.resolver')

class Controller:

    def get_method_for_operation(self, operation):
        """
        Return the method for the operation name.
        """
        try:
            method = getattr(self, operation)
        except AttributeError:
            raise ResolverError("Controller {controller_type} has no operation '{method}'"
                                    .format(controller_type=self.__class__.__name__, method=operation))
        else:
            return method


class Resolution(object):
    def __init__(self, function, operation_id):
        """
        Represents the result of operation resolution

        :param function: The endpoint function
        :type function: types.FunctionType
        """
        self.function = function
        self.operation_id = operation_id


class Resolver(object):
    def __init__(self, function_resolver=utils.get_function_from_name):
        """
        Standard resolver

        :param function_resolver: Function that resolves functions using an operationId
        :type function_resolver: types.FunctionType
        """
        self.function_resolver = function_resolver

    def resolve(self, operation):
        """
        Default operation resolver

        :type operation: connexion.operation.Operation
        """
        operation_id = self.resolve_operation_id(operation)
        return Resolution(self.resolve_function_from_operation_id(operation_id), operation_id)

    def resolve_operation_id(self, operation):
        """
        Default operationId resolver

        :type operation: connexion.operation.Operation
        """
        spec = operation.operation
        operation_id = spec.get('operationId', '')
        x_router_controller = spec.get('x-swagger-router-controller')
        if x_router_controller is None:
            return operation_id
        return '{}.{}'.format(x_router_controller, operation_id)

    def resolve_function_from_operation_id(self, operation_id):
        """
        Invokes the function_resolver

        :type operation_id: str
        """
        try:
            return self.function_resolver(operation_id)
        except ImportError as e:
            msg = 'Cannot resolve operationId "{}"! Import error was "{}"'.format(operation_id, str(e))
            raise ResolverError(msg, sys.exc_info())
        except (AttributeError, ValueError) as e:
            raise ResolverError(str(e), sys.exc_info())


class RestyResolver(Resolver):
    """
    Resolves endpoint functions using REST semantics (unless overridden by specifying operationId)
    """

    def __init__(self, default_module_name, collection_endpoint_name='search'):
        """
        :param default_module_name: Default module name for operations
        :type default_module_name: str
        """
        Resolver.__init__(self)
        self.default_module_name = default_module_name
        self.collection_endpoint_name = collection_endpoint_name

    def resolve_operation_id(self, operation):
        """
        Resolves the operationId using REST semantics unless explicitly configured in the spec

        :type operation: connexion.operation.Operation
        """
        if operation.operation.get('operationId'):
            return Resolver.resolve_operation_id(self, operation)

        return self.resolve_operation_id_using_rest_semantics(operation)

    def resolve_operation_id_using_rest_semantics(self, operation):
        """
        Resolves the operationId using REST semantics

        :type operation: connexion.operation.Operation
        """
        path_match = re.search(
            '^/?(?P<resource_name>([\w\-](?<!/))*)(?P<trailing_slash>/*)(?P<extended_path>.*)$', operation.path
        )

        def get_controller_name():
            x_router_controller = operation.operation.get('x-swagger-router-controller')

            name = self.default_module_name
            resource_name = path_match.group('resource_name')

            if x_router_controller:
                name = x_router_controller

            elif resource_name:
                resource_controller_name = resource_name.replace('-', '_')
                name += '.' + resource_controller_name

            return name

        def get_function_name():
            method = operation.method

            is_collection_endpoint = \
                method.lower() == 'get' \
                and path_match.group('resource_name') \
                and not path_match.group('extended_path')

            return self.collection_endpoint_name if is_collection_endpoint else method.lower()

        return '{}.{}'.format(get_controller_name(), get_function_name())

# TODO: Rename this 
class ObjectResolver(Resolver):
    """
    Resolves the operationId using a collection of instanctated controllers
    """
    def __init__(self):
        self.controllers = {}

    def add_controller(self, controller):
        """
        Register a controller instance to be resolved.

        :type controller Controller
        """
        self.controllers[controller.__class__.__controllername__] = controller
    
    def resolve_operation_id(self, operation):
        """
        Resolves the operationId using REST semantics unless explicitly configured in the spec

        :type operation: connexion.operation.Operation
        """

        # if no explicit operation_id
        # if no class, derive by how many are there
        # if otherwise, use classname.methodname
        # operationId = Resolver.resolve_operation_id(operation)

        spec = operation.operation
        operation_id = spec.get('operationId', '')
        x_router_controller = spec.get('x-swagger-router-controller')

        if x_router_controller:
            controller_name = x_router_controller
        else:
            if len(self.controllers) == 1:
                controller_name = next(iter(self.controllers.keys()))
            else:
                raise ResolverError("Could not determine which controller to use")

        if operation_id:
            method_name = operation_id
        else:
            method_name = ObjectResolver.method_from_operation(operation)
        
        # TODO: Split into own function
        return "{}.{}".format(controller_name, method_name)

    @staticmethod
    def method_from_operation(operation):
        # FIXME: Format paths with multiple slashes
        return "{}_{}".format(operation.method.lower(), operation.path.strip('/'))
    
    def resolve_function_from_operation_id(self, operationId):
        """
        Resolve handler from the added controller instances.
        """
        parts = operationId.split('.')

        controller_name = parts[2]
        method_name = parts[3]

        controller = self.controllers[controller_name]

        handler = controller.get_method_for_operation(method_name)
        return handler