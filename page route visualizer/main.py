# ==============================================================================
# IMPORTS AND ENVIRONMENT SETUP
# ==============================================================================
from dependency_injector import containers, providers
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import IModelElement, IModelUnit
from Mendix.StudioPro.ExtensionsAPI.Model.Pages import (
    IPage,
)
from System.Text.Json import JsonSerializer
import clr
import sys
import json
import inspect
import traceback
from typing import Any, Callable, Dict, List, Set, Optional
from abc import ABC, abstractmethod


# pythonnet库嵌入C#代码
# .NET References for Mendix Environment
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")


# 运行时环境提供的工具
PostMessage("backend:clear", '')  # 清理IDE控制台日志
# ShowDevTools()  # 打开前端开发者工具
# 运行时环境提供的上下文变量
# currentApp：mendix model
# root：untyped model
# dockingWindowService

# ==============================================================================
# RPC FRAMEWORK (No change)
# ==============================================================================


class IRpcModule:
    pass


class RpcDispatcher:
    def __init__(self, modules: List[IRpcModule]):
        self._methods: Dict[str, Any] = {}
        for module_instance in modules:
            for name, method in inspect.getmembers(module_instance, predicate=inspect.ismethod):
                if not name.startswith('_'):
                    self._methods[name] = method

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method_name = request.get('method')
        request_id = request.get('id')
        if not method_name or method_name not in self._methods:
            return {'jsonrpc': '2.0', 'error': {'message': f"Method '{method_name}' not found."}, 'requestId': request_id}
        try:
            params = request.get('params', {})
            result = self._methods[method_name](**params)
            return {'jsonrpc': '2.0', 'result': result, 'requestId': request_id}
        except Exception as e:
            error_message = f"Error in '{method_name}': {e}\n{traceback.format_exc()}"
            PostMessage("backend:info", error_message)
            return {'jsonrpc': '2.0', 'error': {'message': error_message}, 'requestId': request_id}

# ==============================================================================
# REFACTORED SERVICES (No change)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Mendix Model Service
# ------------------------------------------------------------------------------


class IModelService(ABC):
    @abstractmethod
    def get_element_by_id(self, element_id: str) -> Optional[IModelElement]:
        pass

    @abstractmethod
    def get_units_of_type(self, unit_type: str) -> List[IModelUnit]:
        pass

    @abstractmethod
    def find_element_by_qualified_name(self, qn: str) -> Optional[IModelUnit]:
        pass

    @abstractmethod
    def find_descendants_by_type(self, element: IModelElement, target_type: str) -> List[IModelElement]:
        pass


class MendixModelService(IModelService):
    def __init__(self, root: Any):
        self._root = root

    def get_element_by_id(self, element_id: str) -> Optional[IModelElement]:
        return self._root.GetElementById(element_id)

    def get_units_of_type(self, unit_type: str) -> List[IModelUnit]:
        return self._root.GetUnitsOfType(unit_type)

    def find_element_by_qualified_name(self, qn: str) -> Optional[IModelUnit]:
        parts = qn.split('.')
        if len(parts) != 2:
            return None
        module_name, element_name = parts
        module = next((m for m in self.get_units_of_type(
            'Projects$Module') if m.Name == module_name), None)
        if not module:
            return None
        for unit_type in ['Pages$Page', 'Microflows$Microflow']:
            element = next((p for p in module.GetUnitsOfType(
                unit_type) if p.Name == element_name), None)
            if element:
                return element
        return None

    def find_descendants_by_type(self, element: IModelElement, target_type: str) -> List[IModelElement]:
        found_elements = []
        queue = [element]
        visited = {str(element.ID)}
        while queue:
            current_element = queue.pop(0)
            if current_element.Type == target_type:
                found_elements.append(current_element)
            elements_to_check = []
            if isinstance(current_element, IModelUnit):
                elements_to_check.extend(current_element.GetElements())
            for prop in current_element.GetProperties():
                value = prop.Value
                if isinstance(value, IModelElement):
                    elements_to_check.append(value)
                elif isinstance(value, list):
                    elements_to_check.extend(
                        item for item in value if isinstance(item, IModelElement))
            for el in elements_to_check:
                el_id = str(el.ID)
                if el_id not in visited:
                    visited.add(el_id)
                    queue.append(el)
        return found_elements

# ------------------------------------------------------------------------------
# 2. Graph Builder
# ------------------------------------------------------------------------------


class GraphBuilder:
    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[str, Dict[str, Any]] = {}

    def add_node(self, node_id: str, label: str, group: str, title: Optional[str] = None):
        if node_id not in self._nodes:
            self._nodes[node_id] = {
                "id": node_id, "label": label, "group": group, "title": title or label}

    def add_edge(self, from_id: str, to_id: str, label: str = ""):
        edge_id = f"{from_id}->{to_id}"
        if edge_id not in self._edges:
            self._edges[edge_id] = {
                "id": edge_id, "from": from_id, "to": to_id, "arrows": "to", "label": label}

    def get_graph_data(self) -> Dict[str, Any]:
        return {"nodes": list(self._nodes.values()), "edges": list(self._edges.values())}

# ------------------------------------------------------------------------------
# 3. Navigation Analyzer
# ------------------------------------------------------------------------------


class NavigationAnalyzer:
    def __init__(self, model_service: IModelService):
        self._model_service = model_service
        self._builder: GraphBuilder = None
        self._processed_elements: Set[str] = None

    def analyze(self) -> Dict[str, Any]:
        self._builder = GraphBuilder()
        self._processed_elements = set()
        self._process_security()
        self._process_navigation_document()
        return self._builder.get_graph_data()

    def _process_security(self):
        project_security_list = self._model_service.get_units_of_type(
            'Security$ProjectSecurity')
        if not project_security_list:
            return
        project_security = project_security_list[0]
        for user_role in project_security.GetProperty('userRoles').Value:
            user_role_name = user_role.GetProperty('name').Value
            self._builder.add_node(
                user_role_name, user_role_name, 'userRole', title=f"User Role: {user_role_name}")
            for module_role_qn in user_role.GetProperty('moduleRoles').Value:
                self._builder.add_node(module_role_qn, module_role_qn.split(
                    '.')[-1], 'moduleRole', title=f"Module Role: {module_role_qn}")
                self._builder.add_edge(
                    user_role_name, module_role_qn, "contains")

    def _process_navigation_document(self):
        nav_doc_list = self._model_service.get_units_of_type(
            'Navigation$NavigationDocument')
        if not nav_doc_list:
            return
        nav_doc = nav_doc_list[0]
        profile = nav_doc.GetProperty('profiles').Value[0]
        profile_id = str(profile.ID)
        self._builder.add_node(profile_id, "Navigation Profile", "navigation")
        menu_items = profile.GetProperty(
            'menuItemCollection').Value.GetProperty('items').Value
        for item in menu_items:
            self._process_menu_item(item, profile_id)

    def _process_menu_item(self, item: IModelElement, parent_id: str):
        item_id = str(item.ID)
        captionText_obj = item.GetProperty('caption').Value
        item_caption = captionText_obj.GetProperty(
            'translations').Value[0].GetProperty('text').Value
        self._builder.add_node(item_id, item_caption, "menu")
        self._builder.add_edge(parent_id, item_id)
        action = item.GetProperty('action').Value
        if not action:
            return
        target_element = None
        action_type_map = {'Pages$PageClientAction': (
            'pageSettings', 'page'), 'Pages$MicroflowClientAction': ('microflowSettings', 'microflow')}
        if action.Type in action_type_map:
            settings_prop, qn_prop = action_type_map[action.Type]
            qn = action.GetProperty(
                settings_prop).Value.GetProperty(qn_prop).Value
            if qn:
                target_element = self._model_service.find_element_by_qualified_name(
                    qn)
        if target_element:
            target_id = str(target_element.ID)
            target_type_group = target_element.Type.split('$')[-1].lower()
            self._builder.add_node(
                target_id, target_element.QualifiedName, target_type_group)
            self._builder.add_edge(item_id, target_id)
            if target_element.Type == 'Pages$Page':
                self._process_page(target_element)
            elif target_element.Type == 'Microflows$Microflow':
                self._process_microflow(target_element)
        child_items_prop = item.GetProperty('items')
        if child_items_prop and child_items_prop.Value:
            for child_item in child_items_prop.Value:
                self._process_menu_item(child_item, item_id)

    def _process_page(self, page: IModelUnit):
        page_id = str(page.ID)
        if page_id in self._processed_elements:
            return
        self._processed_elements.add(page_id)
        for role_qn in page.GetProperty('allowedRoles').Value:
            self._builder.add_node(role_qn, role_qn.split(
                '.')[-1], 'moduleRole', title=f"Module Role: {role_qn}")
            self._builder.add_edge(role_qn, page_id, "can open")
        self._process_element_actions(
            page, 'Pages$MicroflowClientAction', 'microflowSettings', 'microflow', self._process_microflow)
        self._process_element_actions(
            page, 'Pages$PageClientAction', 'pageSettings', 'page', self._process_page)

    def _process_microflow(self, microflow: IModelUnit):
        mf_id = str(microflow.ID)
        if mf_id in self._processed_elements:
            return
        self._processed_elements.add(mf_id)
        for role_qn in microflow.GetProperty('allowedModuleRoles').Value:
            self._builder.add_node(role_qn, role_qn.split(
                '.')[-1], 'moduleRole', title=f"Module Role: {role_qn}")
            self._builder.add_edge(role_qn, mf_id, "can execute")
        self._process_element_actions(
            microflow, 'Microflows$MicroflowCall', None, 'microflow', self._process_microflow)
        self._process_element_actions(
            microflow, 'Microflows$ShowPageAction', 'pageSettings', 'page', self._process_page)

    def _process_element_actions(self, element: IModelElement, action_type: str, settings_prop: Optional[str], qn_prop: str, processor_func: Callable):
        actions = self._model_service.find_descendants_by_type(
            element, action_type)
        element_id = str(element.ID)
        for action in actions:
            value_container = action
            if settings_prop:
                value_container = action.GetProperty(settings_prop).Value
            qn = value_container.GetProperty(qn_prop).Value
            if not qn:
                continue
            target_element = self._model_service.find_element_by_qualified_name(
                qn)
            if target_element and str(target_element.ID) != element_id:
                target_id = str(target_element.ID)
                target_type_group = target_element.Type.split('$')[-1].lower()
                self._builder.add_node(target_id, qn, target_type_group)
                self._builder.add_edge(element_id, target_id)
                processor_func(target_element)

# ==============================================================================
# REFACTORED RPC MODULES (No change)
# ==============================================================================


class ModelBrowserRpcModule(IRpcModule):
    def __init__(self, model_service: IModelService):
        self._model_service = model_service
        self._root = model_service._root

    def get_root(self):
        return {"id": str(self._root.Id), "caption": "App", "type": "App"}

    def get_children(self, id: str):
        element = self._model_service.get_element_by_id(id)
        if not element:
            return []
        children = element.GetElement() if isinstance(
            element, IModelUnit) else element.GetProperties()
        return [{"id": str(child.Id), "caption": child.Name if isinstance(child, IModelUnit) else child.Type.split("$")[-1], "type": child.Type} for child in children]


class VisualizationRpcModule(IRpcModule):
    def __init__(self, analyzer: NavigationAnalyzer):
        self._analyzer = analyzer

    def get_navigation_data(self) -> Dict[str, Any]:
        return self._analyzer.analyze()

    def locate(self, node):
        if node['group'] == 'page':
            qName = node['label']
            existing_page = currentApp.ToQualifiedName[IPage](qName).Resolve()
            if existing_page:
                status = dockingWindowService.TryOpenEditor(existing_page, None)
                return {status}
        return {status: False}

# ==============================================================================
# DEPENDENCY INJECTION CONTAINER (No change)
# ==============================================================================


class AppContainer(containers.DeclarativeContainer):
    config = providers.Configuration()
    model_service = providers.Singleton(
        MendixModelService, root=config.mendix_root)
    navigation_analyzer = providers.Factory(
        NavigationAnalyzer, model_service=model_service)
    model_browser_service = providers.Singleton(
        ModelBrowserRpcModule, model_service=model_service)
    visualization_service = providers.Singleton(
        VisualizationRpcModule, analyzer=navigation_analyzer)
    rpc_modules = providers.List(model_browser_service, visualization_service)
    dispatcher = providers.Singleton(RpcDispatcher, modules=rpc_modules)


# ==============================================================================
# COMPOSITION ROOT & EVENT LOOP (** FIX APPLIED HERE **)
# ==============================================================================
container = AppContainer()
container.config.mendix_root.from_value(root)
dispatcher_instance = container.dispatcher()

PostMessage("backend:info", 'server started')

# The onMessage function is the main entry point for handling messages from the frontend.


def onMessage(e: Any):
    """
    接收来自C#的消息
    Args:
        e (Any): The event object containing the message type and data from the frontend.
    Returns:
        None
    """
    if e.Message == "frontend:message":  # 接收来自C#转发的前端消息，前端用window.parent.sendMessage("frontend:message", jsonMessageObj)发送消息
        try:
            # FIX: Use the .NET JsonSerializer to handle the incoming .NET JsonObject (e.Data)
            # This correctly converts the .NET object to a standard JSON string.
            request_string = JsonSerializer.Serialize(e.Data)

            # Now, use Python's json library to parse the string into a Python dictionary.
            request_object = json.loads(request_string)

            if request_object:
                # Dispatch the request (this logic is unchanged and correct)
                response = dispatcher_instance.handle_request(request_object)

                # 发送消息给前端，前端可以用如下代码来接收
                # window.addEventListener('message', (event) => {
                #    if (event.data && event.data.type === 'backendResponse') {
                #        const payload = event.data.data;// payload就是echo的response
                #        // your logic here
                #    }
                # })
                PostMessage("backend:response", json.dumps(response))
        except Exception as ex:
            PostMessage(
                "backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")
