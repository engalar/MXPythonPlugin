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
def info(e):
    PostMessage("backend:info", f'{e}')


_dir = dir


def dir(e):
    PostMessage("backend:info", f'{_dir(e)}')


def error(e):
    PostMessage("backend:error", f'{e}')

def print(e):
    PostMessage("backend:info", e)

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
class DeliberateErrorRpc(IRpcHandler):
    """An RPC handler that always raises an exception to test error handling."""
    command_type = "system:deliberateError"
    def execute(self, payload: Dict) -> Any:
        # This will cause a traceback to be generated and sent to the frontend.
        x = 1
        y = 0
        return x / y # Raises ZeroDivisionError
class GetSystemInfoRpc(IRpcHandler):
    """Example of a simple RPC handler."""
    command_type = "system:getInfo"
    def execute(self, payload: Dict) -> Any:
        return {"pythonVersion": "3.x", "status": "OK", "timestamp": time.time()}

class TriggerBroadcastRpc(IRpcHandler):
    """Triggers a server-wide broadcast message to all clients."""
    command_type = "system:triggerBroadcast"

    def __init__(self, message_hub: IMessageHub):
        self._hub = message_hub

    def execute(self, payload: Dict) -> Any:
        message_text = payload.get("message", "This is a default broadcast message!")
        
        # The hub abstracts away the details of sending messages.
        # This message will go to all clients listening on this channel.
        self._hub.broadcast("global:notifications", {
            "text": message_text,
            "timestamp": time.time()
        })
        
        return {"status": "Broadcast sent successfully."}

class FileImportJob(IJobHandler):
    """Example of a long-running job with detailed progress."""
    command_type = "import:file"
    def run(self, payload: Dict, context: IJobContext):
        filename = payload.get("filename", "unknown.csv")
        context.report_progress(ProgressUpdate(percent=0.0, message=f"Starting import for {filename}...", stage="Initializing"))
        time.sleep(1)

        context.report_progress(ProgressUpdate(percent=25.0, message="Reading file into memory...", stage="Reading"))
        time.sleep(2)

        context.report_progress(ProgressUpdate(percent=60.0, message="Processing 50,000 rows...", stage="Processing"))
        time.sleep(3)

        context.report_progress(ProgressUpdate(percent=95.0, message="Finalizing and saving to database...", stage="Saving"))
        time.sleep(1)
        
        return {"rowsImported": 50000, "status": "Completed"}

class RealtimeLogSession(ISessionHandler):
    """Example of a targeted session handler."""
    command_type = "logs:realtime"
    def __init__(self, message_hub: IMessageHub):
        self._hub = message_hub
        self._active_sessions = set()
        
    def on_connect(self, session_id: str, payload: Optional[Dict]):
        print(f"[Logger] Session {session_id} connected.")
        self._active_sessions.add(session_id)
        self._hub.push_to_session(session_id, {"level": "info", "message": "Log stream connected successfully."})

    def on_disconnect(self, session_id: str):
        print(f"[Logger] Session {session_id} disconnected.")
        self._active_sessions.discard(session_id)


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
        providers.Singleton(GetSystemInfoRpc),
        providers.Singleton(TriggerBroadcastRpc, message_hub=message_hub),
        providers.Singleton(DeliberateErrorRpc),
    )
    job_handlers = providers.List(
        providers.Singleton(FileImportJob)
    )
    session_handlers = providers.List(
        providers.Singleton(RealtimeLogSession, message_hub=message_hub)
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