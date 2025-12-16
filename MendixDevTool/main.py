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
# [REPLACED] Imports & Bridge Service
import time
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse, Response
from starlette.requests import Request
from typing import Optional

# ==========================================
# [HELPER] Mendix Document/Widget Finder
# ==========================================
class MendixFinder:
    @staticmethod
    def execute_open_logic(payload: Dict, app_root) -> bool:
        target_str = payload.get('target', '') 
        if not target_str: return False

        parts = target_str.split('.')
        if len(parts) < 2: return False

        module_name = parts[0]
        unit_name = parts[1]
        widget_name = parts[2] if len(parts) > 2 else None

        # 1. Find Module
        module = next((m for m in app_root.GetModules() if m.Name == module_name), None)
        if not module: return False

        # 2. Find Document (Recursive)
        def find_doc(folder, name):
            doc = next((d for d in folder.GetDocuments() if d.Name == name), None)
            if doc: return doc
            for sub in folder.GetFolders():
                res = find_doc(sub, name)
                if res: return res
            return None
        
        document = find_doc(module, unit_name)
        if not document: return document

        # 3. Find Widget (Recursive)
        target_element = None

        # 由于当前API不支持检索页面内部的IElement对象，跳过

        # if widget_name:
        #     def find_wid(node, name):
        #         if getattr(node, "Name", None) == name: return node
        #         if hasattr(node, "GetProperties"):
        #             for p in node.GetProperties():
        #                 if p.Value:
        #                     if p.IsList:
        #                         for item in p.Value:
        #                             res = find_wid(item, name)
        #                             if res: return res
        #                     elif hasattr(p.Value, "GetProperties"):
        #                         res = find_wid(p.Value, name)
        #                         if res: return res
        #         return None
            
        #     found = find_wid(document, widget_name)
        #     if found: target_element = found
        
        # 4. Open Editor
        if 'dockingWindowService' in globals():
            dockingWindowService.TryOpenEditor(document, target_element)
            return True
        return False

class BridgeServerService:
    """Manages the Uvicorn server for Browser-StudioPro communication."""

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        self._server: Optional[uvicorn.Server] = None
        self._server_thread: Optional[threading.Thread] = None
        self.port = 5000 # Matches UserScript default

    def is_running(self) -> bool:
        return self._server is not None and not self._server.should_exit

    def start(self):
        if self.is_running(): return

        async def handle_rpc(request: Request):
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type"
            }
            if request.method == "OPTIONS":
                return Response(status_code=204, headers=headers)
            
            try:
                payload = await request.json()
                
                # [新增] 退出指令处理
                if payload.get("action") == "shutdown":
                    if self._server:
                        self._server.should_exit = True
                    return JSONResponse({"status": "shutting_down"}, status_code=200, headers=headers)

                success = MendixFinder.execute_open_logic(payload, self._mendix_env.app.Root)
                return JSONResponse({"status": "success" if success else "failed"}, status_code=200, headers=headers)
            except Exception as e:
                return JSONResponse({"status": "error", "message": str(e)}, status_code=500, headers=headers)

        app = Starlette(routes=[
            Route("/open_in_studio_pro", handle_rpc, methods=["POST", "OPTIONS"])
        ])
        
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_config=None)
        self._server = uvicorn.Server(config)
        self._server_thread = threading.Thread(target=self._server.run)
        self._server_thread.start()
        
        self._mendix_env.post_message("backend:info", f"Bridge Server started on port {self.port}")

    def stop(self):
        if not self.is_running(): return
        self._server.should_exit = True
        self._mendix_env.post_message("backend:info", "Bridge Server stopped manually.")

    def get_status(self) -> Dict:
        return {"status": "running" if self.is_running() else "stopped", "port": self.port}
    
# [REPLACED] Command Handlers
class StartServerCommandHandler(IAsyncCommandHandler):
    command_type = "SERVER_START" # Modified type
    def __init__(self, service: BridgeServerService, mendix_env: MendixEnvironmentService):
        self._service = service
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        return {"status": "accepted"}

    def execute_async(self, payload: Dict, task_id: str):
        try:
            self._service.start()
            self._mendix_env.post_message("backend:response", json.dumps({
                "taskId": task_id, "status": "success", "data": self._service.get_status()
            }))
        except Exception as e:
            self._mendix_env.post_message("backend:info", str(e))

class StopServerCommandHandler(IAsyncCommandHandler):
    command_type = "SERVER_STOP" # Modified type
    def __init__(self, service: BridgeServerService, mendix_env: MendixEnvironmentService):
        self._service = service
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        return {"status": "accepted"}

    def execute_async(self, payload: Dict, task_id: str):
        self._service.stop()
        time.sleep(0.5)
        self._mendix_env.post_message("backend:response", json.dumps({
            "taskId": task_id, "status": "success", "data": self._service.get_status()
        }))

class GetStatusCommandHandler(ICommandHandler):
    command_type = "SERVER_GET_STATUS"
    def __init__(self, service: BridgeServerService):
        self._service = service
    def execute(self, payload: Dict) -> Dict:
        return self._service.get_status()
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

    # [REPLACED] IoC Container
    # --- Business Logic Registrations ---
    bridge_service = providers.Singleton(BridgeServerService, mendix_env=mendix_env)
    
    command_handlers = providers.List(
        providers.Singleton(StartServerCommandHandler, service=bridge_service, mendix_env=mendix_env),
        providers.Singleton(StopServerCommandHandler, service=bridge_service, mendix_env=mendix_env),
        providers.Singleton(GetStatusCommandHandler, service=bridge_service),
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
import urllib.request
import urllib.error

def ensure_previous_instance_killed(port=5000):
    """
    尝试连接本地端口并发送关闭指令。
    如果端口通畅（旧服务在运行），旧服务收到指令后会退出。
    如果连接被拒绝（无服务运行），则跳过。
    """
    url = f"http://127.0.0.1:{port}/open_in_studio_pro"
    shutdown_payload = json.dumps({"action": "shutdown"}).encode('utf-8')
    
    try:
        # 尝试发送关闭指令
        req = urllib.request.Request(url, data=shutdown_payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=1) as response:
            PostMessage("backend:info", f"Signal sent to existing instance on port {port}. Waiting for shutdown...")
        
        # 给予旧线程一点时间释放端口
        time.sleep(1.5)
    except urllib.error.URLError:
        # 连接失败说明没有服务在运行，直接继续
        pass
    except Exception as e:
        PostMessage("backend:info", f"Warning during cleanup check: {str(e)}")

# 1. 先清理环境
PostMessage("backend:clear", '')

# 2. 尝试关闭之前的实例（如果有）
ensure_previous_instance_killed(5000)

# 3. 初始化并启动新应用
container = initialize_app()
PostMessage("backend:info", "Backend Python script initialized successfully.")

# endregion