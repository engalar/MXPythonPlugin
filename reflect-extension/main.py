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

# ===================================================================
# ===================    CORE ABSTRACTIONS     ======================
# ===================================================================
from abc import ABC, abstractmethod
from typing import Any, Dict, Callable, Iterable, Optional, Protocol
import uuid
import threading
import json
import traceback

class ProgressUpdate:
    """Structured progress data."""
    def __init__(self, percent: float, message: str, stage: Optional[str] = None, metadata: Optional[Dict] = None):
        self.percent = percent
        self.message = message
        self.stage = stage
        self.metadata = metadata

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}

class IMessageHub(Protocol):
    """Abstraction for sending messages to the frontend (DIP)."""
    def send(self, message: Dict): ...
    def broadcast(self, channel: str, data: Any): ...
    def push_to_session(self, session_id: str, data: Any): ...

class IJobContext(Protocol):
    """Context object provided to a running job handler."""
    job_id: str
    def report_progress(self, progress: ProgressUpdate): ...

# --- Handler Interfaces (OCP) ---
class IHandler(ABC):
    @property
    @abstractmethod
    def command_type(self) -> str: ...

class IRpcHandler(IHandler):
    @abstractmethod
    def execute(self, payload: Dict) -> Any: ...

class IJobHandler(IHandler):
    @abstractmethod
    def run(self, payload: Dict, context: IJobContext): ...

class ISessionHandler(IHandler):
    @abstractmethod
    def on_connect(self, session_id: str, payload: Optional[Dict]): ...
    @abstractmethod
    def on_disconnect(self, session_id: str): ...

# 2. FRAMEWORK: CENTRAL DISPATCHER
# ===================================================================
# ===================     FRAMEWORK CORE     ========================
# ===================================================================
class MendixMessageHub:
    """Low-level implementation of IMessageHub for Mendix."""
    def __init__(self, post_message_func: Callable):
        self._post_message = post_message_func

    def send(self, message: Dict):
        self._post_message("backend:response", json.dumps(message))

    def broadcast(self, channel: str, data: Any):
        self.send({"type": "EVENT_BROADCAST", "channel": channel, "data": data})

    def push_to_session(self, session_id: str, data: Any):
        self.send({"type": "EVENT_SESSION", "sessionId": session_id, "data": data})

class AppController:
    """Routes incoming messages to registered handlers. Obeys OCP."""
    def __init__(self, rpc_handlers: Iterable[IRpcHandler], job_handlers: Iterable[IJobHandler],
                 session_handlers: Iterable[ISessionHandler], message_hub: IMessageHub):
        self._rpc = {h.command_type: h for h in rpc_handlers}
        self._jobs = {h.command_type: h for h in job_handlers}
        self._sessions = {h.command_type: h for h in session_handlers}
        self._hub = message_hub
        print(f"Controller initialized. RPCs: {list(self._rpc.keys())}, Jobs: {list(self._jobs.keys())}, Sessions: {list(self._sessions.keys())}")

    def dispatch(self, request: Dict):
        msg_type = request.get("type")
        try:
            if msg_type == "RPC": self._handle_rpc(request)
            elif msg_type == "JOB_START": self._handle_job_start(request)
            elif msg_type == "SESSION_CONNECT": self._handle_session_connect(request)
            elif msg_type == "SESSION_DISCONNECT": self._handle_session_disconnect(request)
            else: raise ValueError(f"Unknown message type: {msg_type}")
        except Exception as e:
            req_id = request.get("reqId")
            if req_id:
                # MODIFIED: Capture and send the full traceback string
                tb_string = traceback.format_exc()
                self._hub.send({"type": "RPC_ERROR", "reqId": req_id, "message": str(e), "traceback": tb_string})
            traceback.print_exc()

    def _handle_rpc(self, request):
        handler = self._rpc.get(request["method"])
        if not handler: raise ValueError(f"No RPC handler for '{request['method']}'")
        result = handler.execute(request.get("params"))
        self._hub.send({"type": "RPC_SUCCESS", "reqId": request["reqId"], "data": result})

    def _handle_job_start(self, request):
        handler = self._jobs.get(request["method"])
        if not handler: raise ValueError(f"No Job handler for '{request['method']}'")
        
        job_id = f"job-{uuid.uuid4()}"
        
        class JobContext(IJobContext):
            def __init__(self, job_id: str, hub: IMessageHub):
                self.job_id = job_id
                self._hub = hub
            def report_progress(self, progress: ProgressUpdate):
                self._hub.send({"type": "JOB_PROGRESS", "jobId": self.job_id, "progress": progress.to_dict()})

        context = JobContext(job_id, self._hub)
        
        def job_runner():
            try:
                # To test job error, uncomment the next line
                # raise ValueError("This is a deliberate job error")
                result = handler.run(request.get("params"), context)
                self._hub.send({"type": "JOB_SUCCESS", "jobId": job_id, "data": result})
            except Exception as e:
                # MODIFIED: Capture and send the full traceback string for jobs
                tb_string = traceback.format_exc()
                self._hub.send({"type": "JOB_ERROR", "jobId": job_id, "message": str(e), "traceback": tb_string})
                traceback.print_exc()

        thread = threading.Thread(target=job_runner, daemon=True)
        thread.start()
        self._hub.send({"type": "JOB_STARTED", "reqId": request["reqId"], "jobId": job_id})

    def _handle_session_connect(self, request):
        handler = self._sessions.get(request["channel"])
        if handler: handler.on_connect(request["sessionId"], request.get("payload"))

    def _handle_session_disconnect(self, request):
        handler = self._sessions.get(request["channel"])
        if handler: handler.on_disconnect(request["sessionId"])

# endregion

# region BUSINESS LOGIC CODE
# ===================================================================
# ===============     BUSINESS LOGIC CODE     =======================
# ===================================================================
# This section contains your feature-specific command handlers.
# To add a new feature, create a new class implementing ICommandHandler
# or IAsyncCommandHandler, and register it in the Container below.
# -------------------------------------------------------------------

import time
import System
import System.Reflection

# Helper function to safely get a FullName to avoid exceptions with complex generic types
def safe_get_name(type_obj):
    try:
        return type_obj.FullName if type_obj else "N/A"
    except:
        return "Unknown Generic Type"

# Helper to format method/constructor parameters
def format_params(parameters):
    return [
        {"name": p.Name, "type": safe_get_name(p.ParameterType)}
        for p in parameters
    ]

from System.Reflection import BindingFlags
class AssemblyReflectionJob(IJobHandler):
    """
    Reflects the Mendix.StudioPro.ExtensionsAPI assembly to extract metadata
    about all its types.
    """
    command_type = "reflection:getApiMetadata"

    def run(self, payload: Dict, context: IJobContext):
        context.report_progress(ProgressUpdate(0, "Starting API reflection...", "Initializing"))
        
        from Mendix.StudioPro.ExtensionsAPI.BackgroundJobs import BackgroundJob
        job = BackgroundJob('test')
        jobType = job.GetType()
        assembly = jobType.Assembly
        if not assembly:
            raise RuntimeError("Could not find assembly: Mendix.StudioPro.ExtensionsAPI")
            
        # Use try-catch for GetTypes as it can fail on some assemblies
        try:
            all_types = list(assembly.GetTypes())
        except System.Reflection.ReflectionTypeLoadException as e:
            print("ReflectionTypeLoadException:", e.LoaderExceptions)
            raise e

        total_types = len(all_types)
        
        results = {"assemblyName": assembly.FullName, "types": []}
        
        binding_flags = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.DeclaredOnly

        for i, type_info in enumerate(all_types):
            progress = (i + 1) / total_types * 100
            if i % 10 == 0: # Report progress periodically
                context.report_progress(ProgressUpdate(progress, f"Analyzing {type_info.Name}", "Scanning"))

            if not type_info.IsPublic:
                continue # Skip non-public types for a cleaner view

            type_kind = "Class"
            if type_info.IsInterface: type_kind = "Interface"
            elif type_info.IsEnum: type_kind = "Enum"
            elif type_info.IsValueType and not type_info.IsEnum: type_kind = "Struct"
            
            type_data = {
                "fullName": type_info.FullName,
                "name": type_info.Name,
                "namespace": type_info.Namespace,
                "isPublic": type_info.IsPublic,
                "isAbstract": type_info.IsAbstract,
                "isSealed": type_info.IsSealed,
                "typeKind": type_kind,
                "baseType": safe_get_name(type_info.BaseType),
                "interfaces": [safe_get_name(i) for i in type_info.GetInterfaces()],
                "properties": [
                    {
                        "name": p.Name,
                        "type": safe_get_name(p.PropertyType),
                        "canRead": p.CanRead,
                        "canWrite": p.CanWrite,
                    } for p in type_info.GetProperties(binding_flags)
                ],
                "methods": [
                    {
                        "name": m.Name,
                        "returnType": safe_get_name(m.ReturnType),
                        "isStatic": m.IsStatic,
                        "parameters": format_params(m.GetParameters()),
                    } for m in type_info.GetMethods(binding_flags) if not m.IsSpecialName # Filter out property get/set methods
                ],
                "events": [
                    {
                        "name": e.Name,
                        "type": safe_get_name(e.EventHandlerType)
                    } for e in type_info.GetEvents(binding_flags)
                ],
                "fields": [
                    {
                        "name": f.Name,
                        "type": safe_get_name(f.FieldType),
                        "isStatic": f.IsStatic,
                    } for f in type_info.GetFields(binding_flags)
                ],
                "enumValues": list(System.Enum.GetNames(type_info)) if type_info.IsEnum else None,
            }
            results["types"].append(type_data)
        
        context.report_progress(ProgressUpdate(100, "Reflection complete.", "Finalizing"))
        # Sort types by name for a consistent UI
        results["types"].sort(key=lambda t: t["name"])
        return results




# endregion 

# region IOC & APP INITIALIZATION
# ===================================================================
# ==============     IOC & APP INITIALIZATION     ===================
# ===================================================================

from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    """The application's Inversion of Control (IoC) container."""
    config = providers.Configuration()

    # --- Framework Services (DIP) ---
    message_hub: providers.Provider[IMessageHub] = providers.Singleton(
        MendixMessageHub,
        post_message_func=config.post_message_func
    )

    # --- Business Logic Handlers (OCP) ---
    rpc_handlers = providers.List(
    )
    job_handlers = providers.List(
        providers.Singleton(AssemblyReflectionJob)
    )
    session_handlers = providers.List(
    )

    # --- Core Controller ---
    app_controller = providers.Singleton(
        AppController,
        rpc_handlers=rpc_handlers,
        job_handlers=job_handlers,
        session_handlers=session_handlers,
        message_hub=message_hub,
    )

def onMessage(e: Any):
    """Entry point called by Mendix Studio Pro for messages from the UI."""
    if e.Message != "frontend:message": return
    controller = container.app_controller()
    try:
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)
        controller.dispatch(request_object)
    except Exception as ex:
        traceback.print_exc()

def initialize_app():
    container = Container()
    container.config.from_dict({"post_message_func": PostMessage})
    return container

# --- Application Start ---
PostMessage("backend:clear", '')
container = initialize_app()
PostMessage("backend:info", "Backend Python script (Refactored) initialized successfully.")

# endregion