# region 样板代码
import time
import anyio
from pymx.mcp import tools
from pymx.mcp import tool_registry
from pymx.mcp.mendix_context import set_mendix_services
import importlib
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import IDomainModel, IEntity
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule
import clr
from System.Text.Json import JsonSerializer
import json
import traceback
from typing import Any, Dict, Callable, Iterable, Optional
from abc import ABC, abstractmethod  # 引入ABC用于定义接口
from dependency_injector import containers, providers
from dependency_injector.wiring import inject, Provide

# --- New imports for MCP server ---
import threading
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
# --- End new imports ---


# pythonnet库嵌入C#代码
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")


# mcp
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


# 运行时环境提供的工具
PostMessage("backend:clear", '')  # 清理IDE控制台日志
# ShowDevTools()  # 打开前端开发者工具


def serialize_json_object(json_object: Any) -> str:
    import System.Text.Json
    return System.Text.Json.JsonSerializer.Serialize(json_object)


def deserialize_json_string(json_string: str) -> Any:
    return json.loads(json_string)


class TransactionManager:
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
# endregion

# ===================================================================
# 1. ABSTRACTIONS AND SERVICES (THE NEW ARCHITECTURE)
# ===================================================================


class MendixEnvironmentService:
    """
    一个抽象了Mendix宿主环境全局变量的服务。
    (此部分保持不变)
    """

    def __init__(self, app_context, window_service, post_message_func: Callable):
        self.app = app_context
        self.window_service = window_service
        self.post_message = post_message_func

# ----------------- Step 1: Define a Command Handler Interface -----------------


class ICommandHandler(ABC):
    """
    定义所有命令处理器的通用接口。
    每个处理器都必须声明它能处理的命令类型，并提供一个执行方法。
    """
    @property
    @abstractmethod
    def command_type(self) -> str:
        """返回此处理器响应的命令类型字符串，例如 "ECHO" 或 "OPEN_EDITOR"."""
        ...

    @abstractmethod
    def execute(self, payload: Dict) -> Dict:
        """执行与命令相关的业务逻辑。"""
        ...

# ----------------- Step 2: Refactor Services to Implement the Interface -----------------


class EchoCommandHandler(ICommandHandler):
    """处理'ECHO'命令的业务逻辑。"""
    command_type = "ECHO"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        self._mendix_env.post_message(
            "backend:info", f"Received {self.command_type} command with payload: {payload}")
        return {"echo_response": payload}


class EditorCommandHandler(ICommandHandler):
    """处理'OPEN_EDITOR'命令的业务逻辑。"""
    command_type = "OPEN_EDITOR"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
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


# 实现开启或者关闭mcp的接口，另外还需要有状态检测接口，以及当前mcp工具列表
# --- START: New MCP Service and Command Handler ---

class MCPService:
    """Manages the lifecycle of the FastMCP Uvicorn server."""

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        self._server: Optional[uvicorn.Server] = None
        self._server_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._mcp_instance: Optional[FastMCP] = None
        self.port = 8009

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
            self._mendix_env.post_message("backend:info", "[Monitor] Cancellation detected, shutting down server.")
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
        self._mcp_instance = tool_registry.mcp # FastMCP("mendix-modular-copilot")

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
            self._mendix_env.post_message("backend:info", "[Lifespan] Starting MCP session manager...")
            async with self._mcp_instance.session_manager.run():
                self._mendix_env.post_message("backend:info", f"[Lifespan] MCP server ready and listening on port {self.port}.")
                yield
            self._mendix_env.post_message("backend:info", "[Lifespan] MCP server shutting down session manager.")

        # 3. Create Starlette app and Uvicorn config
        app = Starlette(
            routes=[
                Mount("/a", app=self._mcp_instance.streamable_http_app()),
                Route("/b", lambda r: JSONResponse({"status": "ok"})),
            ],
            lifespan=lifespan
        )
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_config=None)
        self._server = uvicorn.Server(config)

        # 4. Run in a separate thread to avoid blocking the main Mendix thread
        self._server_thread = threading.Thread(target=self._server.run)
        self._server_thread.start()

        self._monitor_thread = threading.Thread(target=self._monitor_cancellation)
        self._monitor_thread.daemon = True  # Ensure thread doesn't block script exit
        self._monitor_thread.start()

        self._mendix_env.post_message("backend:info", "MCP server start command issued.")

    def stop(self):
        if not self.is_running():
            raise RuntimeError("MCP server is not running.")
        
        self._mendix_env.post_message("backend:info", "Stopping MCP server...")
        self._server.should_exit = True
        # The thread will terminate on its own once the server exits.
        # We don't join it to avoid blocking.
        self._mendix_env.post_message("backend:info", "MCP server stop command issued.")

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


class MCPCommandHandler(ICommandHandler):
    """Handles all MCP-related commands by delegating to MCPService."""
    command_type = "MCP_CONTROL"

    def __init__(self, mcp_service: MCPService):
        self._mcp_service = mcp_service

    def execute(self, payload: Dict) -> Dict:
        action = payload.get("action")
        if action == "start":
            self._mcp_service.start()
            return self._mcp_service.get_status()
        elif action == "stop":
            self._mcp_service.stop()
            return self._mcp_service.get_status()
        elif action == "get_status":
            return self._mcp_service.get_status()
        elif action == "list_tools":
            return self._mcp_service.get_tools()
        else:
            raise ValueError(f"Invalid action '{action}' for MCP_CONTROL.")

# --- END: New MCP Service and Command Handler ---


# ----------------- Step 3: Modify the AppController -----------------
class AppController:
    """
    将前端命令路由到特定的业务逻辑服务。
    现在它依赖于一个可迭代的ICommandHandler集合，而不是具体的服务。
    """

    def __init__(self, handlers: Iterable[ICommandHandler], mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        # 在构造时动态构建命令处理器字典
        self._command_handlers = {h.command_type: h.execute for h in handlers}
        self._mendix_env.post_message(
            "backend:info", f"Controller initialized with handlers for: {list(self._command_handlers.keys())}")

    def dispatch(self, request: Dict) -> Dict:
        """
        分发请求的逻辑保持不变，但现在更加灵活。
        """
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
    应用的控制反转(IoC)容器。
    """
    config = providers.Configuration()

    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        window_service=config.window_service,
        post_message_func=config.post_message_func,
    )

    # ----------------- Step 4: Update IoC Container Configuration -----------------
    
    # Register the new MCPService
    mcp_service = providers.Singleton(MCPService, mendix_env=mendix_env)

    # Use providers.List to aggregate all command handlers
    command_handlers = providers.List(
        providers.Singleton(EchoCommandHandler, mendix_env=mendix_env),
        providers.Singleton(EditorCommandHandler, mendix_env=mendix_env),
        # Add the new MCP command handler
        providers.Singleton(MCPCommandHandler, mcp_service=mcp_service),
    )

    # Update AppController's provider to inject the aggregated list
    app_controller = providers.Singleton(
        AppController,
        handlers=command_handlers,
        mendix_env=mendix_env,
    )


# ===================================================================
# 3. APPLICATION ENTRYPOINT AND WIRING
# ===================================================================

def onMessage(e: Any):
    if e.Message != "frontend:message":
        return
    controller = container.app_controller()
    request_object = None
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
        if request_object and "correlationId" in request_object:
            correlation_id = request_object["correlationId"]
        fatal_error_response = {"status": "error", "message": f"A fatal error occurred: {ex}", "data": {
            "traceback": traceback.format_exc()}, "correlationId": correlation_id}
        PostMessage("backend:response", json.dumps(fatal_error_response))


def initialize_app():
    container = Container()
    container.config.from_dict(
        {"app_context": currentApp, "window_service": dockingWindowService, "post_message_func": PostMessage})
    return container


# ===================================================================
# 4. APPLICATION START
# ===================================================================
container = initialize_app()