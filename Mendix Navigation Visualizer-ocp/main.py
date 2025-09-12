# === 0. BOILERPLATE & IMPORTS ===

from abc import ABC, abstractmethod
from Mendix.StudioPro.ExtensionsAPI.Model.Pages import IPage
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType
import clr
from dependency_injector import containers, providers
import json
from typing import Any, Dict, List, Set, Protocol
import traceback
from collections import deque
import inspect  # For automatic method discovery

# Mendix-specific setup
PostMessage("backend:clear", '')
# ShowDevTools()

# Library imports
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")


# === 1. CORE UTILITIES ===

def serialize_json_object(json_object: Any) -> str:
    """Serializes a Python object to a JSON string using .NET's serializer."""
    import System.Text.Json
    return System.Text.Json.JsonSerializer.Serialize(json_object)


def deserialize_json_string(json_string: str) -> Any:
    """Deserializes a JSON string to a Python object."""
    return json.loads(json_string)


def post_message(channel: str, message: str):
    """Posts a message to the frontend."""
    PostMessage(channel, message)


# === 2. APPLICATION ABSTRACTIONS (Interfaces) ===
# These define the "contracts" of our system. They are open for new implementations.

class IElementMapper(ABC):
    @abstractmethod
    def map_summary_from_unit(
        self, unit: Any, module_name: str) -> Dict[str, Any]: pass

    @abstractmethod
    def map_summary_from_module(self, module: Any) -> Dict[str, Any]: pass
    @abstractmethod
    def map_details_from_element(self, element: Any) -> Dict[str, Any]: pass


class IElementRetriever(ABC):
    @abstractmethod
    def get_all_elements(self) -> List[Dict[str, Any]]: pass

    @abstractmethod
    def get_element_by_id_and_type(
        self, element_id: str, element_type: str) -> Any: pass


class IEditorActions(ABC):
    @abstractmethod
    def locate_element(self, qualified_name: str,
                       element_type: str) -> Dict[str, Any]: pass


class ITraceabilityAnalyzer(ABC):
    @abstractmethod
    def get_full_graph(self) -> Dict[str, Any]: pass

    @abstractmethod
    def find_paths(self, start_node_id: str,
                   end_node_id: str) -> List[List[Dict[str, Any]]]: pass

    @abstractmethod
    def find_common_upstream(self, node_ids: List[str]) -> Dict[str, Any]: pass

    @abstractmethod
    def find_common_downstream(
        self, node_ids: List[str]) -> Dict[str, Any]: pass

    @abstractmethod
    def get_subgraph(self, node_ids: List[str]) -> Dict[str, Any]: pass


# === 3. CONCRETE IMPLEMENTATIONS (Services) ===
# These are the detailed implementations, closed for modification unless there's a bug.

class ElementMapper(IElementMapper):
    def map_summary_from_unit(self, unit: Any, module_name: str) -> Dict[str, Any]:
        return {
            "id": str(unit.ID), "name": f"{module_name}.{unit.Name}",
            "type": unit.Type.split("$")[-1],
            "qualifiedName": unit.QualifiedName if hasattr(unit, "QualifiedName") else None
        }

    def map_summary_from_module(self, module: Any) -> Dict[str, Any]:
        return {"id": str(module.ID), "name": f"{module.Name}", "type": "module"}

    def map_details_from_element(self, element: Any) -> Dict[str, Any]:
        return {
            "name": element.Name, "type": element.Type, "qualifiedName": element.QualifiedName,
            "properties": [], "children": []  # Simplified for brevity
        }


class MendixElementRetriever(IElementRetriever):
    def __init__(self, root: Any, mapper: IElementMapper):
        self._root = root
        self._mapper = mapper

    def get_all_elements(self) -> List[Dict[str, Any]]:
        return [self._mapper.map_summary_from_module(m) for m in self._root.GetUnitsOfType("Projects$Module")]

    def get_element_by_id_and_type(self, element_id: str, element_type: str) -> Any:
        # Implementation would search through the model; simplified for example.
        return None


class MendixEditorActions(IEditorActions):
    def locate_element(self, qualifiedName: str, elementType: str) -> Dict[str, Any]:
        # Implementation would interact with the Studio Pro API.
        return {"success": True}


class MendixTraceabilityAnalyzer(ITraceabilityAnalyzer):
    def __init__(self, root: Any):
        self._root = root
        self._full_graph_cache: Dict[str, Any] | None = None

    def _build_graph_if_needed(self):
        if self._full_graph_cache is not None:
            return
        
        # --- (The existing graph building logic from your code) ---
        nodes_map = {}
        edges_list = []
        page_lookup = {p.QualifiedName: p for m in self._root.GetUnitsOfType('Projects$Module') for p in m.GetUnitsOfType('Pages$Page')}
        microflow_lookup = {mf.QualifiedName: mf for m in self._root.GetUnitsOfType('Projects$Module') for mf in m.GetUnitsOfType('Microflows$Microflow')}
        
        # Helper functions adapted to be local
        def _get_or_create_node(q_name, type_override=None, name=None):
            # ... (Same as your _get_or_create_node, but uses local nodes_map)
            if not q_name or q_name in nodes_map: return
            parts = q_name.split('.')
            node = {"id": q_name, "type": type_override or "UNKNOWN", "name": name or parts[-1], "module": parts[0]}
            if not type_override:
                if page_lookup.get(q_name): node["type"] = "PAGE"
                elif microflow_lookup.get(q_name): node["type"] = "MICROFLOW"
            nodes_map[q_name] = node

        def _add_edge(source, target, type):
            if source and target: edges_list.append({"source": source, "target": target, "type": type})

        def _get_property_value(el, prop):
            p = el.GetProperty(prop)
            return p.Value if p and p.Value else None

        def _get_references_from_unit(unit, is_page):
            # ... (Same as your _get_references_from_unit)
            refs = []
            if is_page:
                for source in unit.GetElementsOfType('Pages$MicroflowSource'):
                    microflowSettings = _get_property_value(source, 'microflowSettings')
                    if microflowSettings:
                        microflow = _get_property_value(microflowSettings, 'microflow')
                        refs.append((microflow, "CALLS"))
            else: # Is Microflow
                for call in unit.GetElementsOfType('Microflows$MicroflowCall'):
                    if mf := _get_property_value(call, 'microflow'): refs.append((mf, "CALLS"))
                for act in unit.GetElementsOfType('Microflows$ActionActivity'):
                    action = _get_property_value(act, 'action')
                    if action and action.Type == 'Microflows$ShowPageAction':
                        if page := _get_property_value(_get_property_value(action, 'pageSettings'), 'page'):
                            refs.append((page, "SHOWS"))
            return list(set(refs))
            
        # --- (The rest of the graph traversal logic) ---
        queue = []
        processed_items = set()
        # Seeding from navigation... (simplified)
        nav_docs = self._root.GetUnitsOfType('Navigation$NavigationDocument')
        for nav_doc in nav_docs:
            for profile in nav_doc.GetElementsOfType('Navigation$NavigationProfile'):
                homePage = _get_property_value(profile, 'homePage')
                home_page_name = _get_property_value(homePage, 'page')
                if home_page_name:
                    nav_id = f"Navigation.{profile.Name}"
                    _get_or_create_node(nav_id, "NAVIGATION_ITEM", name=f"Home Page ({profile.Name})")
                    _get_or_create_node(home_page_name, "PAGE")
                    _add_edge(nav_id, home_page_name, "SHOWS")
                    if home_page_name not in processed_items:
                        queue.append(home_page_name)
                        processed_items.add(home_page_name)
        
        # Traversing...
        head = 0
        while head < len(queue):
            current_id = queue[head]; head += 1
            unit = page_lookup.get(current_id) or microflow_lookup.get(current_id)
            if not unit: continue
            references = _get_references_from_unit(unit, current_id in page_lookup)
            for ref_id, edge_type in references:
                if ref_id:
                    _get_or_create_node(ref_id)
                    _add_edge(current_id, ref_id, edge_type)
                    if ref_id not in processed_items:
                        queue.append(ref_id)
                        processed_items.add(ref_id)
        
        # --- Create efficient lookup structures and cache ---
        self._full_graph_cache = {
            "nodes": list(nodes_map.values()),
            "edges": edges_list
        }
        self._nodes_by_id = {node['id']: node for node in self._full_graph_cache['nodes']}
        # Adjacency lists for fast traversal
        self._adj = {node['id']: [] for node in self._full_graph_cache['nodes']}
        self._rev_adj = {node['id']: [] for node in self._full_graph_cache['nodes']}
        for edge in edges_list:
            if edge['source'] in self._adj: self._adj[edge['source']].append(edge['target'])
            if edge['target'] in self._rev_adj: self._rev_adj[edge['target']].append(edge['source'])

    # --- Public API Methods ---
    def get_full_graph(self) -> Dict[str, Any]:
        self._build_graph_if_needed()
        return self._full_graph_cache

    def find_paths(self, start_node_id: str, end_node_id: str) -> List[List[Dict[str, Any]]]:
        self._build_graph_if_needed()
        # Using BFS to find the shortest path for simplicity
        if start_node_id not in self._adj or end_node_id not in self._adj:
            return []
        queue = deque([(start_node_id, [start_node_id])])
        visited = {start_node_id}
        
        while queue:
            current_node, path = queue.popleft()
            if current_node == end_node_id:
                return [[self._nodes_by_id.get(node_id) for node_id in path if self._nodes_by_id.get(node_id)]]

            for neighbor in self._adj.get(current_node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append((neighbor, new_path))
        return [] # No path found

    def _traverse(self, start_nodes: List[str], forward: bool = True) -> Set[str]:
        adj_list = self._adj if forward else self._rev_adj
        all_related = set()
        for start_node in start_nodes:
            q = deque([start_node])
            visited = {start_node}
            while q:
                curr = q.popleft()
                for neighbor in adj_list.get(curr, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        q.append(neighbor)
            all_related.update(visited)
        return all_related

    def find_common_upstream(self, node_ids: List[str]) -> Dict[str, Any]:
        self._build_graph_if_needed()
        if not node_ids: return {"nodes": [], "edges": []}
        
        ancestor_sets = []
        for node_id in node_ids:
            ancestors = self._traverse([node_id], forward=False)
            ancestor_sets.append(ancestors)
            
        common_ancestors_ids = set.intersection(*ancestor_sets)
        # We should not include the selected nodes themselves in the result
        common_ancestors_ids = common_ancestors_ids - set(node_ids)

        return self.get_subgraph(list(common_ancestors_ids))

    def find_common_downstream(self, node_ids: List[str]) -> Dict[str, Any]:
        self._build_graph_if_needed()
        if not node_ids: return {"nodes": [], "edges": []}
        
        descendant_sets = []
        for node_id in node_ids:
            descendants = self._traverse([node_id], forward=True)
            descendant_sets.append(descendants)
            
        common_descendants_ids = set.intersection(*descendant_sets)
        common_descendants_ids = common_descendants_ids - set(node_ids)

        return self.get_subgraph(list(common_descendants_ids))

    def get_subgraph(self, node_ids: List[str]) -> Dict[str, Any]:
        self._build_graph_if_needed()
        node_id_set = set(node_ids)
        subgraph_nodes = [node for node in self._full_graph_cache['nodes'] if node['id'] in node_id_set]
        subgraph_edges = [edge for edge in self._full_graph_cache['edges'] if edge['source'] in node_id_set and edge['target'] in node_id_set]
        return {"nodes": subgraph_nodes, "edges": subgraph_edges}

# === 4. RPC LAYER (Application's Public API) ===
# This layer is now modular and adheres to the Open/Closed Principle.

class IRpcModule(Protocol):
    """A marker protocol that identifies a class as a provider of RPC methods."""
    pass


class CoreElementRpcModule(IRpcModule):
    """Handles core element retrieval and editor actions."""

    def __init__(self, retriever: IElementRetriever, editor: IEditorActions, mapper: IElementMapper):
        self._retriever = retriever
        self._editor = editor
        self._mapper = mapper

    def getAllElements(self) -> List[Dict[str, Any]]:
        return self._retriever.get_all_elements()

    def getElementDetails(self, elementId: str, elementType: str) -> Dict[str, Any]:
        element = self._retriever.get_element_by_id_and_type(
            elementId, elementType)
        return self._mapper.map_details_from_element(element) if element else {}

    def locateElement(self, qualifiedName: str, elementType: str) -> Dict[str, Any]:
        return self._editor.locate_element(qualifiedName, elementType)


class TraceabilityRpcModule(IRpcModule):
    """Handles traceability graph analysis."""

    def __init__(self, analyzer: ITraceabilityAnalyzer):
        self._analyzer = analyzer

    def getTraceabilityGraph(self) -> Dict[str, Any]:
        return self._analyzer.get_full_graph()

    def findPaths(self, startNodeId: str, endNodeId: str) -> List[List[Dict[str, Any]]]:
        return self._analyzer.find_paths(startNodeId, endNodeId)

    def findCommonUpstream(self, nodeIds: List[str]) -> Dict[str, Any]:
        return self._analyzer.find_common_upstream(nodeIds)

    def findCommonDownstream(self, nodeIds: List[str]) -> Dict[str, Any]:
        return self._analyzer.find_common_downstream(nodeIds)

    def getSubgraph(self, nodeIds: List[str]) -> Dict[str, Any]:
        return self._analyzer.get_subgraph(nodeIds)


class RpcDispatcher:
    """
    Generic dispatcher for RPC calls. It discovers and registers public methods from
    all provided RPC modules. This class is now completely closed for modification.
    """

    def __init__(self, modules: List[IRpcModule]):
        self._methods: Dict[str, Any] = {}
        for module_instance in modules:
            for name, method in inspect.getmembers(module_instance, predicate=inspect.ismethod):
                if not name.startswith('_'):
                    if name in self._methods:
                        PostMessage(
                            "backend:info", f"Warning: RPC method name collision for '{name}'. Overwriting.")
                    self._methods[name] = method
        PostMessage(
            "backend:info", f"Dispatcher initialized with methods: {list(self._methods.keys())}")

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method_name = request.get('method')
        if not method_name or method_name not in self._methods:
            error_message = f"Method '{method_name}' not found."
            PostMessage("backend:info", error_message)
            return {'jsonrpc': '2.0', 'error': {'message': error_message}, 'requestId': request.get('id')}

        try:
            method = self._methods[method_name]
            params = request.get('params', {})
            result = method(**params)
            return {'jsonrpc': '2.0', 'result': result, 'requestId': request.get('id')}
        except Exception as e:
            error_message = f"An error occurred in method '{method_name}': {e}\n{traceback.format_exc()}"
            PostMessage("backend:info", error_message)
            return {'jsonrpc': '2.0', 'error': {'message': error_message}, 'requestId': request.get('id')}


# === 5. IoC CONTAINER (The Assembler) ===
# This class wires the entire application together. To extend the system,
# you will primarily add new providers and list new modules here.

class AppContainer(containers.DeclarativeContainer):
    """Assembles the application's components."""
    config = providers.Configuration()

    # --- Service Providers ---
    # These create single instances of our core services.
    element_mapper = providers.Singleton(ElementMapper)
    editor_actions = providers.Singleton(MendixEditorActions)
    element_retriever = providers.Singleton(
        MendixElementRetriever, root=config.mendix_root, mapper=element_mapper)
    traceability_analyzer = providers.Singleton(
        MendixTraceabilityAnalyzer, root=config.mendix_root)

    # --- RPC Module Providers ---
    # These create single instances of our RPC modules, injecting their dependencies.
    core_element_module = providers.Singleton(
        CoreElementRpcModule,
        retriever=element_retriever,
        editor=editor_actions,
        mapper=element_mapper
    )
    traceability_module = providers.Singleton(
        TraceabilityRpcModule,
        analyzer=traceability_analyzer
    )

    # --- The List of All Active RPC Modules ---
    # TO EXTEND THE APPLICATION with new RPC features, simply add the new module's provider to this list.
    # This is the primary extension point for new functionality.
    rpc_modules = providers.List(
        core_element_module,
        traceability_module,
        # e.g., code_quality_module would be added here
    )

    # --- Dispatcher Provider ---
    # This creates the final dispatcher, injecting the list of all active modules.
    dispatcher = providers.Singleton(
        RpcDispatcher,
        modules=rpc_modules,
    )


# === 6. COMPOSITION ROOT & EVENT HANDLING (Application Entry Point) ===
# This section initializes the container and sets up the message handling loop.
# It is completely generic and closed for modification.

container = AppContainer()
# The global 'root' object from the Mendix environment is injected here.
container.config.mendix_root.from_value(root)

# The dispatcher is now fully wired by the container. No manual registration is needed.
dispatcher_instance = container.dispatcher()


def onMessage(e: Any):
    """Main message handler, delegates all incoming requests to the dispatcher."""
    if e.Message == "frontend:message":
        try:
            # The serialization dance is necessary due to the IronPython environment
            message_data = deserialize_json_string(serialize_json_object(e))
            # Pass the RPC request object to the dispatcher for handling
            request_object = message_data.get("Data")
            if request_object:
                response = dispatcher_instance.handle_request(request_object)
                post_message("backend:response", json.dumps(response))
            else:
                PostMessage("backend:info",
                            "Received message with no 'Data' field.")
        except Exception as ex:
            PostMessage(
                "backend:info", f"Fatal error in onMessage handler: {ex}\n{traceback.format_exc()}")
