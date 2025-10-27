# region FRAMEWORK CODE
import json
import os
import sys
import glob
import re
import traceback
from typing import Any, Dict, Callable, Iterable, Optional
from abc import ABC, abstractmethod
from datetime import datetime

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
def info(e):
    PostMessage("backend:info", f'{e}')


_dir = dir


def dir(e):
    PostMessage("backend:info", f'{_dir(e)}')


def error(e):
    PostMessage("backend:error", f'{e}')

def print(e):
    PostMessage("backend:info", e)

class MendixEnvironmentService:
    """Abstracts the Mendix host environment global variables."""
    def __init__(self, app_context, window_service, post_message_func: Callable):
        self.app = app_context
        self.window_service = window_service
        self.post_message = post_message_func
        # Assuming configurationService is a global available in the Mendix environment
        self._config = configurationService.Configuration

    def get_project_path(self) -> str:
        return self.app.Root.DirectoryPath

    def get_mendix_version(self) -> str:
        """Get current Mendix version from configuration."""
        try:
            return f"{self._config.MendixVersion}.{self._config.BuildTag}"
        except:
            return "Unknown"

    def get_current_language(self) -> str:
        """Get the current language of the Studio Pro IDE."""
        try:
            # Example: 'en-US', 'nl-NL', 'zh-CN'
            return self._config.CurrentLanguage.Name
        except:
            return "en-US" # Default to English if not found
        
from abc import ABC, abstractmethod
from typing import Any, Dict, Callable, Iterable, Optional, Protocol, List
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
    """Abstraction for sending messages to the frontend."""
    def send(self, message: Dict): ...
    def broadcast(self, channel: str, data: Any): ...


class IJobContext(Protocol):
    """Context object provided to a running job handler."""
    job_id: str
    def report_progress(self, progress: ProgressUpdate): ...


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

class MendixMessageHub:
    """Low-level implementation of IMessageHub for Mendix."""

    def __init__(self, post_message_func):
        self._post_message = post_message_func

    def send(self, message: Dict):
        self._post_message("backend:response", json.dumps(message))

    def broadcast(self, channel: str, data: Any):
        self.send({"type": "EVENT_BROADCAST", "channel": channel, "data": data})


class AppController:
    """Routes incoming messages to registered handlers."""

    def __init__(self, rpc_handlers: List[IRpcHandler], job_handlers: List[IJobHandler],session_handlers: List[ISessionHandler], message_hub: IMessageHub):
        self._rpc = {h.command_type: h for h in rpc_handlers}
        self._jobs = {h.command_type: h for h in job_handlers}
        self._hub = message_hub
        print(f"Controller initialized. RPCs: {list(self._rpc.keys())}, Jobs: {list(self._jobs.keys())}")

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
        if not handler:
            raise ValueError(f"No RPC handler for '{request['method']}'")
        result = handler.execute(request.get("params"))
        self._hub.send({"type": "RPC_SUCCESS", "reqId": request["reqId"], "data": result})

    def _handle_job_start(self, request):
        handler = self._jobs.get(request["method"])
        if not handler:
            raise ValueError(f"No Job handler for '{request['method']}'")

        import uuid
        import threading
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
                result = handler.run(request.get("params"), context)
                self._hub.send({"type": "JOB_SUCCESS", "jobId": job_id, "data": result})
            except Exception as e:
                self._hub.send({"type": "JOB_ERROR", "jobId": job_id, "message": str(e)})

        thread = threading.Thread(target=job_runner, daemon=True)
        thread.start()
        self._hub.send({"type": "JOB_STARTED", "reqId": request["reqId"], "jobId": job_id})


# endregion

# region BUSINESS LOGIC CODE
# ===================================================================
# ===============     BUSINESS LOGIC CODE     =======================
# ===================================================================
# This section contains your feature-specific command handlers.
# To add a new feature, create a new class implementing ICommandHandler
# or IAsyncCommandHandler, and register it in the Container below.
# -------------------------------------------------------------------
from pathlib import Path

def sanitize_path_prefix_pathlib(file_path: str, sensitive_prefix: str = None, replacement: str = "~") -> str:
    """
    使用 pathlib 检查路径是否以敏感前缀开始，并进行脱敏。
    默认脱敏用户的 HOME 目录。
    """
    try:
        # 1. 确保敏感前缀是 Path 对象，并进行绝对路径规范化
        if sensitive_prefix is None:
            # 默认使用用户主目录作为敏感前缀
            prefix_path = Path.home().resolve()
        else:
            prefix_path = Path(sensitive_prefix).resolve()
            
        # 2. 规范化输入路径
        input_path = Path(file_path).resolve()

        # 3. 检查输入路径是否以敏感前缀开始
        if input_path.is_relative_to(prefix_path):
            # is_relative_to() 是 Python 3.9+ 的方法，判断路径是否在另一个路径下。
            
            # 计算剩余部分（即去掉前缀后的路径）
            try:
                # relative_to 会返回去掉前缀后的路径对象
                relative_part = input_path.relative_to(prefix_path)
            except ValueError:
                # 如果路径完全等于前缀，relative_to 会抛出 ValueError，此时相对部分为空
                relative_part = Path("")

            # 4. 组合脱敏后的路径
            # Windows/Linux 都会正确处理路径分隔符
            return f"{replacement}{os.sep}{relative_part}"
        
        # 如果不是敏感路径，返回原路径
        return file_path
        
    except Exception as e:
        # 如果路径无效，返回原路径
        # print(f"Error processing path: {e}")
        return file_path
    
class LogExtractor:
    """Core log extraction functionality."""

    def __init__(self, mendix_env: MendixEnvironmentService):
        self.mendix_env = mendix_env

    def get_appdata_path(self) -> str:
        """Get Windows AppData Local path."""
        return os.environ.get('LOCALAPPDATA', '')

    def get_mendix_log_path(self, version: str) -> str:
        """Get Mendix log directory path for specific version."""
        appdata = self.get_appdata_path()
        if not appdata:
            return ""
        return os.path.join(appdata, "Mendix", "log", version)

    def get_studio_pro_install_path(self, version: str) -> str:
        """Get Studio Pro installation path."""
        program_files = os.environ.get('ProgramFiles', '')
        if not program_files:
            return ""
        return os.path.join(program_files, "Mendix", version, "modeler")

    def read_log_file(self, file_path: str, limit: int = 100, offset: int = 0) -> dict:
        """Read a specified range of lines from a log file, from the end."""
        try:
            if not os.path.exists(file_path):
                return {"lines": [], "totalLines": 0, "limit": limit, "offset": offset, "error": "File not found"}

            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            
            # Calculate slicing indices from the end of the file
            start_index = max(0, total_lines - offset - limit)
            end_index = max(0, total_lines - offset)

            return {
                "lines": lines[start_index:end_index],
                "totalLines": total_lines,
                "limit": limit,
                "offset": offset,
            }
        except Exception as e:
            return {"lines": [f"Error reading log file: {str(e)}"], "totalLines": 0, "limit": limit, "offset": offset, "error": str(e)}

    def extract_studio_pro_logs(self, version: str, limit: int = 100) -> dict:
        """Extract Studio Pro logs with line limit."""
        log_path = self.get_mendix_log_path(version)
        log_file = os.path.join(log_path, "log.txt")
        log_data = self.read_log_file(log_file, limit=limit)

        return {
            "version": version,
            "logPath": log_file,
            "exists": os.path.exists(log_file),
            "lastModified": datetime.fromtimestamp(os.path.getmtime(log_file)).isoformat() if os.path.exists(log_file) else None,
            **log_data
        }

    def extract_git_logs(self, version: str, limit: int = 100) -> dict:
        """Extract Git logs with line limit."""
        log_path = self.get_mendix_log_path(version)
        git_log_file = os.path.join(log_path, "git", "git.log.txt")
        log_data = self.read_log_file(git_log_file, limit=limit)

        return {
            "version": version,
            "logPath": git_log_file,
            "exists": os.path.exists(git_log_file),
            "lastModified": datetime.fromtimestamp(os.path.getmtime(git_log_file)).isoformat() if os.path.exists(git_log_file) else None,
            **log_data
        }
    def extract_modules_info(self) -> list:
        """Extract module information from current project."""
        try:
            modules = []
            for module in currentApp.Root.GetModules():
                module_info = {
                    "id": module.AppStorePackageId,
                    "version": module.AppStoreVersion,
                    "name": module.Name,
                    "type": 'FromAppStore' if module.FromAppStore else "NotFromAppStore"
                }

                modules.append(module_info)

            return modules
        except Exception as e:
            return [{"error": f"Failed to extract modules: {str(e)}"}]

    def extract_jar_dependencies(self) -> list:
        """Extract JAR dependencies from project."""
        try:
            project_path = self.mendix_env.get_project_path()
            userlib_path = os.path.join(project_path, "userlib")

            if not os.path.exists(userlib_path):
                return []

            jars = []
            for jar_file in glob.glob(os.path.join(userlib_path, "*.jar")):
                file_stat = os.stat(jar_file)
                jars.append({
                    "name": os.path.basename(jar_file),
                    "path": jar_file,
                    "size": file_stat.st_size,
                    "lastModified": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                })

            return jars
        except Exception as e:
            return [{"error": f"Failed to extract JAR dependencies: {str(e)}"}]

    def extract_frontend_components(self) -> list:
        """Extract frontend components and widgets, distinguishing their types."""
        try:
            project_path = self.mendix_env.get_project_path()
            components = []

            # Extract Widgets (.mpk files)
            widgets_path = os.path.join(project_path, "widgets")
            if os.path.exists(widgets_path):
                for widget_file in glob.glob(os.path.join(widgets_path, "*.mpk")):
                    file_stat = os.stat(widget_file)
                    components.append({
                        "name": os.path.basename(widget_file),
                        "path": widget_file,
                        "size": file_stat.st_size,
                        "lastModified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                        "type": "Widget"
                    })

            # Extract JavaScript Actions (.js files)
            js_source_path = os.path.join(project_path, "javascriptsource")
            if os.path.exists(js_source_path):
                # The glob pattern correctly finds JS actions inside module-specific action folders
                for item_full_path in glob.glob(os.path.join(js_source_path, "*", "actions", "*.js")):
                    if os.path.isfile(item_full_path):
                        file_stat = os.stat(item_full_path)
                        components.append({
                            "name": os.path.basename(item_full_path),
                            "path": item_full_path,
                            "type": "JavaScript Action",
                            "size": file_stat.st_size,
                            "lastModified": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                        })

            return components
        except Exception as e:
            return [{"error": f"Failed to extract frontend components: {str(e)}"}]

    def format_for_forum(self, data: dict) -> str:
        """Format extracted data for comprehensive forum posting."""
        output = []
        output.append("# Mendix Project Diagnostic Information")
        output.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("")

        # Version info
        if "version" in data:
            output.append("## Mendix Version")
            output.append(f"- **Version:** {data['version']}")
            output.append("")

        # Project Overview

        output.append("## Project Overview")
        output.append(f"- **Total Modules:** {len(data.get('modules', []))}")
        output.append(f"- **JAR Dependencies:** {len(data.get('jarDependencies', []))}")
        output.append(f"- **Frontend Components:** {len(data.get('frontendComponents', []))}")
        output.append("")

        # Modules
        if "modules" in data and data["modules"]:
            output.append("## Modules")
            for module in data["modules"]:
                output.append(f"### {module['name']}")
                output.append(f"- **Type:** {module.get('type', 'N/A')}")
                output.append(f"- **Version:** {module.get('version', 'N/A')}")
                output.append(f"- **Guid:** {module.get('id','N/A')}")
                output.append("")

        # Dependencies
        if "jarDependencies" in data and data["jarDependencies"]:
            output.append("## JAR Dependencies")
            output.append(f"- **Total JARs:** {len(data['jarDependencies'])}")
            for jar in data["jarDependencies"]:
                size_kb = jar.get('size', 0) / 1024
                output.append(f"- {jar['name']} ({size_kb:.1f} KB)")
            output.append("")

        # Frontend Components
        if "frontendComponents" in data and data["frontendComponents"]:
            output.append("## Frontend Components")
            output.append(f"- **Total Components:** {len(data['frontendComponents'])}")
            for component in data["frontendComponents"]:
                component_type = component.get('type', 'Widget')
                if component.get('size'):
                    size_kb = component['size'] / 1024
                    output.append(f"- {component['name']} ({component_type}, {size_kb:.1f} KB)")
                else:
                    output.append(f"- {component['name']} ({component_type})")
            output.append("")

        # Studio Pro Log summaries
        if "studioProLogs" in data and data["studioProLogs"]:
            logs = data["studioProLogs"]
            output.append("## Studio Pro Logs")
            output.append(f"- **Log file exists:** {logs.get('exists', False)}")
            output.append(f"- **Log file path:** {sanitize_path_prefix_pathlib(logs.get('logPath', 'Unknown'))}")
            output.append(f"- **Last modified:** {logs.get('lastModified', 'Unknown')}")
            output.append(f"- **Total lines:** {len(logs.get('lines', []))}")
            if logs.get("lines"):
                output.append("### Recent Log Entries:")
                output.append("```")
                for line in logs["lines"]:
                    output.append(line.strip())
                output.append("```")
            output.append("")

        # Git logs
        if "gitLogs" in data and data["gitLogs"]:
            git_logs = data["gitLogs"]
            output.append("## Git Logs")
            output.append(f"- **Git log file exists:** {git_logs.get('exists', False)}")
            output.append(f"- **Log file path:** {sanitize_path_prefix_pathlib(git_logs.get('logPath', 'Unknown'))}")
            output.append(f"- **Last modified:** {git_logs.get('lastModified', 'Unknown')}")
            output.append(f"- **Total lines:** {len(git_logs.get('lines', []))}")
            if git_logs.get("lines"):
                output.append("### Recent Git Log Entries:")
                output.append("```")
                for line in git_logs["lines"]:
                    output.append(line.strip())
                output.append("```")
            output.append("")

        # System info
        output.append("## System Information")
        output.append(f"- **Operating System:** {os.name}")
        output.append(f"- **Python Version:** {sys.version}")
        output.append("")

        return "\n".join(output)


# ===================================================================
# ===================   RPC HANDLERS   ==============================
# ===================================================================

import time
class GetEnvironmentRpc(IRpcHandler):
    """Get current Mendix version, project path, and IDE language."""
    command_type = "app:getEnvironment"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self.mendix_env = mendix_env

    def execute(self, payload: dict) -> Any:
        return {
            "version": self.mendix_env.get_mendix_version(),
            "projectPath": self.mendix_env.get_project_path(),
            "language": self.mendix_env.get_current_language()
        }
class GetVersionRpc(IRpcHandler):
    """Get current Mendix version."""
    command_type = "logs:getVersion"

    def __init__(self, mendix_env: MendixEnvironmentService):
        self.mendix_env = mendix_env

    def execute(self, payload: dict) -> Any:
        return {
            "version": self.mendix_env.get_mendix_version(),
            "projectPath": self.mendix_env.get_project_path()
        }

class GetStudioProLogsRpc(IRpcHandler):
    """Get Studio Pro logs."""
    command_type = "logs:getStudioProLogs"

    def __init__(self, log_extractor: LogExtractor, mendix_env: MendixEnvironmentService):
        self.log_extractor = log_extractor
        self.mendix_env = mendix_env

    def execute(self, payload: dict) -> Any:
        version = self.mendix_env.get_mendix_version()
        limit = payload.get('limit', 100)
        return self.log_extractor.extract_studio_pro_logs(version, limit=limit)

class GetGitLogsRpc(IRpcHandler):
    """Get Git logs."""
    command_type = "logs:getGitLogs"

    def __init__(self, log_extractor: LogExtractor, mendix_env: MendixEnvironmentService):
        self.log_extractor = log_extractor
        self.mendix_env = mendix_env

    def execute(self, payload: dict) -> Any:
        version = self.mendix_env.get_mendix_version()
        limit = payload.get('limit', 100)
        return self.log_extractor.extract_git_logs(version, limit=limit)
    
class GetModulesInfoRpc(IRpcHandler):
    """Get modules information."""
    command_type = "logs:getModulesInfo"

    def __init__(self, log_extractor: LogExtractor):
        self.log_extractor = log_extractor

    def execute(self, payload: dict) -> Any:
        return self.log_extractor.extract_modules_info()

class GetJarDependenciesRpc(IRpcHandler):
    """Get JAR dependencies."""
    command_type = "logs:getJarDependencies"

    def __init__(self, log_extractor: LogExtractor):
        self.log_extractor = log_extractor

    def execute(self, payload: dict) -> Any:
        return self.log_extractor.extract_jar_dependencies()

class GetFrontendComponentsRpc(IRpcHandler):
    """Get frontend components."""
    command_type = "logs:getFrontendComponents"

    def __init__(self, log_extractor: LogExtractor):
        self.log_extractor = log_extractor

    def execute(self, payload: dict) -> Any:
        return self.log_extractor.extract_frontend_components()


class GenerateCompleteForumExportRpc(IRpcHandler):
    """Generate complete forum export with all log data."""
    command_type = "logs:generateCompleteForumExport"

    def __init__(self, log_extractor: LogExtractor, mendix_env: MendixEnvironmentService):
        self.log_extractor = log_extractor
        self.mendix_env = mendix_env

    def execute(self, payload: dict) -> Any:
        version = self.mendix_env.get_mendix_version()

        # Extract all log data
        studio_pro_logs = self.log_extractor.extract_studio_pro_logs(version)
        git_logs = self.log_extractor.extract_git_logs(version)
        modules_info = self.log_extractor.extract_modules_info()
        jar_dependencies = self.log_extractor.extract_jar_dependencies()
        frontend_components = self.log_extractor.extract_frontend_components()

        # Combine all data
        all_data = {
            "version": version,
            "studioProLogs": studio_pro_logs,
            "gitLogs": git_logs,
            "modules": modules_info,
            "jarDependencies": jar_dependencies,
            "frontendComponents": frontend_components
        }

        # Format for forum
        formatted_text = self.log_extractor.format_for_forum(all_data)

        return {
            "formattedText": formatted_text,
            "timestamp": datetime.now().isoformat(),
            "data": all_data
        }

class ExtractAllLogsJob(IJobHandler):
    """Extract all logs as a background job."""
    command_type = "logs:extractAll"

    def __init__(self, log_extractor: LogExtractor, mendix_env: MendixEnvironmentService):
        self.log_extractor = log_extractor
        self.mendix_env = mendix_env

    def run(self, payload: dict, context: IJobContext):
        version = self.mendix_env.get_mendix_version()

        context.report_progress(ProgressUpdate(10, "Extracting Studio Pro logs...", "studio_pro"))
        studio_pro_logs = self.log_extractor.extract_studio_pro_logs(version)

        context.report_progress(ProgressUpdate(25, "Extracting Git logs...", "git"))
        git_logs = self.log_extractor.extract_git_logs(version)

        context.report_progress(ProgressUpdate(40, "Extracting modules information...", "modules"))
        modules_info = self.log_extractor.extract_modules_info()

        context.report_progress(ProgressUpdate(60, "Extracting JAR dependencies...", "jars"))
        jar_dependencies = self.log_extractor.extract_jar_dependencies()

        context.report_progress(ProgressUpdate(80, "Extracting frontend components...", "frontend"))
        frontend_components = self.log_extractor.extract_frontend_components()

        context.report_progress(ProgressUpdate(90, "Formatting data...", "formatting"))
        all_data = {
            "version": version,
            "studioProLogs": studio_pro_logs,
            "gitLogs": git_logs,
            "modules": modules_info,
            "jarDependencies": jar_dependencies,
            "frontendComponents": frontend_components
        }

        formatted_forum = self.log_extractor.format_for_forum(all_data)

        context.report_progress(ProgressUpdate(100, "Extraction complete!", "complete"))

        return {
            "data": all_data,
            "forumFormatted": formatted_forum
        }


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

    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        window_service=config.window_service,
        post_message_func=config.post_message_func,
    )

    log_extractor = providers.Singleton(LogExtractor, mendix_env=mendix_env)

    # --- Business Logic Handlers (OCP) ---
    rpc_handlers = providers.List(
        providers.Singleton(GetEnvironmentRpc, mendix_env=mendix_env),
        providers.Singleton(GetVersionRpc, mendix_env=mendix_env),
        providers.Singleton(GetStudioProLogsRpc, log_extractor=log_extractor, mendix_env=mendix_env),
        providers.Singleton(GetGitLogsRpc, log_extractor=log_extractor, mendix_env=mendix_env),
        providers.Singleton(GetModulesInfoRpc, log_extractor=log_extractor),
        providers.Singleton(GetJarDependenciesRpc, log_extractor=log_extractor),
        providers.Singleton(GetFrontendComponentsRpc, log_extractor=log_extractor),
        providers.Singleton(GenerateCompleteForumExportRpc, log_extractor=log_extractor, mendix_env=mendix_env),
    )
    job_handlers = providers.List(
        providers.Singleton(ExtractAllLogsJob, log_extractor=log_extractor, mendix_env=mendix_env),
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
    container.config.from_dict({
        "post_message_func": PostMessage,
        "app_context": currentApp,
        "window_service": dockingWindowService
    })
    return container

# --- Application Start ---
PostMessage("backend:clear", '')
container = initialize_app()
PostMessage("backend:info", "Mendix Log Extractor Plugin initialized successfully.")

# endregion