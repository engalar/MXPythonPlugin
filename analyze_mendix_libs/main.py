# --- Base Imports ---
import clr
from System.Text.Json import JsonSerializer
import json
import traceback
from typing import Any, Dict, Callable

# --- Dependency Injection ---
from dependency_injector import containers, providers
from dependency_injector.wiring import inject, Provide

# --- JAR Analysis Imports ---
import os
import re
from collections import defaultdict
import pandas as pd

# pythonnet library setup for embedding C#
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import IDomainModel, IEntity
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule

# Runtime environment provides these globals
# PostMessage, ShowDevTools, currentApp, root, dockingWindowService

# --- Initial Setup ---
PostMessage("backend:clear", '')
ShowDevTools()

# ===================================================================
# 1. JAR CONFLICT ANALYSIS LOGIC (FROM YOUR SCRIPT)
# ===================================================================

def parse_userlib_dir(directory_path: str) -> list:
    """Analyzes a Mendix userlib directory to parse JARs and identify their sources."""
    jar_pattern = re.compile(r'^(.*?)-(\d+(?:\.\d+)*.*?)\.jar$')
    generic_jar_pattern = re.compile(r'^(.*?)_([\d\.]+.*?)\.jar$')
    required_by_pattern = re.compile(r'^(.*\.jar)\.(.*?)\.(RequiredLib|Required\.by.*)$')
    jar_info = {}

    try:
        filenames = os.listdir(directory_path)
    except FileNotFoundError:
        return []

    for filename in filenames:
        if filename.endswith('.jar'):
            lib_name, version = None, None
            match = jar_pattern.match(filename)
            if not match:
                match = generic_jar_pattern.match(filename)
            if match:
                lib_name, version = match.groups()
                lib_name = lib_name.replace('org.apache.commons.', 'commons-')
                lib_name = lib_name.replace('org.apache.httpcomponents.', '')
            
            jar_info[filename] = {
                'library_name': lib_name if lib_name else filename.replace('.jar', ''),
                'version': version if version else 'unknown',
                'source': 'userlib',
                'details': {'filename': filename, 'required_by': set()}
            }

    for filename in filenames:
        if 'Required' in filename:
            match = required_by_pattern.match(filename)
            if match:
                jar_filename, module_name, _ = match.groups()
                if jar_filename in jar_info:
                    jar_info[jar_filename]['details']['required_by'].add(module_name)
    
    dependency_list = []
    for info in jar_info.values():
        required_by_str = ", ".join(sorted(list(info['details']['required_by']))) or "Unknown"
        info['details'] = f"File: {info['details']['filename']} (Required by: {required_by_str})"
        dependency_list.append(info)
        
    return dependency_list

def parse_sbom_file(sbom_path: str) -> list:
    """Parses a CycloneDX SBOM JSON file to extract dependency information."""
    dependency_list = []
    try:
        with open(sbom_path, 'r', encoding='utf-8') as f:
            sbom_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    components = sbom_data.get('components', [])
    for comp in components:
        lib_name = comp.get('name')
        if lib_name:
            dependency_list.append({
                'library_name': lib_name,
                'version': comp.get('version', 'unknown'),
                'source': 'SBOM (vendorlib)',
                'details': f"PURL: {comp.get('purl', 'N/A')}"
            })
    return dependency_list

def analyze_conflicts(dependencies: list) -> dict:
    """Analyzes a combined list of dependencies to find version conflicts."""
    grouped_libs = defaultdict(list)
    for dep in dependencies:
        if dep['version'] != 'unknown':
            grouped_libs[dep['library_name']].append({
                'version': dep['version'],
                'source': dep['source'],
                'details': dep['details']
            })

    conflicts = {lib_name: versions_info for lib_name, versions_info in grouped_libs.items() if len({info['version'] for info in versions_info}) > 1}
    return conflicts


# ===================================================================
# 2. ABSTRACTIONS AND SERVICES (NEW ARCHITECTURE)
# ===================================================================

class MendixEnvironmentService:
    """Abstracts away the Mendix host environment's global variables."""
    def __init__(self, app_context, post_message_func: Callable):
        self.app = app_context
        self.post_message = post_message_func

class JarConflictService:
    """Handles the business logic for analyzing JARs."""
    def __init__(self, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env

    def analyze_project(self, payload: Dict) -> Dict:
        """Runs the full JAR analysis for the current Mendix project."""
        project_path = self._mendix_env.app.Root.DirectoryPath
        self._mendix_env.post_message("backend:info", f"Analyzing project at: {project_path}")

        userlib_path = os.path.join(project_path, 'userlib')
        
        # Check for SBOM in both potential Mendix 9 and 10+ locations
        sbom_path_mx10 = os.path.join(userlib_path, 'vendorlib-sbom.json')
        sbom_path_mx9 = os.path.join(project_path, 'vendorlib', 'vendorlib-sbom.json')
        sbom_path = sbom_path_mx10 if os.path.exists(sbom_path_mx10) else sbom_path_mx9

        userlib_deps = parse_userlib_dir(userlib_path)
        sbom_deps = parse_sbom_file(sbom_path)
        all_dependencies = userlib_deps + sbom_deps

        # Create DataFrame for analysis and reporting
        df = pd.DataFrame(all_dependencies)
        all_deps_list = []
        if not df.empty:
            df = df[['library_name', 'version', 'source', 'details']]
            df = df.sort_values(by=['library_name', 'version']).reset_index(drop=True)
            all_deps_list = df.to_dict('records') # Convert to list of dicts for JSON

        conflict_report = analyze_conflicts(all_dependencies)

        return {
            "dependencies": all_deps_list,
            "conflicts": conflict_report,
            "summary": {
                "userlib_count": len(userlib_deps),
                "sbom_count": len(sbom_deps),
                "total_count": len(all_dependencies),
                "conflict_count": len(conflict_report)
            }
        }


class AppController:
    """Handles routing of commands from the frontend to specific services."""
    def __init__(self, jar_service: JarConflictService, mendix_env: MendixEnvironmentService):
        self._mendix_env = mendix_env
        self._command_handlers: Dict[str, Callable[[Dict], Any]] = {
            "ANALYZE_JARS": jar_service.analyze_project,
        }

    def dispatch(self, request: Dict) -> Dict:
        """Dispatches a request and ensures a consistently formatted response."""
        command_type = request.get("type")
        payload = request.get("payload", {})
        correlation_id = request.get("correlationId")

        handler = self._command_handlers.get(command_type)
        if not handler:
            return self._create_error_response(f"No handler for command: {command_type}", correlation_id)

        try:
            result = handler(payload)
            return self._create_success_response(result, correlation_id)
        except Exception as e:
            error_message = f"Error executing '{command_type}': {e}"
            self._mendix_env.post_message("backend:info", f"{error_message}\n{traceback.format_exc()}")
            return self._create_error_response(error_message, correlation_id, {"traceback": traceback.format_exc()})

    def _create_success_response(self, data: Any, correlation_id: str) -> Dict:
        return {"status": "success", "data": data, "correlationId": correlation_id}

    def _create_error_response(self, message: str, correlation_id: str, data: Any = None) -> Dict:
        return {"status": "error", "message": message, "data": data or {}, "correlationId": correlation_id}


# ===================================================================
# 3. IOC CONTAINER CONFIGURATION
# ===================================================================

class Container(containers.DeclarativeContainer):
    """The IoC container that wires all services together."""
    config = providers.Configuration()

    mendix_env = providers.Singleton(
        MendixEnvironmentService,
        app_context=config.app_context,
        post_message_func=config.post_message_func,
    )

    jar_conflict_service = providers.Singleton(JarConflictService, mendix_env=mendix_env)
    
    app_controller = providers.Singleton(
        AppController,
        jar_service=jar_conflict_service,
        mendix_env=mendix_env,
    )

# ===================================================================
# 4. APPLICATION ENTRYPOINT
# ===================================================================

container = Container()
container.config.from_dict({
    "app_context": currentApp,
    "post_message_func": PostMessage,
})

def onMessage(e: Any):
    """Entry point for all messages from the frontend."""
    controller = container.app_controller()
    if e.Message != "frontend:message":
        return

    try:
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)

        if "correlationId" not in request_object:
            PostMessage("backend:info", f"Msg without correlationId: {request_object}")
            return

        response = controller.dispatch(request_object)
        PostMessage("backend:response", json.dumps(response))

    except Exception as ex:
        PostMessage("backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")
        correlation_id = "unknown"
        try:
            # Attempt to recover correlationId for a proper error response
            request_string = JsonSerializer.Serialize(e.Data)
            request_object = json.loads(request_string)
            correlation_id = request_object.get("correlationId", "unknown")
        except:
            pass
        
        error_response = controller._create_error_response(
            f"A fatal error occurred in the Python backend: {ex}",
            correlation_id,
            {"traceback": traceback.format_exc()}
        )
        PostMessage("backend:response", json.dumps(error_response))