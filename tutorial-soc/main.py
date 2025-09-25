from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import IDomainModel, IEntity
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule
import clr
from System.Text.Json import JsonSerializer
import json
import traceback
from typing import Any, Dict, Callable
from dependency_injector import containers, providers
from dependency_injector.wiring import inject, Provide

# pythonnet库嵌入C#代码
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")


# 运行时环境提供的工具
PostMessage("backend:clear", '')  # 清理IDE控制台日志
ShowDevTools()  # 打开前端开发者工具

# 运行时环境提供的上下文变量如下
# currentApp：mendix model
# root：untyped model
# dockingWindowService

# region Utilities (Unchanged)


def serialize_json_object(json_object: Any) -> str:
    import System.Text.Json
    return System.Text.Json.JsonSerializer.Serialize(json_object)


def deserialize_json_string(json_string: str) -> Any:
    return json.loads(json_string)


class TransactionManager:
    """with TransactionManager(currentApp, f"your transaction name"):"""

    def __init__(self, app, transaction_name):
        self.app = app
        self.name = transaction_name
        self.transaction = None

    def __enter__(self):
        self.transaction = self.app.StartTransaction(self.name)
        return self.transaction

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.transaction.Commit()
        else:
            self.transaction.Rollback()
        self.transaction.Dispose()
        return False
# endregion

# ===================================================================
# 1. ABSTRACTIONS AND SERVICES (THE NEW ARCHITECTURE)
# ===================================================================


class MendixEnvironmentService:
    """
    A service that abstracts away the Mendix host environment's global variables.
    Any part of the application needing access to `currentApp`, `dockingWindowService`,
    or `PostMessage` should depend on this service, not the globals themselves.
    This adheres to the Dependency Inversion Principle (DIP).
    """

    def __init__(self, app_context, window_service, post_message_func: Callable):
        self.app = app_context
        self.window_service = window_service
        self.post_message = post_message_func


class EchoService:
    """Handles the business logic for the 'ECHO' command."""

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def echo(self, payload: Dict) -> Dict:
        self._mendix_env.post_message(
            "backend:info", f"Received ECHO command with payload: {payload}")
        return {"echo_response": payload}


class EditorService:
    """Handles the business logic for the 'OPEN_EDITOR' command."""

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def open_editor(self, payload: Dict) -> Dict:
        module_name = payload.get("moduleName")
        entity_name = payload.get("entityName")

        if not module_name or not entity_name:
            raise ValueError(
                "Payload must contain 'moduleName' and 'entityName'.")

        self._mendix_env.post_message(
            "backend:info", f"Attempting to open editor for {module_name}.{entity_name}")

        target_module = next(
            (m for m in self._mendix_env.app.Root.GetModules() if m.Name == module_name), None)
        if not target_module:
            raise FileNotFoundError(f"Module '{module_name}' not found.")

        target_entity = next(
            (e for e in target_module.DomainModel.GetEntities() if e.Name == entity_name), None)
        if not target_entity:
            raise FileNotFoundError(
                f"Entity '{entity_name}' not found in module '{module_name}'.")

        was_opened = self._mendix_env.window_service.TryOpenEditor(
            target_module.DomainModel, target_entity)
        return {"moduleName": module_name, "entityName": entity_name, "opened": was_opened}


class AppController:
    """
    Handles routing of commands from the frontend to specific business logic services.
    It depends on abstract services, not concrete implementations of logic.
    """

    def __init__(self, echo_service: EchoService, editor_service: EditorService, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        self._command_handlers: Dict[str, Callable[[Dict], Any]] = {
            "ECHO": echo_service.echo,
            "OPEN_EDITOR": editor_service.open_editor,
        }

    def dispatch(self, request: Dict) -> Dict:
        """Dispatches a request and ensures the response includes the correlationId."""
        command_type = request.get("type")
        payload = request.get("payload", {})
        correlation_id = request.get("correlationId")

        handler = self._command_handlers.get(command_type)

        if not handler:
            return self._create_error_response(f"No handler found for command type: {command_type}", correlation_id)

        try:
            result = handler(payload)
            return self._create_success_response(result, correlation_id)
        except Exception as e:
            error_message = f"Error executing command '{command_type}': {e}"
            self._mendix_env.post_message(
                "backend:info", f"{error_message}\n{traceback.format_exc()}")
            return self._create_error_response(error_message, correlation_id, {"traceback": traceback.format_exc()})

    def _create_success_response(self, data: Any, correlation_id: str) -> Dict:
        return {"status": "success", "data": data, "correlationId": correlation_id}

    def _create_error_response(self, message: str, correlation_id: str, data: Any = None) -> Dict:
        return {"status": "error", "message": message, "data": data or {}, "correlationId": correlation_id}


# ===================================================================
# 2. IOC CONTAINER CONFIGURATION
# ===================================================================

class Container(containers.DeclarativeContainer):
    """
    The Inversion of Control (IoC) container for the backend application.
    It defines how to create and wire all the services together.
    """
    # Configuration provider for injecting external values like the Mendix globals
    config = providers.Configuration()

    # Provides a singleton instance of the MendixEnvironmentService.
    # It's configured with the actual global variables provided by the host.
    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        window_service=config.window_service,
        post_message_func=config.post_message_func,
    )

    # Provides business logic services, injecting the environment service.
    echo_service = providers.Singleton(EchoService, mendix_env=mendix_env)
    editor_service = providers.Singleton(EditorService, mendix_env=mendix_env)

    # Provides the main AppController, injecting all necessary business logic services.
    app_controller = providers.Singleton(
        AppController,
        echo_service=echo_service,
        editor_service=editor_service,
        mendix_env=mendix_env,
    )


# ===================================================================
# 3. APPLICATION ENTRYPOINT
# ===================================================================

# Create the container instance
container = Container()

# **IMPORTANT**: Inject the actual Mendix global variables into the container's configuration.
# This is the one and only place where globals are accessed directly.
container.config.from_dict({
    "app_context": currentApp,
    "window_service": dockingWindowService,
    "post_message_func": PostMessage,
})


def onMessage(
    e: Any
):
    """
    Entry point for all messages. Now a thin layer that delegates to the controller.
    """
    controller = container.app_controller()
    if e.Message != "frontend:message":
        return

    try:
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)

        if "correlationId" not in request_object:
            PostMessage(
                "backend:info", f"Received message without correlationId: {request_object}")
            return

        response = controller.dispatch(request_object)
        PostMessage("backend:response", json.dumps(response))

    except Exception as ex:
        PostMessage(
            "backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")
        correlation_id = "unknown"
        try:
            request_string = JsonSerializer.Serialize(e.Data)
            request_object = json.loads(request_string)
            correlation_id = request_object.get("correlationId", "unknown")
        except:
            pass

        # Use the controller to create a consistently formatted error response
        error_response = controller._create_error_response(
            f"A fatal error occurred in the Python backend: {ex}",
            correlation_id,
            {"traceback": traceback.format_exc()}
        )
        PostMessage("backend:response", json.dumps(error_response))
