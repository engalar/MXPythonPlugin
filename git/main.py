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
import os
import subprocess
import sys
import re
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
        raise Exception(f"Command '{' '.join(command)}' failed with exit code {e.returncode}: {error_details}")
    except FileNotFoundError:
        raise Exception(f"Command not found: {command[0]}. Is Git installed and in your PATH?")
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
                    commit_data["mx_metadata"] = {"error": "JSONDecodeError", "raw": notes_content}

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
                    commit_data["refs"] = [r.strip() for r in refs_str.split(",")]
            elif not line.strip():
                commit_data["message"] = "\n".join(lines).strip()
                break
        commits.append(commit_data)
    return commits

def get_git_notes_log_paginated(repo_path: str, page_size: int, skip_count: int) -> (list, bool):
    """Runs git log with pagination and returns commits and a has_more flag."""
    if not os.path.isdir(os.path.join(repo_path, '.git')):
        raise FileNotFoundError(f"'{repo_path}' is not a valid Git repository.")

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
        current_branch = run_git_command(repo_path, ["branch", "--show-current"])
        branches_output = run_git_command(repo_path, ["branch"])
        all_branches = [b.strip().lstrip('* ') for b in branches_output.split('\n')]
        remotes = []
        remotes_output = run_git_command(repo_path, ["remote", "-v"])
        if remotes_output:
            remote_map = {}
            for line in remotes_output.split('\n'):
                name, url, _ = re.split(r'\s+', line, 2)
                if name not in remote_map:
                    remote_map[name] = url
            remotes = [{"name": name, "url": url} for name, url in remote_map.items()]
        return {"isRepo": True, "currentBranch": current_branch, "allBranches": all_branches, "remotes": remotes}
    except Exception as e:
        return {"isRepo": True, "error": str(e)}

def initialize_and_commit(repo_path: str, message: str) -> dict:
    """Initializes a git repository, adds all files, and commits."""
    run_git_command(repo_path, ["init"])
    run_git_command(repo_path, ["add", "."])
    run_git_command(repo_path, ["commit", "-m", message])
    commit_sha = run_git_command(repo_path, ["rev-parse", "HEAD"])
    mx_metadata_note = '{"BranchName":"","ModelerVersion":"10.24.4.77222","ModelChanges":[],"RelatedStories":[],"SolutionVersion":"","MPRFormatVersion":"Version2","HasModelerVersion":true}'
    run_git_command(repo_path, ["notes", "--ref=mx_metadata", "add", "-m", mx_metadata_note, commit_sha])
    return {"status": "success", "commitSha": commit_sha}


# 4. BUSINESS LOGIC: COMMAND HANDLER IMPLEMENTATIONS

class GitLogCommandHandler(ICommandHandler):
    """Handles fetching a paginated list of the git commit history."""
    command_type = "GET_GIT_LOG"
    DEFAULT_PAGE_SIZE = 20

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> dict:
        page = payload.get("page", 1)
        page_size = payload.get("pageSize", self.DEFAULT_PAGE_SIZE)
        skip_count = (page - 1) * page_size
        repo_path = self._mendix_env.get_project_path()
        commits, has_more = get_git_notes_log_paginated(repo_path, page_size, skip_count)
        return {"commits": commits, "hasMore": has_more}

class GetGitStatusCommandHandler(ICommandHandler):
    """Handles getting the overall status of the git repository."""
    command_type = "GET_GIT_STATUS"
    def __init__(self, mendix_env: MendixEnvironmentService): self._mendix_env = mendix_env
    def execute(self, payload: Dict) -> Dict:
        return get_git_status_info(self._mendix_env.get_project_path())

class GitInitCommitCommandHandler(IAsyncCommandHandler):
    """Handles initializing a repo and making the first commit."""
    command_type = "GIT_INIT_COMMIT"
    def __init__(self, mendix_env: MendixEnvironmentService): self._mendix_env = mendix_env
    def execute(self, payload: Dict) -> Any:
        """Main thread: returns immediately, confirming the task has started."""
        return {"status": "accepted", "message": "Async task accepted and running."}

    def execute_async(self, payload: Dict, task_id: str):
        """Background thread: performs the long-running work."""
        try:
            message = payload.get("message")
            data = initialize_and_commit(self._mendix_env.get_project_path(), message)

            completion_event = {
                "taskId": task_id,
                "status": "success",
                "data": data
            }
            self._mendix_env.post_message("backend:response", json.dumps(completion_event))

        except Exception as e:
            error_message = f"Error in async task {task_id}: {e}"
            self._mendix_env.post_message("backend:info", f"{error_message}\n{traceback.format_exc()}")
            error_event = {
                "taskId": task_id,
                "status": "error",
                "message": error_message
            }
            self._mendix_env.post_message("backend:response", json.dumps(error_event))

class GitSwitchBranchCommandHandler(ICommandHandler):
    """Handles switching the current git branch."""
    command_type = "GIT_SWITCH_BRANCH"
    def __init__(self, mendix_env: MendixEnvironmentService): self._mendix_env = mendix_env
    def execute(self, payload: Dict) -> Dict:
        branch_name = payload.get("branchName")
        if not branch_name: raise ValueError("Payload must contain 'branchName'.")
        run_git_command(self._mendix_env.get_project_path(), ["checkout", branch_name])
        return {"status": "success", "switchedTo": branch_name}

class GitAddRemoteCommandHandler(ICommandHandler):
    """Handles adding a new git remote."""
    command_type = "GIT_ADD_REMOTE"
    def __init__(self, mendix_env: MendixEnvironmentService): self._mendix_env = mendix_env
    def execute(self, payload: Dict) -> Dict:
        name, url = payload.get("name"), payload.get("url")
        if not name or not url: raise ValueError("Payload must contain 'name' and 'url'.")
        run_git_command(self._mendix_env.get_project_path(), ["remote", "add", name, url])
        return {"status": "success", "name": name, "url": url}

class GitDeleteRemoteCommandHandler(ICommandHandler):
    """Handles deleting a git remote."""
    command_type = "GIT_DELETE_REMOTE"
    def __init__(self, mendix_env: MendixEnvironmentService): self._mendix_env = mendix_env
    def execute(self, payload: Dict) -> Dict:
        remote_name = payload.get("remoteName")
        if not remote_name: raise ValueError("Payload must contain 'remoteName'.")
        run_git_command(self._mendix_env.get_project_path(), ["remote", "rm", remote_name])
        return {"status": "success", "removed": remote_name}

class GitPushCommandHandler(ICommandHandler):
    """Handles pushing to a specified remote."""
    command_type = "GIT_PUSH"
    def __init__(self, mendix_env: MendixEnvironmentService): self._mendix_env = mendix_env
    def execute(self, payload: Dict) -> Dict:
        remote_name, branch_name = payload.get("remoteName"), payload.get("branchName")
        if not remote_name or not branch_name: raise ValueError("Payload must contain 'remoteName' and 'branchName'.")
        repo_path = self._mendix_env.get_project_path()
        # Use execute_silent with check=False to handle git's non-zero exit codes on some "successful" pushes with warnings
        result = execute_silent(["git", "push", remote_name, branch_name], repo_path, timeout=120, check=False)
        if result.returncode != 0:
            error_message = result.stderr.strip() if result.stderr else result.stdout.strip()
            raise Exception(f"Push failed: {error_message}")
        return {"status": "success", "output": result.stdout.strip() or result.stderr.strip()}

class GitSetRemoteUrlCommandHandler(ICommandHandler):
    """Handles setting the URL for a git remote."""
    command_type = "GIT_SET_REMOTE_URL"
    def __init__(self, mendix_env: MendixEnvironmentService): self._mendix_env = mendix_env
    def execute(self, payload: Dict) -> Dict:
        remote_name, url = payload.get("remoteName"), payload.get("url")
        if not remote_name or not url: raise ValueError("Payload must contain 'remoteName' and 'url'.")
        run_git_command(self._mendix_env.get_project_path(), ["remote", "set-url", remote_name, url])
        return {"status": "success", "remote": remote_name, "newUrl": url}
    
# endregion 

# region IOC & APP INITIALIZATION
# ===================================================================
# ==============     IOC & APP INITIALIZATION     ===================
# ===================================================================

class Container(containers.DeclarativeContainer):
    """The application's Inversion of Control (IoC) container."""
    config = providers.Configuration()

    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        window_service=config.window_service,
        post_message_func=config.post_message_func,
    )
    
    command_handlers = providers.List(
        providers.Singleton(GitLogCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GetGitStatusCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GitInitCommitCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GitSwitchBranchCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GitAddRemoteCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GitDeleteRemoteCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GitPushCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GitSetRemoteUrlCommandHandler, mendix_env=mendix_env),
    )
    
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