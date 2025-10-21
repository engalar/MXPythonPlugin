# region FRAMEWORK CODE
from Mendix.StudioPro.ExtensionsAPI.BackgroundJobs import BackgroundJob
from System import Func, Boolean
import time
from typing import Any, Dict, Callable, Iterable, Optional, Protocol
from System.Text.Json import JsonSerializer
from dependency_injector import containers, providers
import uuid
import threading
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


# ===================================================================
# ===================    CORE ABSTRACTIONS     ======================
# ===================================================================


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
        self.send({"type": "EVENT_BROADCAST",
                  "channel": channel, "data": data})

    def push_to_session(self, session_id: str, data: Any):
        self.send({"type": "EVENT_SESSION",
                  "sessionId": session_id, "data": data})


class AppController:
    """Routes incoming messages to registered handlers. Obeys OCP."""

    def __init__(self, rpc_handlers: Iterable[IRpcHandler], job_handlers: Iterable[IJobHandler],
                 session_handlers: Iterable[ISessionHandler], message_hub: IMessageHub):
        self._rpc = {h.command_type: h for h in rpc_handlers}
        self._jobs = {h.command_type: h for h in job_handlers}
        self._sessions = {h.command_type: h for h in session_handlers}
        self._hub = message_hub
        print(
            f"Controller initialized. RPCs: {list(self._rpc.keys())}, Jobs: {list(self._jobs.keys())}, Sessions: {list(self._sessions.keys())}")

    def dispatch(self, request: Dict):
        msg_type = request.get("type")
        try:
            if msg_type == "RPC":
                self._handle_rpc(request)
            elif msg_type == "JOB_START":
                self._handle_job_start(request)
            elif msg_type == "SESSION_CONNECT":
                self._handle_session_connect(request)
            elif msg_type == "SESSION_DISCONNECT":
                self._handle_session_disconnect(request)
            else:
                raise ValueError(f"Unknown message type: {msg_type}")
        except Exception as e:
            req_id = request.get("reqId")
            if req_id:
                self._hub.send(
                    {"type": "RPC_ERROR", "reqId": req_id, "message": str(e)})
            traceback.print_exc()

    def _handle_rpc(self, request):
        handler = self._rpc.get(request["method"])
        if not handler:
            raise ValueError(f"No RPC handler for '{request['method']}'")
        result = handler.execute(request.get("params"))
        self._hub.send(
            {"type": "RPC_SUCCESS", "reqId": request["reqId"], "data": result})

    def _handle_job_start(self, request):
        handler = self._jobs.get(request["method"])
        if not handler:
            raise ValueError(f"No Job handler for '{request['method']}'")

        job_id = f"job-{uuid.uuid4()}"

        class JobContext(IJobContext):
            def __init__(self, job_id: str, hub: IMessageHub):
                self.job_id = job_id
                self._hub = hub

            def report_progress(self, progress: ProgressUpdate):
                self._hub.send(
                    {"type": "JOB_PROGRESS", "jobId": self.job_id, "progress": progress.to_dict()})

        context = JobContext(job_id, self._hub)

        def job_runner():
            try:
                result = handler.run(request.get("params"), context)
                self._hub.send(
                    {"type": "JOB_SUCCESS", "jobId": job_id, "data": result})
            except Exception as e:
                self._hub.send(
                    {"type": "JOB_ERROR", "jobId": job_id, "message": str(e)})
                traceback.print_exc()

        thread = threading.Thread(target=job_runner, daemon=True)
        thread.start()
        self._hub.send(
            {"type": "JOB_STARTED", "reqId": request["reqId"], "jobId": job_id})

    def _handle_session_connect(self, request):
        handler = self._sessions.get(request["channel"])
        if handler:
            handler.on_connect(request["sessionId"], request.get("payload"))

    def _handle_session_disconnect(self, request):
        handler = self._sessions.get(request["channel"])
        if handler:
            handler.on_disconnect(request["sessionId"])

# endregion


# region BUSINESS LOGIC CODE
# ===================================================================
# ===============     BUSINESS LOGIC CODE     =======================
# ===================================================================
# This section contains your feature-specific command handlers.
# To add a new feature, create a new class implementing ICommandHandler
# or IAsyncCommandHandler, and register it in the Container below.
# -------------------------------------------------------------------


class MendixOperationJob(IJobHandler):
    """
    Runs a simulated multi-step Mendix background job and reports detailed progress.
    This replaces the poll-based `JobStateService` with a push-based model,
    aligning with the existing framework's `IJobHandler` pattern.
    """
    command_type = "mendix:runOperation"

    def run(self, payload: Dict, context: IJobContext):
        job_title = payload.get("title", "Mendix Background Operation")

        steps_config = [
            {"title": "环境检查", "desc": "检查模型完整性", "dur": 1.5},
            {"title": "依赖分析", "desc": "分析模块间依赖", "dur": 2.0},
            {"title": "代码生成", "desc": "生成领域代码", "dur": 1.0},
            {"title": "清理资源", "desc": "释放临时句柄", "dur": 0.5}
        ]

        # Initial state for the UI
        steps_state = [{"title": s["title"], "status": "pending"}
                       for s in steps_config]
        total_duration = sum(s["dur"] for s in steps_config)
        time_elapsed = 0

        context.report_progress(ProgressUpdate(
            percent=0.0,
            message="Job queued, awaiting execution...",
            stage="Queued",
            metadata={"steps": steps_state}
        ))
        time.sleep(0.5)  # Simulate job pickup delay

        def create_step_func(step_title, duration, i):
            def step_implementation() -> bool:
                try:
                    steps_state[i]['status'] = 'running'
                    p = i/len(steps_config)
                    context.report_progress(ProgressUpdate(
                        percent=p * 100,
                        message=f"Executing: {step_title}",
                        stage=step_title,
                        metadata={"steps": steps_state}
                    ))
                    time.sleep(duration)
                    steps_state[i]['status'] = 'completed'
                    p = (i+1)/len(steps_config)
                    context.report_progress(ProgressUpdate(
                        percent=p * 100,
                        message=f"Executing: {step_title}",
                        stage=step_title,
                        metadata={"steps": steps_state}
                    ))
                    return True
                except Exception:
                    # In a real app, you might want to update the state to "failed"
                    return False
            return step_implementation
        job = BackgroundJob(job_title)

        for i, step_config in enumerate(steps_config):
            py_func = create_step_func(
                step_config["title"], step_config["dur"], i)
            net_func = Func[Boolean](py_func)
            job.AddStep(step_config["title"], step_config["desc"], net_func)

        backgroundJobService.Run(job)

        return {"status": "Completed", "steps_executed": len(steps_config)}


# endregion

# region IOC & APP INITIALIZATION
# ===================================================================
# ==============     IOC & APP INITIALIZATION     ===================
# ===================================================================


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
        providers.Singleton(MendixOperationJob)
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
    if e.Message != "frontend:message":
        return
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
PostMessage("backend:info",
            "Backend Python script (Refactored) initialized successfully.")

# endregion
