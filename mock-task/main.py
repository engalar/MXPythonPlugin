import subprocess
import sys
import threading
import uuid
import time
from dependency_injector import containers, providers
from System.Text.Json import JsonSerializer
import re

# region FRAMEWORK CODE
import json
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod

# Mendix and .NET related imports
import clr
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
# ShowDevTools()

# ===================================================================
# ===================     FRAMEWORK CODE     ========================
# ===================================================================
# This section contains the reusable, application-agnostic core.
# You should not need to modify this section to add new features.
# -------------------------------------------------------------------

# 1. FRAMEWORK: CORE ABSTRACTIONS AND INTERFACES

class MendixEnvironmentService:
    """Abstracts the Mendix host environment global variables."""
    def __init__(self, app_context, window_service, post_message_func: Callable):
        self.app = app_context
        self.window_service = window_service
        self.post_message = post_message_func

    def get_project_path(self) -> str:
        return self.app.Root.DirectoryPath

class ICommandHandler(ABC):
    """Contract for all command handlers."""
    @property
    @abstractmethod
    def command_type(self) -> str:
        """The command type string this handler responds to."""
        pass

    @abstractmethod
    def execute(self, payload: Dict) -> Any:
        """Executes the business logic for the command."""
        pass

class IAsyncCommandHandler(ICommandHandler):
    """Extends ICommandHandler for tasks that should not block the main thread."""
    @abstractmethod
    def execute_async(self, payload: Dict, task_id: str):
        """The logic to be executed in a background thread."""
        pass

# 2. FRAMEWORK: CENTRAL DISPATCHER

class AppController:
    """Routes incoming frontend commands to the appropriate ICommandHandler."""
    def __init__(self, handlers: Iterable[ICommandHandler], mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        self._command_handlers = {h.command_type: h for h in handlers}
        self._mendix_env.post_message(
            "backend:info", f"Controller initialized with handlers for: {list(self._command_handlers.keys())}")

    def dispatch(self, request: Dict) -> Dict:
        command_type = request.get("type")
        payload = request.get("payload", {})
        correlation_id = request.get("correlationId")
        try:
            handler = self._command_handlers.get(command_type)
            if not handler:
                raise ValueError(f"No handler found for command type: {command_type}")

            # Generic logic to handle sync vs. async handlers
            if isinstance(handler, IAsyncCommandHandler):
                task_id = f"task-{uuid.uuid4()}"
                thread = threading.Thread(
                    target=handler.execute_async,
                    args=(payload, task_id)
                )
                thread.daemon = True
                thread.start()
                # The immediate response includes the taskId for frontend tracking
                result = handler.execute(payload)
                result['taskId'] = task_id
                return self._create_success_response(result, correlation_id)
            else:
                # Original synchronous execution path
                result = handler.execute(payload)
                return self._create_success_response(result, correlation_id)

        except Exception as e:
            error_message = f"Error executing command '{command_type}': {e}"
            self._mendix_env.post_message(
                "backend:info", f"{error_message}\n{traceback.format_exc()}")
            return self._create_error_response(error_message, correlation_id)

    def _create_success_response(self, data: Any, correlation_id: str) -> Dict:
        return {"status": "success", "data": data, "correlationId": correlation_id}

    def _create_error_response(self, message: str, correlation_id: str) -> Dict:
        return {"status": "error", "message": message, "correlationId": correlation_id}


# endregion

# region BUSINESS LOGIC CODE
# ===================================================================
# ===============     BUSINESS LOGIC CODE     =======================
# ===================================================================
# This section contains your feature-specific command handlers.
# To add a new feature, create a new class implementing ICommandHandler
# or IAsyncCommandHandler, and register it in the Container below.
# -------------------------------------------------------------------

class SimulateTaskCommandHandler(IAsyncCommandHandler):
    """
    Handles the 'SIMULATE_TASK' command asynchronously.
    This is an example of business logic implementing a framework interface.
    """
    command_type = "SIMULATE_TASK"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Any:
        """Main thread: returns immediately, confirming the task has started."""
        return {"status": "accepted", "message": "Async task accepted and running."}

    def execute_async(self, payload: Dict, task_id: str):
        """Background thread: performs the long-running work."""
        seconds = 5
        try:
            seconds = payload.get("seconds", 5)
            seconds_int = int(seconds)
            if not (0 < seconds_int <= 60):
                raise ValueError("Seconds must be an integer between 1 and 60.")

            time.sleep(seconds_int)
            result_message = f"Simulated task completed after {seconds_int} seconds."

            completion_event = {
                "taskId": task_id,
                "status": "success",
                "data": {"message": result_message}
            }
            self._mendix_env.post_message("backend:response", json.dumps(completion_event))

        except Exception as e:
            error_message = f"Error in async task {task_id}: {e}"
            self._mendix_env.post_message("backend:info", f"{error_message}\n{traceback.format_exc()}")
            error_event = {
                "taskId": task_id,
                "status": "error",
                "message": error_message
            }
            self._mendix_env.post_message("backend:response", json.dumps(error_event))

# endregion 

# region IOC & APP INITIALIZATION
# ===================================================================
# ==============     IOC & APP INITIALIZATION     ===================
# ===================================================================

class Container(containers.DeclarativeContainer):
    """The application's Inversion of Control (IoC) container."""
    config = providers.Configuration()

    # --- Framework Registrations ---
    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        window_service=config.window_service,
        post_message_func=config.post_message_func,
    )

    # --- Business Logic Registrations ---
    # To add a new command, add its handler to this list.
    command_handlers = providers.List(
        providers.Singleton(SimulateTaskCommandHandler, mendix_env=mendix_env),
        # e.g., providers.Singleton(AnotherCommandHandler, mendix_env=mendix_env),
    )

    # --- Framework Controller (depends on handlers) ---
    app_controller = providers.Singleton(
        AppController,
        handlers=command_handlers,
        mendix_env=mendix_env,
    )

# --- Application Entrypoint and Wiring ---
def onMessage(e: Any):
    """Entry point called by Mendix Studio Pro for messages from the UI."""
    if e.Message != "frontend:message":
        return
    controller = container.app_controller()
    request_object = None
    try:
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)
        response = controller.dispatch(request_object)
        PostMessage("backend:response", json.dumps(response))
    except Exception as ex:
        PostMessage("backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")
        correlation_id = request_object.get("correlationId", "unknown") if request_object else "unknown"
        fatal_error_response = {
            "status": "error",
            "message": f"A fatal backend error occurred: {ex}",
            "correlationId": correlation_id
        }
        PostMessage("backend:response", json.dumps(fatal_error_response))

def initialize_app():
    """Initializes the IoC container with the Mendix environment services."""
    container = Container()
    container.config.from_dict({
        "app_context": currentApp,
        "window_service": dockingWindowService,
        "post_message_func": PostMessage
    })
    return container

# --- Application Start ---
PostMessage("backend:clear", '')
container = initialize_app()
PostMessage("backend:info", "Backend Python script initialized successfully.")

# endregion