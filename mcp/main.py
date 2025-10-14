# region FRAMEWORK CODE
import json
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod

# Mendix and .NET related imports
import clr
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
import threading
import uuid
from dependency_injector import containers, providers
from System.Text.Json import JsonSerializer
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
from pymx.mcp import tools
from pymx.mcp import tool_registry
from pymx.mcp.mendix_context import set_mendix_services
import importlib
from typing import Optional

import time
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

set_mendix_services(
    currentApp,
    messageBoxService,
    extensionFileService,
    microflowActivitiesService,
    microflowExpressionService,
    microflowService,
    untypedModelAccessService,
    dockingWindowService,
    domainModelService,
    backgroundJobService,
    configurationService,
    extensionFeaturesService,
    httpClientService,
    nameValidationService,
    navigationManagerService,
    pageGenerationService,
    appService,
    dialogService,
    entityService,
    findResultsPaneService,
    localRunConfigurationsService,
    notificationPopupService,
    runtimeService,
    selectorDialogService,
    versionControlService
)

class MCPService:
    """Manages the lifecycle of the FastMCP Uvicorn server."""

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        self._server: Optional[uvicorn.Server] = None
        self._server_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._mcp_instance: Optional[FastMCP] = None
        self.port = 8008

    def is_running(self) -> bool:
        return self._server is not None and not self._server.should_exit

    def _monitor_cancellation(self):
        """
        Runs in a separate thread to monitor the script's cancellation_token.
        This ensures the server is gracefully shut down when the script is re-run.
        """
        # Assumes `cancellation_token` is provided by the execution environment
        while not cancellation_token.IsCancellationRequested:
            time.sleep(1)

        if self.is_running():
            self._mendix_env.post_message(
                "backend:info", "[Monitor] Cancellation detected, shutting down server.")
            self._server.should_exit = True

    def start(self):
        if self.is_running():
            raise RuntimeError("MCP server is already running.")

        self._mendix_env.post_message("backend:info", "Starting MCP server...")

        # 1. Create fresh instances
        # 触发服务重新实例化
        importlib.reload(tool_registry)
        # 关键：导入 'tools' 包以触发 __init__.py 中的动态加载
        importlib.reload(tools)
        # FastMCP("mendix-modular-copilot")
        self._mcp_instance = tool_registry.mcp

        @self._mcp_instance.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers"""
            return a + b

        @self._mcp_instance.tool()
        def get_project_name() -> str:
            """Returns the name of the current Mendix project."""
            return self._mendix_env.app.Root.Name

        # 2. Define lifespan
        async def lifespan(app: Starlette):
            self._mendix_env.post_message(
                "backend:info", "[Lifespan] Starting MCP session manager...")
            async with self._mcp_instance.session_manager.run():
                self._mendix_env.post_message(
                    "backend:info", f"[Lifespan] MCP server ready and listening on port {self.port}.")
                yield
            self._mendix_env.post_message(
                "backend:info", "[Lifespan] MCP server shutting down session manager.")

        # 3. Create Starlette app and Uvicorn config
        app = Starlette(
            routes=[
                Mount("/a", app=self._mcp_instance.streamable_http_app()),
                Route("/b", lambda r: JSONResponse({"status": "ok"})),
            ],
            lifespan=lifespan
        )
        config = uvicorn.Config(app, host="127.0.0.1",
                                port=self.port, log_config=None)
        self._server = uvicorn.Server(config)

        # 4. Run in a separate thread to avoid blocking the main Mendix thread
        self._server_thread = threading.Thread(target=self._server.run)
        self._server_thread.start()

        self._monitor_thread = threading.Thread(
            target=self._monitor_cancellation)
        self._monitor_thread.daemon = True  # Ensure thread doesn't block script exit
        self._monitor_thread.start()

        self._mendix_env.post_message(
            "backend:info", "MCP server start command issued.")

    def stop(self):
        if not self.is_running():
            raise RuntimeError("MCP server is not running.")

        self._mendix_env.post_message("backend:info", "Stopping MCP server...")
        self._server.should_exit = True
        # The thread will terminate on its own once the server exits.
        # We don't join it to avoid blocking.
        self._mendix_env.post_message(
            "backend:info", "MCP server stop command issued.")

    def get_status(self) -> Dict:
        if self.is_running():
            return {"status": "running", "port": self.port}
        else:
            return {"status": "stopped", "port": self.port}

    def get_tools(self) -> Dict:
        if not self.is_running() or self._mcp_instance is None:
            return {"tools": []}

        tool_list = []
        # FIX: The internal attribute for tools in FastMCP is `_tools`, not `tools`.
        for tool in self._mcp_instance._tool_manager.list_tools():
            tool_list.append({
                "name": tool.name,
                "description": tool.description or "No description provided."
            })
        return {"tools": tool_list}


class StartMcpCommandHandler(IAsyncCommandHandler):
    command_type = "MCP_START"

    def __init__(self, mcp_service: MCPService, mendix_env: MendixEnvironmentService):
        self._mcp_service = mcp_service
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        # This runs first on the main thread, returning immediately.
        return {"status": "accepted", "message": "MCP server start command accepted."}

    def execute_async(self, payload: Dict, task_id: str):
        # This runs in a background thread.
        try:
            self._mcp_service.start()
            final_status = self._mcp_service.get_status()
            completion_event = {
                "taskId": task_id,
                "status": "success",
                "data": final_status
            }
        except Exception as e:
            self._mendix_env.post_message(
                "backend:info", f"[Task {task_id}] Error starting MCP: {e}\n{traceback.format_exc()}")
            completion_event = {
                "taskId": task_id,
                "status": "error",
                "message": f"Failed to start MCP Server: {e}"
            }
        self._mendix_env.post_message(
            "backend:response", json.dumps(completion_event))


class StopMcpCommandHandler(IAsyncCommandHandler):
    command_type = "MCP_STOP"

    def __init__(self, mcp_service: MCPService, mendix_env: MendixEnvironmentService):
        self._mcp_service = mcp_service
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        return {"status": "accepted", "message": "MCP server stop command accepted."}

    def execute_async(self, payload: Dict, task_id: str):
        try:
            self._mcp_service.stop()
            # Give it a moment to fully shut down before reporting status
            time.sleep(0.5)
            final_status = self._mcp_service.get_status()
            completion_event = {
                "taskId": task_id,
                "status": "success",
                "data": final_status
            }
        except Exception as e:
            self._mendix_env.post_message(
                "backend:info", f"[Task {task_id}] Error stopping MCP: {e}\n{traceback.format_exc()}")
            completion_event = {
                "taskId": task_id,
                "status": "error",
                "message": f"Failed to stop MCP Server: {e}"
            }
        self._mendix_env.post_message(
            "backend:response", json.dumps(completion_event))


class GetMcpStatusCommandHandler(ICommandHandler):
    """Handles synchronous status requests."""
    command_type = "MCP_GET_STATUS"

    def __init__(self, mcp_service: MCPService):
        self._mcp_service = mcp_service

    def execute(self, payload: Dict) -> Dict:
        return self._mcp_service.get_status()


class ListMcpToolsCommandHandler(ICommandHandler):
    """Handles synchronous tool listing requests."""
    command_type = "MCP_LIST_TOOLS"

    def __init__(self, mcp_service: MCPService):
        self._mcp_service = mcp_service

    def execute(self, payload: Dict) -> Dict:
        return self._mcp_service.get_tools()

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
    mcp_service = providers.Singleton(MCPService, mendix_env=mendix_env)
    # To add a new command, add its handler to this list.
    command_handlers = providers.List(
        providers.Singleton(StartMcpCommandHandler,
                            mcp_service=mcp_service, mendix_env=mendix_env),
        providers.Singleton(StopMcpCommandHandler,
                            mcp_service=mcp_service, mendix_env=mendix_env),
        providers.Singleton(GetMcpStatusCommandHandler,
                            mcp_service=mcp_service),
        providers.Singleton(ListMcpToolsCommandHandler,
                            mcp_service=mcp_service),
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