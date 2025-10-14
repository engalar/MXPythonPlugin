import subprocess
import sys
import os
import time
from dependency_injector import containers, providers
from System.Text.Json import JsonSerializer
import re

# region Boilerplate Imports
import json
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod

# Mendix and .NET related imports
import clr
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# Dependency Injection framework

# --- START: New Imports for Git Log Functionality ---


def execute_silent(command, cwd=None, timeout=None):
    """
    执行命令，捕获 stdout 和 stderr，并确保在 Windows 上没有控制台窗口弹出。

    Args:
        command (list): 要执行的命令列表。
        timeout (int): 命令超时时间（秒）。

    Returns:
        subprocess.CompletedProcess: 包含 stdout, stderr, 和 returncode。
    """

    # 1. 设置 Windows 静默标志
    creation_flags = 0
    if sys.platform == "win32":
        # 0x08000000 是 CREATE_NO_WINDOW 的值
        creation_flags = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(
            command,
            capture_output=True,  # 关键：捕获 stdout 和 stderr
            text=True,            # 将输出解码为文本（使用默认系统编码）
            check=True,           # 如果返回非零状态码，则抛出 CalledProcessError
            cwd=cwd,
            creationflags=creation_flags,
            timeout=timeout
        )
        return result

    except subprocess.CalledProcessError as e:
        print(f"命令执行失败，返回码: {e.returncode}")
        print("Standard Output (partial):\n", e.stdout)
        print("Standard Error:\n", e.stderr)
        # 可以选择重新抛出异常，或返回一个包含错误的CompletedProcess对象
        raise
    except FileNotFoundError:
        print(f"找不到可执行文件: {command[0]}")
        raise
    except subprocess.TimeoutExpired:
        print("命令执行超时")
        raise
    except Exception as e:
        print(f"发生未知错误: {e}")
        raise
# --- END: New Imports for Git Log Functionality ---
# endregion

# ===================================================================
# 1. CORE SERVICES AND ABSTRACTIONS
# ===================================================================


class MendixEnvironmentService:
    """
    A service that abstracts the Mendix host environment global variables.
    It provides a clean way to access Mendix APIs.
    """

    def __init__(self, app_context, window_service, post_message_func: Callable):
        self.app = app_context
        self.window_service = window_service
        self.post_message = post_message_func

    def get_project_path(self) -> str:
        """
        Returns the file path of the current Mendix project root directory.
        This is needed to run git commands.
        """
        return self.app.Root.DirectoryPath


class ICommandHandler(ABC):
    """
    Defines the contract for all command handlers. Each handler is responsible
    for a single command type from the frontend.
    """
    @property
    @abstractmethod
    def command_type(self) -> str:
        """The command type string this handler responds to (e.g., "GET_GIT_LOG")."""
        pass

    @abstractmethod
    def execute(self, payload: Dict) -> Any:
        """Executes the business logic for the command and returns the result."""
        pass

# ===================================================================
# 2. COMMAND HANDLER IMPLEMENTATIONS
# ===================================================================

# --- START: New Command Handler for Simulating Long Tasks ---

class SimulateTaskCommandHandler(ICommandHandler):
    """Handles the 'SIMULATE_TASK' command to test UI blocking."""
    command_type = "SIMULATE_TASK"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        seconds = payload.get("seconds", 5)
        try:
            # Add a reasonable limit to prevent very long blocks
            seconds_int = int(seconds)
            if not (0 < seconds_int <= 60):
                 raise ValueError("Seconds must be an integer between 1 and 60.")
        except (ValueError, TypeError):
            raise ValueError("Payload 'seconds' must be a valid integer.")

        self._mendix_env.post_message(
            "backend:info", f"Starting simulated task for {seconds_int} seconds.")

        time.sleep(seconds_int)

        self._mendix_env.post_message(
            "backend:info", "Simulated task finished.")

        return {"status": "success", "message": f"Simulated task completed after {seconds_int} seconds."}

# --- END: New Command Handler for Simulating Long Tasks ---

# ===================================================================
# 3. APPLICATION CONTROLLER / DISPATCHER
# ===================================================================


class AppController:
    """
    Routes incoming frontend commands to the appropriate ICommandHandler.
    This class is the central point of control for the backend logic.
    """

    def __init__(self, handlers: Iterable[ICommandHandler], mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        self._command_handlers = {h.command_type: h.execute for h in handlers}
        self._mendix_env.post_message(
            "backend:info", f"Controller initialized with handlers for: {list(self._command_handlers.keys())}")

    def dispatch(self, request: Dict) -> Dict:
        command_type = request.get("type")
        payload = request.get("payload", {})
        correlation_id = request.get("correlationId")
        try:
            handler_execute_func = self._command_handlers.get(command_type)
            if not handler_execute_func:
                raise ValueError(
                    f"No handler found for command type: {command_type}")
            result = handler_execute_func(payload)
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

# ===================================================================
# 4. IOC CONTAINER CONFIGURATION
# ===================================================================


class Container(containers.DeclarativeContainer):
    """
    The application's Inversion of Control (IoC) container.
    It is responsible for creating and wiring all the application components.
    """
    config = providers.Configuration()

    # Singleton service for Mendix environment access
    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        window_service=config.window_service,
        post_message_func=config.post_message_func,
    )

    # Use providers.List to aggregate all command handlers.
    # This makes the system pluggable; just add a new handler here.
    command_handlers = providers.List(
        providers.Singleton(SimulateTaskCommandHandler,
                            mendix_env=mendix_env),
    )

    # The main controller, injected with the list of all available handlers
    app_controller = providers.Singleton(
        AppController,
        handlers=command_handlers,
        mendix_env=mendix_env,
    )

# ===================================================================
# 5. APPLICATION ENTRYPOINT AND WIRING
# ===================================================================

# These variables are provided by the Mendix Studio Pro script environment
# They are used here to initialize the IoC container.
# currentApp, dockingWindowService, PostMessage


def onMessage(e: Any):
    """This function is the entry point called by Mendix Studio Pro for messages from the UI."""
    if e.Message != "frontend:message":
        return

    controller = container.app_controller()
    request_object = None
    try:
        # Deserialize the incoming request from the frontend
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)

        # Dispatch the request and get a response
        response = controller.dispatch(request_object)

        # Send the response back to the frontend
        PostMessage("backend:response", json.dumps(response))

    except Exception as ex:
        # Gracefully handle any fatal errors during dispatch
        PostMessage(
            "backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")
        correlation_id = request_object.get(
            "correlationId", "unknown") if request_object else "unknown"
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
    # This wires the providers to the actual instances for dependency injection
    # container.wire(modules=[__name__]) # this script is exe by eval, so we can not do like this
    return container


# --- Application Start ---
PostMessage("backend:clear", '')
container = initialize_app()
PostMessage("backend:info", "Backend Python script initialized successfully.")
