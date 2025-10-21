# region FRAMEWORK CODE
from System import Func, Boolean
from Mendix.StudioPro.ExtensionsAPI.BackgroundJobs import BackgroundJob
import time
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

    def __init__(self, app_context, window_service, post_message_func: Callable, background_job_service):
        self.app = app_context
        self.window_service = window_service
        self.post_message = post_message_func
        self.background_job_service = background_job_service

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
                raise ValueError(
                    f"No handler found for command type: {command_type}")

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
# ===================================================================
# ===============     BUSINESS LOGIC CODE     =======================
# ===================================================================

# --- NEW: Thread-safe state management for background jobs ---

class JobStateService:
    """A thread-safe singleton service to store and retrieve job progress."""

    def __init__(self):
        self._states = {}
        self._lock = threading.Lock()

    def create_job(self, job_id, initial_state):
        with self._lock:
            self._states[job_id] = initial_state

    def update_step_status(self, job_id, step_title, status):
        with self._lock:
            if job_id in self._states:
                job = self._states[job_id]
                # Update status for the specific step
                for step in job["steps"]:
                    if step["title"] == step_title:
                        step["status"] = status
                        break
                # Update overall job status
                all_steps_completed = all(
                    s["status"] == "completed" for s in job["steps"])
                job["status"] = "completed" if all_steps_completed else "running"

    def get_states(self, job_ids: list):
        with self._lock:
            # Return states only for the requested job IDs
            return {job_id: self._states.get(job_id) for job_id in job_ids if job_id in self._states}


class StartBackgroundJobCommandHandler(ICommandHandler):
    command_type = "START_BACKGROUND_JOB"

    def __init__(self, mendix_env: MendixEnvironmentService, state_service: JobStateService):
        self._mendix_env = mendix_env
        self._state_service = state_service

    def execute(self, payload: Dict) -> Any:
        job_title = payload.get("title", "Mendix 作业")
        job_id = str(uuid.uuid4())

        steps_config = [
            {"title": "环境检查", "desc": "检查模型完整性", "dur": 1.5},
            {"title": "依赖分析", "desc": "分析模块间依赖", "dur": 2.0},
            {"title": "代码生成", "desc": "生成领域代码", "dur": 1.0},
            {"title": "清理资源", "desc": "释放临时句柄", "dur": 0.5}
        ]

        initial_state = {
            "jobId": job_id,
            "title": job_title,
            "status": "queued",
            "steps": [{"title": s["title"], "status": "pending"} for s in steps_config]
        }
        self._state_service.create_job(job_id, initial_state)

        def create_step_func(step_title, duration):
            def step_implementation() -> bool:
                try:
                    self._state_service.update_step_status(
                        job_id, step_title, "running")
                    time.sleep(duration)
                    self._state_service.update_step_status(
                        job_id, step_title, "completed")
                    return True
                except Exception:
                    # In a real app, you might want to update the state to "failed"
                    return False
            return step_implementation

        # 1. Create the job object
        job = BackgroundJob(job_title)

        # 2. Add steps with state-updating logic
        for step in steps_config:
            py_func = create_step_func(step["title"], step["dur"])
            net_func = Func[Boolean](py_func)
            job.AddStep(step["title"], step["desc"], net_func)

        # 3. [CRITICAL FIX] Actually run the job using the injected service
        # This was the missing line. It schedules the job to run in a Mendix background thread.
        self._mendix_env.background_job_service.Run(job)

        # 4. Immediately return the initial state to the frontend
        return initial_state


class GetJobStatusCommandHandler(ICommandHandler):
    command_type = "GET_JOB_STATUS"

    def __init__(self, state_service: JobStateService):
        self._state_service = state_service

    def execute(self, payload: Dict) -> Any:
        job_ids = payload.get("jobIds", [])
        if not job_ids:
            return {}
        return self._state_service.get_states(job_ids)

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
        background_job_service=config.background_job_service,
    )

    # --- Business Logic Registrations ---
    job_state_service = providers.Singleton(JobStateService)
    # To add a new command, add its handler to this list.
    command_handlers = providers.List(
        providers.Singleton(StartBackgroundJobCommandHandler,
                            mendix_env=mendix_env, state_service=job_state_service),
        providers.Singleton(GetJobStatusCommandHandler,
                            state_service=job_state_service),
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
        "post_message_func": PostMessage,
        "background_job_service": backgroundJobService
    })
    return container


# --- Application Start ---
PostMessage("backend:clear", '')
container = initialize_app()
PostMessage("backend:info", "Backend Python script initialized successfully.")

# endregion
