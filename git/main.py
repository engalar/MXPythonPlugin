import subprocess
import sys
import os
from dependency_injector import containers, providers
from System.Text.Json import JsonSerializer
import re

# region Boilerplate Imports
import json
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod

# Mendix and .NET related imports
import clr
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# Dependency Injection framework

# --- START: New Imports for Git Log Functionality ---


def execute_silent(command, cwd=None, timeout=None):
    """
    执行命令，捕获 stdout 和 stderr，并确保在 Windows 上没有控制台窗口弹出。

    Args:
        command (list): 要执行的命令列表。
        timeout (int): 命令超时时间（秒）。

    Returns:
        subprocess.CompletedProcess: 包含 stdout, stderr, 和 returncode。
    """

    # 1. 设置 Windows 静默标志
    creation_flags = 0
    if sys.platform == "win32":
        # 0x08000000 是 CREATE_NO_WINDOW 的值
        creation_flags = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(
            command,
            capture_output=True,  # 关键：捕获 stdout 和 stderr
            text=True,            # 将输出解码为文本（使用默认系统编码）
            check=True,           # 如果返回非零状态码，则抛出 CalledProcessError
            cwd=cwd,
            creationflags=creation_flags,
            timeout=timeout
        )
        return result

    except subprocess.CalledProcessError as e:
        print(f"命令执行失败，返回码: {e.returncode}")
        print("Standard Output (partial):\n", e.stdout)
        print("Standard Error:\n", e.stderr)
        # 可以选择重新抛出异常，或返回一个包含错误的CompletedProcess对象
        raise
    except FileNotFoundError:
        print(f"找不到可执行文件: {command[0]}")
        raise
    except subprocess.TimeoutExpired:
        print("命令执行超时")
        raise
    except Exception as e:
        print(f"发生未知错误: {e}")
        raise
# --- END: New Imports for Git Log Functionality ---
# endregion

# ===================================================================
# 1. CORE SERVICES AND ABSTRACTIONS
# ===================================================================


class MendixEnvironmentService:
    """
    A service that abstracts the Mendix host environment global variables.
    It provides a clean way to access Mendix APIs.
    """

    def __init__(self, app_context, window_service, post_message_func: Callable):
        self.app = app_context
        self.window_service = window_service
        self.post_message = post_message_func

    def get_project_path(self) -> str:
        """
        Returns the file path of the current Mendix project root directory.
        This is needed to run git commands.
        """
        return self.app.Root.DirectoryPath


class ICommandHandler(ABC):
    """
    Defines the contract for all command handlers. Each handler is responsible
    for a single command type from the frontend.
    """
    @property
    @abstractmethod
    def command_type(self) -> str:
        """The command type string this handler responds to (e.g., "GET_GIT_LOG")."""
        pass

    @abstractmethod
    def execute(self, payload: Dict) -> Any:
        """Executes the business logic for the command and returns the result."""
        pass

# ===================================================================
# 2. COMMAND HANDLER IMPLEMENTATIONS
# ===================================================================


class EchoCommandHandler(ICommandHandler):
    """Handles the 'ECHO' command for connectivity testing."""
    command_type = "ECHO"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        self._mendix_env.post_message(
            "backend:info", f"Received {self.command_type} command with payload: {payload}")
        return {"echo_response": payload}


class EditorCommandHandler(ICommandHandler):
    """Handles the 'OPEN_EDITOR' command to open Mendix editors."""
    command_type = "OPEN_EDITOR"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        # (Implementation from your reference code)
        module_name = payload.get("moduleName")
        entity_name = payload.get("entityName")
        if not module_name or not entity_name:
            raise ValueError(
                "Payload must contain 'moduleName' and 'entityName'.")
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

# --- START: New Git Log Functionality ---


# --- START: Paginated Git Log Function ---
def get_git_notes_log_paginated(repo_path: str, page_size: int, skip_count: int) -> (list, bool):
    """
    Runs git log with pagination and returns commits and a flag indicating if more commits exist.
    The output is formatted for robust parsing.
    """
    if not os.path.isdir(repo_path) or not os.path.isdir(os.path.join(repo_path, '.git')):
        raise FileNotFoundError(
            f"'{repo_path}' is not a valid Git repository.")

    # Request one more than page_size to check if there are more pages
    # %H: full hash, %an: author name, %ai: author date (ISO), %P: parent hashes,
    # %d: decorations (refs), %s: subject, %b: body, %N: notes
    # --- FIX: Added a custom separator and the %N placeholder for notes ---
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
        "git", "log",
        # Keep --show-notes to specify WHICH notes ref to use for the %N placeholder
        "--show-notes=mx_metadata",
        "--decorate=full",
        f"--pretty=format:{log_format}",
        f"--max-count={page_size + 1}",
        f"--skip={skip_count}"
    ]
    result = execute_silent(command, repo_path)

    all_fetched_commits = parse_git_log(result.stdout)

    has_more = len(all_fetched_commits) > page_size
    commits_for_page = all_fetched_commits[:page_size]

    return commits_for_page, has_more
# --- END: Paginated Git Log Function ---


def parse_git_log(log_output: str) -> list:
    """
    Parses the raw output from 'git log' with a custom format into a structured list.
    Handles multi-line messages, parents, refs (branches/tags), and notes.
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

        if notes_separator in block:
            main_part, notes_part = block.split(notes_separator, 1)
            # --- FIX: Robustly handle commits with no notes content ---
            notes_content = notes_part.strip()
            if notes_content:
                try:
                    commit_data["mx_metadata"] = json.loads(notes_content)
                except json.JSONDecodeError:
                    commit_data["mx_metadata"] = {"error": "JSONDecodeError", "raw": notes_content}
        else:
            main_part = block

        lines = main_part.strip().split('\n')
        message_lines, is_message_section = [], False

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
            elif not line.strip() and not is_message_section:
                is_message_section = True
                commit_data["message"] = "\n".join(lines).strip()
                break

        commits.append(commit_data)
    return commits


def parse_git_log(log_output: str) -> list:
    """
    Parses the raw output from 'git log' with a custom format into a structured list.
    Handles multi-line messages, parents, refs (branches/tags), and notes.
    """
    commits = []
    if not log_output.strip():
        return []

    # Split output into individual commit blocks. The first block might not have the leading newline.
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

        # Separate the main commit data from the notes
        if notes_separator in block:
            main_part, notes_part = block.split(notes_separator, 1)
            try:
                commit_data["mx_metadata"] = json.loads(notes_part.strip())
            except json.JSONDecodeError:
                commit_data["mx_metadata"] = {"error": "JSONDecodeError", "raw": notes_part.strip()}
        else:
            main_part = block

        lines = main_part.strip().split('\n')
        message_lines, is_message_section = [], False

        # Parse the structured part of the commit
        commit_data["sha"] = lines.pop(0).replace("commit ", "").strip()

        # Use a while loop to safely consume header lines
        while lines:
            line = lines.pop(0)
            if line.startswith("Author:"):
                commit_data["author"] = line.split(":", 1)[1].strip()
            elif line.startswith("Date:"):
                commit_data["date"] = line.split(":", 1)[1].strip()
            elif line.startswith("Parents:"):
                # A merge commit will have more than one parent hash
                parents_str = line.split(":", 1)[1].strip()
                if parents_str:
                    commit_data["parents"] = parents_str.split()
            elif line.startswith("Refs:"):
                # Refs are typically in parentheses, e.g., " (HEAD -> main, tag: v1.0, origin/main)"
                refs_str = line.split(":", 1)[1].strip()
                if refs_str.startswith("(") and refs_str.endswith(")"):
                    refs_str = refs_str[1:-1]  # Remove parentheses
                    commit_data["refs"] = [r.strip() for r in refs_str.split(",")]
            elif not line.strip() and not is_message_section:
                # The first blank line signals the start of the message
                is_message_section = True
                # The rest of the lines are the message
                commit_data["message"] = "\n".join(lines).strip()
                break # Exit header parsing

        commits.append(commit_data)
    return commits


def parse_git_log(log_output: str) -> list:
    """Parses the raw output from 'git log --show-notes' into a structured list."""
    commits = []
    if not log_output.strip():
        return []
    commit_blocks = log_output.strip().split("\ncommit ")
    if commit_blocks and not commit_blocks[0].startswith("commit "):
        commit_blocks[0] = "commit " + commit_blocks[0]

    for block in commit_blocks:
        commit_data = {"sha": None, "author": None,
                       "date": None, "message": None, "mx_metadata": None}
        notes_separator = "\n\nNotes (mx_metadata):\n"
        if notes_separator in block:
            main_part, notes_part = block.split(notes_separator, 1)
            try:
                commit_data["mx_metadata"] = json.loads(notes_part.strip())
            except json.JSONDecodeError:
                commit_data["mx_metadata"] = {
                    "error": "JSONDecodeError", "raw": notes_part.strip()}
        else:
            main_part = block
        lines = main_part.strip().split('\n')
        commit_data["sha"] = lines[0].replace("commit ", "").split()[0]
        message_lines, is_message_section = [], False
        for line in lines[1:]:
            if line.startswith("Author:"):
                commit_data["author"] = line.split(":", 1)[1].strip()
            elif line.startswith("Date:"):
                commit_data["date"] = line.split(":", 1)[1].strip()
            elif not line.strip() and not is_message_section:
                is_message_section = True
            elif is_message_section:
                message_lines.append(line.strip())
        commit_data["message"] = "\n".join(message_lines)
        commits.append(commit_data)
    return commits


# --- START: Updated GitLogCommandHandler with Pagination Logic ---
class GitLogCommandHandler(ICommandHandler):
    """
    Handles the 'GET_GIT_LOG' command requested by the frontend.
    It fetches a paginated list of the git commit history.
    """
    command_type = "GET_GIT_LOG"
    DEFAULT_PAGE_SIZE = 20

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> dict:
        """
        Executes the logic to get and parse a page of the git log.
        Payload can contain 'page' and 'pageSize'.
        """
        page = payload.get("page", 1)
        page_size = payload.get("pageSize", self.DEFAULT_PAGE_SIZE)
        skip_count = (page - 1) * page_size

        self._mendix_env.post_message(
            "backend:info", f"Executing GET_GIT_LOG command for page {page}.")
        repo_path = self._mendix_env.get_project_path()

        # Call the new paginated function
        commits, has_more = get_git_notes_log_paginated(
            repo_path, page_size, skip_count)

        self._mendix_env.post_message(
            "backend:info", f"Found {len(commits)} commits for page {page}. Has more: {has_more}")

        return {"commits": commits, "hasMore": has_more}

# --- END: Updated GitLogCommandHandler with Pagination Logic ---
# --- END: New Git Log Functionality ---
# --- START: New Git Helper Functions (to be added near other git functions) ---


def run_git_command(repo_path: str, command: list) -> str:
    """A generic helper to run a git command and return its stdout."""
    if not os.path.isdir(repo_path):
        # Don't check for .git here, as some commands like 'init' run without it
        raise FileNotFoundError(f"Project path '{repo_path}' does not exist.")
    result = execute_silent(
        ["git"] + command, repo_path
    )
    return result.stdout.strip()


def get_git_status_info(repo_path: str) -> dict:
    """
    Gathers comprehensive status information about the Git repository.
    Returns a dictionary with repo status, branches, and remotes.
    """
    is_repo = os.path.isdir(os.path.join(repo_path, '.git'))
    if not is_repo:
        return {"isRepo": False}

    try:
        # Get current branch
        current_branch = run_git_command(
            repo_path, ["branch", "--show-current"])

        # Get all local branches
        branches_output = run_git_command(repo_path, ["branch"])
        all_branches = [b.strip().lstrip('* ')
                        for b in branches_output.split('\n')]

        # Get remotes
        remotes = []
        remotes_output = run_git_command(repo_path, ["remote", "-v"])
        if remotes_output:
            remote_lines = remotes_output.split('\n')
            # Use a dict to group fetch/push URLs by remote name
            remote_map = {}
            for line in remote_lines:
                name, url, _ = re.split(r'\s+', line, 2)
                if name not in remote_map:
                    remote_map[name] = url
            remotes = [{"name": name, "url": url}
                       for name, url in remote_map.items()]

        return {
            "isRepo": True,
            "currentBranch": current_branch,
            "allBranches": all_branches,
            "remotes": remotes
        }
    except Exception as e:
        # If any git command fails in a supposed repo, return a specific error state
        return {"isRepo": True, "error": str(e)}


def initialize_and_commit(repo_path: str, message: str) -> dict:
    """
    Initializes a git repository, adds all files, commits, and adds Mendix metadata note.
    """
    run_git_command(repo_path, ["init"])
    run_git_command(repo_path, ["add", "."])
    run_git_command(repo_path, ["commit", "-m", message])

    # Get the SHA of the new commit
    commit_sha = run_git_command(repo_path, ["rev-parse", "HEAD"])

    # Mendix metadata note, as per the example
    mx_metadata_note = '{"BranchName":"","ModelerVersion":"10.24.4.77222","ModelChanges":[],"RelatedStories":[],"SolutionVersion":"","MPRFormatVersion":"Version2","HasModelerVersion":true}'

    run_git_command(repo_path, [
                    "notes", "--ref=mx_metadata", "add", "-m", mx_metadata_note, commit_sha])

    return {"status": "success", "commitSha": commit_sha}

# --- END: New Git Helper Functions ---


# --- START: New Command Handler Implementations (to be added in section 2) ---

class GetGitStatusCommandHandler(ICommandHandler):
    """Handles getting the overall status of the git repository."""
    command_type = "GET_GIT_STATUS"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        repo_path = self._mendix_env.get_project_path()
        return get_git_status_info(repo_path)


class GitSwitchBranchCommandHandler(ICommandHandler):
    """Handles switching the current git branch."""
    command_type = "GIT_SWITCH_BRANCH"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        branch_name = payload.get("branchName")
        if not branch_name:
            raise ValueError("Payload must contain 'branchName'.")
        repo_path = self._mendix_env.get_project_path()
        run_git_command(repo_path, ["checkout", branch_name])
        return {"status": "success", "switchedTo": branch_name}


class GitInitCommitCommandHandler(ICommandHandler):
    """Handles initializing a repo and making the first commit."""
    command_type = "GIT_INIT_COMMIT"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        message = payload.get("message")
        if not message:
            raise ValueError(
                "Payload must contain a 'message' for the initial commit.")
        repo_path = self._mendix_env.get_project_path()
        return initialize_and_commit(repo_path, message)

class GitAddRemoteCommandHandler(ICommandHandler):
    """Handles adding a new git remote."""
    command_type = "GIT_ADD_REMOTE"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        name = payload.get("name")
        url = payload.get("url")
        if not name or not url:
            raise ValueError("Payload must contain 'name' and 'url'.")
        repo_path = self._mendix_env.get_project_path()
        run_git_command(repo_path, ["remote", "add", name, url])
        return {"status": "success", "name": name, "url": url}


# --- START: New Command Handlers for Remote Management and Push ---

class GitDeleteRemoteCommandHandler(ICommandHandler):
    """Handles deleting a git remote."""
    command_type = "GIT_DELETE_REMOTE"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        remote_name = payload.get("remoteName")
        if not remote_name:
            raise ValueError("Payload must contain 'remoteName'.")
        repo_path = self._mendix_env.get_project_path()
        run_git_command(repo_path, ["remote", "rm", remote_name])
        return {"status": "success", "removed": remote_name}

class GitPushCommandHandler(ICommandHandler):
    """Handles pushing to a specified remote."""
    command_type = "GIT_PUSH"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        remote_name = payload.get("remoteName")
        branch_name = payload.get("branchName")
        if not remote_name or not branch_name:
            raise ValueError("Payload must contain 'remoteName' and 'branchName'.")

        repo_path = self._mendix_env.get_project_path()
        try:
            # Use execute_silent directly to capture stderr on failure
            command = ["git", "push", remote_name, branch_name]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=repo_path,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                timeout=120  # Increased timeout for network operations
            )
            if result.returncode != 0:
                # Git often prints errors to stderr
                error_message = result.stderr.strip() if result.stderr else result.stdout.strip()
                raise Exception(f"Push failed: {error_message}")
            
            return {"status": "success", "output": result.stdout.strip()}

        except subprocess.CalledProcessError as e:
            # This might not be hit if check=False, but good practice
            raise Exception(f"Push failed with exit code {e.returncode}: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise Exception("Git push command timed out after 120 seconds.")
        except Exception as e:
            # Re-raise other exceptions with more context
            raise Exception(f"An unexpected error occurred during git push: {e}")


# --- END: New Command Handlers for Remote Management and Push ---

class GitSetRemoteUrlCommandHandler(ICommandHandler):
    """Handles setting the URL for a git remote."""
    command_type = "GIT_SET_REMOTE_URL"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def execute(self, payload: Dict) -> Dict:
        remote_name = payload.get("remoteName")
        url = payload.get("url")
        if not remote_name or not url:
            raise ValueError("Payload must contain 'remoteName' and 'url'.")
        repo_path = self._mendix_env.get_project_path()
        run_git_command(repo_path, ["remote", "set-url", remote_name, url])
        return {"status": "success", "remote": remote_name, "newUrl": url}

# --- END: New Command Handler Implementations ---

# ===================================================================
# 3. APPLICATION CONTROLLER / DISPATCHER
# ===================================================================


class AppController:
    """
    Routes incoming frontend commands to the appropriate ICommandHandler.
    This class is the central point of control for the backend logic.
    """

    def __init__(self, handlers: Iterable[ICommandHandler], mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        self._command_handlers = {h.command_type: h.execute for h in handlers}
        self._mendix_env.post_message(
            "backend:info", f"Controller initialized with handlers for: {list(self._command_handlers.keys())}")

    def dispatch(self, request: Dict) -> Dict:
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
            return self._create_error_response(error_message, correlation_id)

    def _create_success_response(self, data: Any, correlation_id: str) -> Dict:
        return {"status": "success", "data": data, "correlationId": correlation_id}

    def _create_error_response(self, message: str, correlation_id: str) -> Dict:
        return {"status": "error", "message": message, "correlationId": correlation_id}

# ===================================================================
# 4. IOC CONTAINER CONFIGURATION
# ===================================================================


class Container(containers.DeclarativeContainer):
    """
    The application's Inversion of Control (IoC) container.
    It is responsible for creating and wiring all the application components.
    """
    config = providers.Configuration()

    # Singleton service for Mendix environment access
    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        window_service=config.window_service,
        post_message_func=config.post_message_func,
    )

    # Use providers.List to aggregate all command handlers.
    # This makes the system pluggable; just add a new handler here.
    command_handlers = providers.List(
        # ... existing handlers
        providers.Singleton(GitLogCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GetGitStatusCommandHandler, mendix_env=mendix_env),
        providers.Singleton(GitSwitchBranchCommandHandler,
                            mendix_env=mendix_env),
        providers.Singleton(GitSetRemoteUrlCommandHandler,
                            mendix_env=mendix_env),
        providers.Singleton(GitInitCommitCommandHandler,
                            mendix_env=mendix_env),
        providers.Singleton(GitAddRemoteCommandHandler,
                            mendix_env=mendix_env),
        # --- START: Add these two new handlers ---
        providers.Singleton(GitDeleteRemoteCommandHandler,
                            mendix_env=mendix_env),
        providers.Singleton(GitPushCommandHandler,
                            mendix_env=mendix_env),
        # --- END: Add these two new handlers ---
    )

    # The main controller, injected with the list of all available handlers
    app_controller = providers.Singleton(
        AppController,
        handlers=command_handlers,
        mendix_env=mendix_env,
    )

# ===================================================================
# 5. APPLICATION ENTRYPOINT AND WIRING
# ===================================================================

# These variables are provided by the Mendix Studio Pro script environment
# They are used here to initialize the IoC container.
# currentApp, dockingWindowService, PostMessage


def onMessage(e: Any):
    """This function is the entry point called by Mendix Studio Pro for messages from the UI."""
    if e.Message != "frontend:message":
        return

    controller = container.app_controller()
    request_object = None
    try:
        # Deserialize the incoming request from the frontend
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)

        # Dispatch the request and get a response
        response = controller.dispatch(request_object)

        # Send the response back to the frontend
        PostMessage("backend:response", json.dumps(response))

    except Exception as ex:
        # Gracefully handle any fatal errors during dispatch
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
        "post_message_func": PostMessage
    })
    # This wires the providers to the actual instances for dependency injection
    # container.wire(modules=[__name__]) # this script is exe by eval, so we can not do like this
    return container


# --- Application Start ---
PostMessage("backend:clear", '')
container = initialize_app()
PostMessage("backend:info", "Backend Python script initialized successfully.")
