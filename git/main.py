# region FRAMEWORK CODE
from pymx.git import containers as containers2
import importlib
import re
import sys
import subprocess
import os
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
                # MODIFIED: Capture and send the full traceback string
                tb_string = traceback.format_exc()
                self._hub.send({"type": "RPC_ERROR", "reqId": req_id,
                               "message": str(e), "traceback": tb_string})
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
                # To test job error, uncomment the next line
                # raise ValueError("This is a deliberate job error")
                result = handler.run(request.get("params"), context)
                self._hub.send(
                    {"type": "JOB_SUCCESS", "jobId": job_id, "data": result})
            except Exception as e:
                # MODIFIED: Capture and send the full traceback string for jobs
                tb_string = traceback.format_exc()
                self._hub.send({"type": "JOB_ERROR", "jobId": job_id,
                               "message": str(e), "traceback": tb_string})
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


# Add these imports to the BUSINESS LOGIC CODE region
# Alias to avoid name clash with our own container
importlib.reload(containers2)

# Add these helper functions (or ensure they are present) from the old main.py
# into the BUSINESS LOGIC CODE region.


def execute_silent(command, cwd=None, timeout=None, check=True):
    """Executes a command silently, capturing stdout and stderr."""
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        return subprocess.run(
            command, capture_output=True, text=True, check=check,
            cwd=cwd, creationflags=creation_flags, timeout=timeout
        )
    except subprocess.CalledProcessError as e:
        # Provide more context by including stderr in the exception message
        error_details = e.stderr.strip() if e.stderr else e.stdout.strip()
        raise Exception(
            f"Command '{' '.join(command)}' failed with exit code {e.returncode}: {error_details}")
    except FileNotFoundError:
        raise Exception(
            f"Command not found: {command[0]}. Is Git installed and in your PATH?")
    except subprocess.TimeoutExpired:
        raise Exception(f"Command '{' '.join(command)}' timed out.")


def run_git_command(repo_path: str, command: list) -> str:
    """A generic helper to run a git command and return its stdout."""
    if not os.path.isdir(repo_path):
        raise FileNotFoundError(f"Project path '{repo_path}' does not exist.")
    result = execute_silent(["git"] + command, repo_path)
    return result.stdout.strip()


def parse_git_log(log_output: str) -> list:
    """
    Parses the raw output from 'git log' with a custom format into a structured list.
    This is the single, consolidated version.
    """
    commits = []
    if not log_output.strip():
        return []

    commit_blocks = log_output.strip().split("\ncommit ")
    if commit_blocks and not commit_blocks[0].startswith("commit "):
        commit_blocks[0] = "commit " + commit_blocks[0]

    for block in commit_blocks:
        if not block.strip():
            continue

        commit_data = {
            "sha": None, "author": None, "date": None, "message": None,
            "mx_metadata": None, "parents": [], "refs": []
        }
        notes_separator = "\n\nNotes (mx_metadata):\n"

        main_part, notes_part = (block.split(notes_separator, 1) + [None])[:2]

        if notes_part is not None:
            notes_content = notes_part.strip()
            if notes_content:
                try:
                    commit_data["mx_metadata"] = json.loads(notes_content)
                except json.JSONDecodeError:
                    commit_data["mx_metadata"] = {
                        "error": "JSONDecodeError", "raw": notes_content}

        lines = main_part.strip().split('\n')
        commit_data["sha"] = lines.pop(0).replace("commit ", "").strip()

        while lines:
            line = lines.pop(0)
            if line.startswith("Author:"):
                commit_data["author"] = line.split(":", 1)[1].strip()
            elif line.startswith("Date:"):
                commit_data["date"] = line.split(":", 1)[1].strip()
            elif line.startswith("Parents:"):
                parents_str = line.split(":", 1)[1].strip()
                if parents_str:
                    commit_data["parents"] = parents_str.split()
            elif line.startswith("Refs:"):
                refs_str = line.split(":", 1)[1].strip()
                if refs_str.startswith("(") and refs_str.endswith(")"):
                    refs_str = refs_str[1:-1]
                    commit_data["refs"] = [r.strip()
                                           for r in refs_str.split(",")]
            elif not line.strip():
                commit_data["message"] = "\n".join(lines).strip()
                break
        commits.append(commit_data)
    return commits


def get_git_notes_log_paginated(repo_path: str, page_size: int, skip_count: int) -> (list, bool):
    """Runs git log with pagination and returns commits and a has_more flag."""
    if not os.path.isdir(os.path.join(repo_path, '.git')):
        raise FileNotFoundError(
            f"'{repo_path}' is not a valid Git repository.")

    log_format = (
        "commit %H%n"
        "Author: %an%n"
        "Date: %ai%n"
        "Parents: %P%n"
        "Refs: %d%n"
        "%n%s%n%b"
        "%n%nNotes (mx_metadata):%n%N"
    )
    command = [
        "git", "log", "--show-notes=mx_metadata", "--decorate=full",
        f"--pretty=format:{log_format}", f"--max-count={page_size + 1}", f"--skip={skip_count}"
    ]
    result = execute_silent(command, repo_path)
    all_fetched_commits = parse_git_log(result.stdout)

    has_more = len(all_fetched_commits) > page_size
    return all_fetched_commits[:page_size], has_more


def get_git_status_info(repo_path: str) -> dict:
    """Gathers comprehensive status information about the Git repository."""
    is_repo = os.path.isdir(os.path.join(repo_path, '.git'))
    if not is_repo:
        return {"isRepo": False}
    try:
        current_branch = run_git_command(
            repo_path, ["branch", "--show-current"])
        branches_output = run_git_command(repo_path, ["branch"])
        all_branches = [b.strip().lstrip('* ')
                        for b in branches_output.split('\n')]
        remotes = []
        remotes_output = run_git_command(repo_path, ["remote", "-v"])
        if remotes_output:
            remote_map = {}
            for line in remotes_output.split('\n'):
                name, url, _ = re.split(r'\s+', line, 2)
                if name not in remote_map:
                    remote_map[name] = url
            remotes = [{"name": name, "url": url}
                       for name, url in remote_map.items()]
        return {"isRepo": True, "currentBranch": current_branch, "allBranches": all_branches, "remotes": remotes}
    except Exception as e:
        return {"isRepo": True, "error": str(e)}

# Add these new handler classes to the BUSINESS LOGIC CODE region.


class GetGitStatusRpc(IRpcHandler):
    """RPC handler for getting the overall status of the git repository."""
    command_type = "git:getStatus"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Any:
        return get_git_status_info(self._mendix_env.get_project_path())


class GetGitLogRpc(IRpcHandler):
    """RPC handler for fetching a paginated list of the git commit history."""
    command_type = "git:getLog"
    DEFAULT_PAGE_SIZE = 20

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Any:
        page = payload.get("page", 1)
        page_size = payload.get("pageSize", self.DEFAULT_PAGE_SIZE)
        skip_count = (page - 1) * page_size
        repo_path = self._mendix_env.get_project_path()
        commits, has_more = get_git_notes_log_paginated(
            repo_path, page_size, skip_count)
        return {"commits": commits, "hasMore": has_more}


class GitDiffJob(IJobHandler):
    """
    Handles comparing two git commits as a long-running job with progress updates.
    """
    command_type = "diff:run"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def run(self, payload: Dict, context: IJobContext):
        old_commit = payload.get("oldCommit")
        new_commit = payload.get("newCommit")
        if not old_commit or not new_commit:
            raise ValueError(
                "Payload must contain both 'oldCommit' and 'newCommit'.")

        repo_path = self._mendix_env.get_project_path()

        context.report_progress(ProgressUpdate(
            percent=0.0, message=f"Starting comparison...", stage="Initializing"))
        time.sleep(0.5)

        context.report_progress(ProgressUpdate(
            percent=15.0, message=f"Loading model data for base commit {old_commit[:7]}...", stage="Loading Base"))
        time.sleep(1)

        context.report_progress(ProgressUpdate(
            percent=40.0, message=f"Loading model data for target commit {new_commit[:7]}...", stage="Loading Target"))
        time.sleep(1)

        context.report_progress(ProgressUpdate(
            percent=65.0, message="Analyzing differences between models...", stage="Analyzing"))

        diff_result = containers2.perform_pymx_diff(
            repo_path=repo_path, old_commit=old_commit, new_commit=new_commit)
        time.sleep(0.5)

        context.report_progress(ProgressUpdate(
            percent=95.0, message="Formatting comparison results...", stage="Finalizing"))
        time.sleep(0.2)

        return diff_result


class GitInitJob(IJobHandler):
    """Initializes a repo and makes the first commit as a job."""
    command_type = "git:init"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def run(self, payload: Dict, context: IJobContext):
        message = payload.get("message", "Initial commit")
        repo_path = self._mendix_env.get_project_path()

        # --- START MODIFICATION: Add .gitignore creation ---
        context.report_progress(ProgressUpdate(
            percent=0.0, message="Checking for .gitignore file...", stage="Setup"))

        gitignore_path = os.path.join(repo_path, ".gitignore")
        gitignore_content = """/**/node_modules/
!/javascriptsource/**/node_modules/
/*.launch
/.classpath
/.mendix-cache/
/.project
/deployment/
/javasource/*/proxies/
/javasource/system/
/modeler-merge-marker
/nativemobile/builds
/packages/
/project-settings.user.json
/releases/
*.mpr.lock
*.mpr.bak
/vendorlib/temp/
.DS_Store
/app.mpr.bak
/app.mpr.lock
/nativemobile/builds/
/.svn/
"""
        if not os.path.exists(gitignore_path):
            context.report_progress(ProgressUpdate(
                percent=5.0, message="Creating Mendix-specific .gitignore file...", stage="Setup"))
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write(gitignore_content)
            time.sleep(0.2)
        else:
            context.report_progress(ProgressUpdate(
                percent=5.0, message=".gitignore already exists, skipping.", stage="Setup"))

        context.report_progress(ProgressUpdate(
            percent=10.0, message="Starting repository initialization...", stage="Begin"))
        # --- END MODIFICATION ---

        run_git_command(repo_path, ["init"])
        context.report_progress(ProgressUpdate(
            percent=25.0, message="Git repository created.", stage="Init"))
        time.sleep(0.5)

        context.report_progress(ProgressUpdate(
            percent=40.0, message="Adding all project files to the index...", stage="Add"))
        run_git_command(repo_path, ["add", "."])
        context.report_progress(ProgressUpdate(
            percent=75.0, message="Files added.", stage="Add"))
        time.sleep(1)  # Simulate work

        context.report_progress(ProgressUpdate(
            percent=80.0, message=f"Committing with message: '{message}'...", stage="Commit"))
        run_git_command(repo_path, ["commit", "-m", message])
        commit_sha = run_git_command(repo_path, ["rev-parse", "HEAD"])

        # Add Mendix metadata note
        mx_metadata_note = '{"BranchName":"","ModelerVersion":"10.24.4.77222","ModelChanges":[],"RelatedStories":[],"SolutionVersion":"","MPRFormatVersion":"Version2","HasModelerVersion":true}'
        run_git_command(repo_path, [
                        "notes", "--ref=mx_metadata", "add", "-m", mx_metadata_note, commit_sha])
        context.report_progress(ProgressUpdate(
            percent=95.0, message="Mendix metadata attached.", stage="Commit"))

        return {"status": "success", "commitSha": commit_sha}


class GitSwitchBranchRpc(IRpcHandler):
    """Handles switching the current git branch."""
    command_type = "git:switchBranch"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Any:
        branch_name = payload.get("branchName")
        if not branch_name:
            raise ValueError("Payload must contain 'branchName'.")
        run_git_command(self._mendix_env.get_project_path(),
                        ["checkout", branch_name])
        return {"status": "success", "switchedTo": branch_name}


class GitAddRemoteRpc(IRpcHandler):
    """Handles adding a new git remote."""
    command_type = "git:addRemote"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Any:
        name, url = payload.get("name"), payload.get("url")
        if not name or not url:
            raise ValueError("Payload must contain 'name' and 'url'.")
        run_git_command(self._mendix_env.get_project_path(),
                        ["remote", "add", name, url])
        return {"status": "success", "name": name, "url": url}


class GitDeleteRemoteRpc(IRpcHandler):
    """Handles deleting a git remote."""
    command_type = "git:deleteRemote"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Any:
        remote_name = payload.get("remoteName")
        if not remote_name:
            raise ValueError("Payload must contain 'remoteName'.")
        run_git_command(self._mendix_env.get_project_path(),
                        ["remote", "rm", remote_name])
        return {"status": "success", "removed": remote_name}


class GitPushJob(IJobHandler):
    """Handles pushing to a specified remote as a job."""
    command_type = "git:push"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def run(self, payload: Dict, context: IJobContext):
        remote_name, branch_name = payload.get(
            "remoteName"), payload.get("branchName")
        if not remote_name or not branch_name:
            raise ValueError(
                "Payload must contain 'remoteName' and 'branchName'.")

        repo_path = self._mendix_env.get_project_path()
        context.report_progress(ProgressUpdate(
            percent=10.0, message=f"Starting push to '{remote_name}'...", stage="Connecting"))

        time.sleep(1)  # simulate connection
        context.report_progress(ProgressUpdate(
            percent=50.0, message=f"Pushing branch '{branch_name}'...", stage="Uploading"))

        result = execute_silent(
            ["git", "push", remote_name, branch_name], repo_path, timeout=120, check=False)

        if result.returncode != 0:
            error_message = result.stderr.strip() if result.stderr else result.stdout.strip()
            raise Exception(f"Push failed: {error_message}")

        context.report_progress(ProgressUpdate(
            percent=95.0, message="Push completed successfully.", stage="Finalizing"))
        return {"status": "success", "output": result.stdout.strip() or result.stderr.strip()}


class GitSetRemoteUrlRpc(IRpcHandler):
    """Handles setting the URL for a git remote."""
    command_type = "git:setRemoteUrl"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Any:
        remote_name, url = payload.get("remoteName"), payload.get("url")
        if not remote_name or not url:
            raise ValueError("Payload must contain 'remoteName' and 'url'.")
        run_git_command(self._mendix_env.get_project_path(), [
                        "remote", "set-url", remote_name, url])
        return {"status": "success", "remote": remote_name, "newUrl": url}

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

    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        window_service=config.window_service,
        post_message_func=config.post_message_func,
    )

    # --- Business Logic Handlers (OCP) ---
    rpc_handlers = providers.List(
        providers.Singleton(GetGitStatusRpc, mendix_env=mendix_env),
        providers.Singleton(GetGitLogRpc, mendix_env=mendix_env),
        providers.Singleton(GitSwitchBranchRpc, mendix_env=mendix_env),
        providers.Singleton(GitAddRemoteRpc, mendix_env=mendix_env),
        providers.Singleton(GitDeleteRemoteRpc, mendix_env=mendix_env),
        providers.Singleton(GitSetRemoteUrlRpc, mendix_env=mendix_env),
    )
    job_handlers = providers.List(
        providers.Singleton(GitDiffJob, mendix_env=mendix_env),
        providers.Singleton(GitInitJob, mendix_env=mendix_env),
        providers.Singleton(GitPushJob, mendix_env=mendix_env),
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
# endregion


def initialize_app():
    container = Container()
    # ADDED app_context and window_service for MendixEnvironmentService
    container.config.from_dict({
        "post_message_func": PostMessage,
        "app_context": currentApp,
        "window_service": dockingWindowService
    })
    return container


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


# --- Application Start ---
PostMessage("backend:clear", '')
container = initialize_app()
PostMessage("backend:info",
            "Backend Python script (Refactored) initialized successfully.")

# endregion
