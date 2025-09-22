from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import IDomainModel, IEntity
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule
import clr
from System.Text.Json import JsonSerializer
import json
import traceback
from typing import Any, Dict, Callable

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
# REFACTORED BACKEND ARCHITECTURE (RPC-Aware)
# ===================================================================


class AppController:
    """
    Handles routing of commands from the frontend to specific business logic handlers.
    """

    def __init__(self, app_context):
        self.app = app_context
        self._command_handlers: Dict[str, Callable[[Dict], Any]] = {
            "ECHO": self.handle_echo,
            "OPEN_EDITOR": self.handle_open_editor,
        }

    def dispatch(self, request: Dict) -> Dict:
        """
        Dispatches a request and ensures the response includes the correlationId.
        """
        command_type = request.get("type")
        payload = request.get("payload", {})
        # Extract the correlationId
        correlation_id = request.get("correlationId")

        handler = self._command_handlers.get(command_type)

        if not handler:
            return self._create_error_response(f"No handler found for command type: {command_type}", correlation_id)

        try:
            result = handler(payload)
            return self._create_success_response(result, correlation_id)
        except Exception as e:
            error_message = f"Error executing command '{command_type}': {e}"
            PostMessage("backend:info",
                        f"{error_message}\n{traceback.format_exc()}")
            return self._create_error_response(error_message, correlation_id, {"traceback": traceback.format_exc()})

    # --- Command Handlers (Logic is unchanged) ---

    def handle_echo(self, payload: Dict) -> Dict:
        PostMessage("backend:info",
                    f"Received ECHO command with payload: {payload}")
        return {"echo_response": payload}

    def handle_open_editor(self, payload: Dict) -> Dict:
        module_name = payload.get("moduleName")
        entity_name = payload.get("entityName")

        if not module_name or not entity_name:
            raise ValueError(
                "Payload must contain 'moduleName' and 'entityName'.")
        PostMessage(
            "backend:info", f"Attempting to open editor for {module_name}.{entity_name}")

        target_module = next(
            (m for m in self.app.Root.GetModules() if m.Name == module_name), None)
        if not target_module:
            raise FileNotFoundError(f"Module '{module_name}' not found.")
        target_entity = next(
            (e for e in target_module.DomainModel.GetEntities() if e.Name == entity_name), None)
        if not target_entity:
            raise FileNotFoundError(
                f"Entity '{entity_name}' not found in module '{module_name}'.")

        was_opened = dockingWindowService.TryOpenEditor(
            target_module.DomainModel, target_entity)
        return {"moduleName": module_name, "entityName": entity_name, "opened": was_opened}

    # --- Response Formatting (Now includes correlationId) ---

    def _create_success_response(self, data: Any, correlation_id: str) -> Dict:
        return {"status": "success", "data": data, "correlationId": correlation_id}

    def _create_error_response(self, message: str, correlation_id: str, data: Any = None) -> Dict:
        return {"status": "error", "message": message, "data": data or {}, "correlationId": correlation_id}


# Global instance of our controller
app_controller = AppController(currentApp)


def onMessage(e: Any):
    """
    Entry point for all messages. Now handles the RPC request/response flow.
    """
    if e.Message != "frontend:message":
        return

    try:
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)

        # The request MUST contain a correlationId for RPC to work
        if "correlationId" not in request_object:
            PostMessage(
                "backend:info", f"Received message without correlationId: {request_object}")
            return

        response = app_controller.dispatch(request_object)
        PostMessage("backend:response", json.dumps(response))

    except Exception as ex:
        PostMessage(
            "backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")
        # Try to construct an error response if we can parse the correlationId
        correlation_id = "unknown"
        try:
            request_string = JsonSerializer.Serialize(e.Data)
            request_object = json.loads(request_string)
            correlation_id = request_object.get("correlationId", "unknown")
        except:
            pass  # Ignore if deserialization fails

        error_response = app_controller._create_error_response(
            f"A fatal error occurred in the Python backend: {ex}",
            correlation_id,
            {"traceback": traceback.format_exc()}
        )
        PostMessage("backend:response", json.dumps(error_response))
