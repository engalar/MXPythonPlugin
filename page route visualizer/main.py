# gh gist edit d4a9cf90c46c4e91cfc16102a1a56579 .\main.py -f main.py

from dependency_injector import containers, providers
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import IModelElement, IModelUnit
from System.Text.Json import JsonSerializer, JsonSerializerOptions
import clr
import sys
import json
import inspect
import traceback
from typing import Any, Callable, Dict, List
PostMessage("backend:clear", '')
# .NET References for Mendix Environment
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# Dependency Injection

# ==============================================================================
# HELPER FUNCTIONS (assumed from boilerplate)
# ==============================================================================
# These helpers are needed for the boilerplate to function.
# We provide standard Python implementations.


def serialize_json_object(e: Any) -> str:
    # This function likely extracts the string data from the Mendix message object 'e'.
    # The exact implementation might vary based on the type of 'e'.
    # We assume 'e.Data' holds the relevant JSON string or dict.
    if isinstance(e.Data, str):
        return e.Data
    return json.dumps(e.Data)


def deserialize_json_string(s: str) -> Dict:
    return json.loads(s)

# ==============================================================================
# RPC FRAMEWORK
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
# RPC MODULES
# ==============================================================================


class ModelBrowserRpcModule(IRpcModule):
    """Original module to browse the model tree."""

    def __init__(self, root: Any):
        self._root = root

    def get_root(self):
        return {"id": str(self._root.Id), "caption": "App", "type": "App"}

    def get_children(self, id: str):
        element = self._root.GetElementById(id)
        if not element:
            return []
        children = element.GetElement() if isinstance(
            element, IModelUnit) else element.GetProperties()
        return [
            {
                "id": str(child.Id),
                "caption": child.Name if isinstance(child, IModelUnit) else child.Type.split("$")[-1],
                "type": child.Type,
            }
            for child in children
        ]


class VisualizationRpcModule(IRpcModule):
    """Module to provide data for the navigation visualization graph with recursive analysis."""

    def __init__(self, root: Any):
        self._root = root
        self.nodes = {}
        self.edges = []
        self._processed_elements = set()

    def _add_node(self, element_id, label, group, title=None):
        if element_id not in self.nodes:
            self.nodes[element_id] = {
                "id": element_id, "label": label, "group": group, "title": title or label}

    def _add_edge(self, from_id, to_id, label=""):
        edge_id = f"{from_id}->{to_id}"
        if not any(e.get('id') == edge_id for e in self.edges):
            self.edges.append({"id": edge_id, "from": from_id,
                              "to": to_id, "arrows": "to", "label": label})

    def _get_element_by_qualified_name(self, qn: str) -> IModelUnit | None:
        parts = qn.split('.')
        if len(parts) != 2:
            return None
        module_name, element_name = parts
        module = next((m for m in self._root.GetUnitsOfType(
            'Projects$Module') if m.Name == module_name), None)
        if not module:
            return None
        page = next((p for p in module.GetUnitsOfType(
            'Pages$Page') if p.Name == element_name), None)
        if page:
            return page
        microflow = next((mf for mf in module.GetUnitsOfType(
            'Microflows$Microflow') if mf.Name == element_name), None)
        if microflow:
            return microflow
        return None

    def _find_descendants_by_type(self, element: IModelElement, target_type: str) -> List[IModelElement]:
        """Iteratively finds all descendant elements of a specific type."""
        found_elements = []
        queue = [element]
        visited = {str(element.ID)}
        while queue:
            current_element = queue.pop(0)
            if current_element.Type == target_type:
                found_elements.append(current_element)

            elements_to_check = []
            for prop in current_element.GetProperties():
                value = prop.Value
                if isinstance(value, IModelElement):
                    elements_to_check.append(value)
                elif isinstance(value, list):
                    elements_to_check.extend(
                        item for item in value if isinstance(item, IModelElement))
            if isinstance(current_element, IModelUnit):
                elements_to_check.extend(current_element.GetElements())

            for el in elements_to_check:
                el_id = str(el.ID)
                if el_id not in visited:
                    visited.add(el_id)
                    queue.append(el)
        return found_elements

    def _process_menu_item(self, item: IModelElement, parent_id: str):
        item_id = str(item.ID)
        captionText_obj = item.GetProperty('caption').Value
        item_caption = captionText_obj.GetProperty(
            'translations').Value[0].GetProperty('text').Value
        self._add_node(item_id, item_caption, "menu")
        self._add_edge(parent_id, item_id)

        action = item.GetProperty('action').Value
        if action:
            target_element = None
            if action.Type == 'Pages$PageClientAction':
                page_qn = action.GetProperty(
                    'pageSettings').Value.GetProperty('page').Value
                if page_qn:
                    target_element = self._get_element_by_qualified_name(
                        page_qn)
            elif action.Type == 'Pages$MicroflowClientAction':
                mf_qn = action.GetProperty(
                    'microflowSettings').Value.GetProperty('microflow').Value
                if mf_qn:
                    target_element = self._get_element_by_qualified_name(mf_qn)

            if target_element:
                self._add_node(str(target_element.ID), target_element.QualifiedName,
                               target_element.Type.split('$')[-1].lower())
                self._add_edge(item_id, str(target_element.ID))
                if target_element.Type == 'Pages$Page':
                    self._process_page(target_element)
                elif target_element.Type == 'Microflows$Microflow':
                    self._process_microflow(target_element)

        child_items_prop = item.GetProperty('items')
        if child_items_prop:
            for child_item in child_items_prop.Value:
                self._process_menu_item(child_item, item_id)

    def _process_page(self, page: IModelUnit):
        page_id = str(page.ID)
        if page_id in self._processed_elements:
            return
        self._processed_elements.add(page_id)

        for role_qn in page.GetProperty('allowedRoles').Value:
            self._add_node(role_qn, role_qn.split(
                '.')[-1], 'moduleRole', title=f"Module Role: {role_qn}")
            self._add_edge(role_qn, page_id, "can open")

        # Recursive analysis: Find microflows called from this page
        mf_actions = self._find_descendants_by_type(
            page, 'Pages$MicroflowClientAction')
        for action in mf_actions:
            mf_qn = action.GetProperty(
                'microflowSettings').Value.GetProperty('microflow').Value
            if mf_qn:
                target_mf = self._get_element_by_qualified_name(mf_qn)
                if target_mf:
                    self._add_node(str(target_mf.ID), mf_qn, 'microflow')
                    self._add_edge(page_id, str(target_mf.ID))
                    self._process_microflow(target_mf)  # Recursive call

        # Recursive analysis: Find pages opened from this page
        page_actions = self._find_descendants_by_type(
            page, 'Pages$PageClientAction')
        for action in page_actions:
            page_qn = action.GetProperty(
                'pageSettings').Value.GetProperty('page').Value
            if page_qn:
                target_page = self._get_element_by_qualified_name(page_qn)
                # Avoid self-references
                if target_page and str(target_page.ID) != page_id:
                    self._add_node(str(target_page.ID), page_qn, 'page')
                    self._add_edge(page_id, str(target_page.ID))
                    self._process_page(target_page)  # Recursive call

    def _process_microflow(self, microflow: IModelUnit):
        mf_id = str(microflow.ID)
        if mf_id in self._processed_elements:
            return
        self._processed_elements.add(mf_id)

        for role_qn in microflow.GetProperty('allowedModuleRoles').Value:
            self._add_node(role_qn, role_qn.split(
                '.')[-1], 'moduleRole', title=f"Module Role: {role_qn}")
            self._add_edge(role_qn, mf_id, "can execute")

        # Recursive analysis: Find other microflows called from this microflow
        mf_calls = self._find_descendants_by_type(
            microflow, 'Microflows$MicroflowCall')
        for call in mf_calls:
            mf_qn = call.GetProperty('microflow').Value
            if mf_qn:
                target_mf = self._get_element_by_qualified_name(mf_qn)
                if target_mf:
                    self._add_node(str(target_mf.ID), mf_qn, 'microflow')
                    self._add_edge(mf_id, str(target_mf.ID))
                    self._process_microflow(target_mf)  # Recursive call

        # Recursive analysis: Find pages shown from this microflow
        page_actions = self._find_descendants_by_type(
            microflow, 'Microflows$ShowPageAction')
        for action in page_actions:
            page_qn = action.GetProperty(
                'pageSettings').Value.GetProperty('page').Value
            if page_qn:
                target_page = self._get_element_by_qualified_name(page_qn)
                if target_page:
                    self._add_node(str(target_page.ID), page_qn, 'page')
                    self._add_edge(mf_id, str(target_page.ID))
                    self._process_page(target_page)  # Recursive call

    def get_navigation_data(self) -> Dict[str, Any]:
        self.nodes.clear()
        self.edges.clear()
        self._processed_elements.clear()
        project_security = self._root.GetUnitsOfType(
            'Security$ProjectSecurity')[0]
        for user_role in project_security.GetProperty('userRoles').Value:
            user_role_name = user_role.GetProperty('name').Value
            self._add_node(user_role_name, user_role_name,
                           'userRole', title=f"User Role: {user_role_name}")
            for module_role_qn in user_role.GetProperty('moduleRoles').Value:
                self._add_node(module_role_qn, module_role_qn.split(
                    '.')[-1], 'moduleRole', title=f"Module Role: {module_role_qn}")
                self._add_edge(user_role_name, module_role_qn, "contains")

        nav_doc = self._root.GetUnitsOfType('Navigation$NavigationDocument')[0]
        profile = nav_doc.GetProperty('profiles').Value[0]
        profile_id = str(profile.ID)
        self._add_node(profile_id, "Navigation Profile", "navigation")

        menu_items = profile.GetProperty(
            'menuItemCollection').Value.GetProperty('items').Value
        for item in menu_items:
            self._process_menu_item(item, profile_id)

        return {"nodes": list(self.nodes.values()), "edges": self.edges}

# ==============================================================================
# DEPENDENCY INJECTION CONTAINER
# ==============================================================================


class AppContainer(containers.DeclarativeContainer):
    config = providers.Configuration()
    model_browser_service = providers.Singleton(
        ModelBrowserRpcModule, root=config.mendix_root)
    visualization_service = providers.Singleton(
        VisualizationRpcModule, root=config.mendix_root)
    rpc_modules = providers.List(model_browser_service, visualization_service)
    dispatcher = providers.Singleton(RpcDispatcher, modules=rpc_modules)

# ==============================================================================
# COMPOSITION ROOT & EVENT LOOP (as per your boilerplate)
# ==============================================================================
# The 'root' variable is injected into the script's scope by the Mendix environment.
# We check for its existence before trying to use it.


container = AppContainer()
container.config.mendix_root.from_value(root)
dispatcher_instance = container.dispatcher()

# This is the main entry point for handling messages from the frontend
PostMessage("backend:info", 'server started')
# 样板代码，接收前端请求（插件是一个长期运行的、由事件驱动）


def onMessage(e: Any):
    if e.Message == "frontend:message":
        try:
            request_string = JsonSerializer.Serialize(e.Data)
            request_object = json.loads(request_string)
            if request_object:
                response = dispatcher_instance.handle_request(request_object)
                PostMessage("backend:response", json.dumps(response))
        except Exception as ex:
            PostMessage(
                "backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")
