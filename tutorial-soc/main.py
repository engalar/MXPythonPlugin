# region 样板代码
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import IDomainModel, IEntity
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule
import clr
from System.Text.Json import JsonSerializer
import json
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod  # 引入ABC用于定义接口
from dependency_injector import containers, providers
from dependency_injector.wiring import inject, Provide

# pythonnet库嵌入C#代码
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")


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

    # 1. 将每个命令处理器注册为独立的Provider

    # 2. 使用 providers.List 将所有命令处理器聚合到一个集合中
    command_handlers = providers.List(
        providers.Singleton(EchoCommandHandler, mendix_env=mendix_env),
        providers.Singleton(EditorCommandHandler, mendix_env=mendix_env),
        # **未来若要添加新命令，只需在此处添加新的handler provider即可**
    )

    # 3. 更新AppController的Provider，将聚合后的列表注入到其'handlers'参数
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
