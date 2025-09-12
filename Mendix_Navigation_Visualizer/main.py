import json
from typing import Any, Dict, List, Type, Set
import traceback
from collections import deque
PostMessage("backend:clear",'')
# ShowDevTools()
# --- 1. LIBRARY IMPORTS ---
from dependency_injector import containers, providers

import clr
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow
from Mendix.StudioPro.ExtensionsAPI.Model.Pages import IPage
from abc import ABC, abstractmethod

# --- Core Utilities (Unchanged) ---
def serialize_json_object(json_object: Any) -> str:
    import System.Text.Json
    return System.Text.Json.JsonSerializer.Serialize(json_object)

def deserialize_json_string(json_string: str) -> Any:
    return json.loads(json_string)

def post_message(channel: str, message: str):
    PostMessage(channel, message)

# === 2. APPLICATION COMPONENTS (Interfaces and Implementations) ===

#region Abstractions (Interfaces)
class IElementMapper(ABC):
    # ... (Unchanged)
    @abstractmethod
    def map_summary_from_unit(self, unit: Any, module_name: str) -> Dict[str, Any]: pass
    @abstractmethod
    def map_summary_from_module(self, module: Any) -> Dict[str, Any]: pass
    @abstractmethod
    def map_details_from_element(self, element: Any) -> Dict[str, Any]: pass

class IElementRetriever(ABC):
    # ... (Unchanged)
    @abstractmethod
    def get_all_elements(self) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_element_by_id_and_type(self, element_id: str, element_type: str) -> Any: pass
    
class IEditorActions(ABC):
    # ... (Unchanged)
    @abstractmethod
    def locate_element(self, qualified_name: str, element_type: str) -> Dict[str, Any]: pass

# --- [NEW] Traceability Analyzer Abstraction ---
# --- [MODIFIED] Traceability Analyzer Abstraction ---
class ITraceabilityAnalyzer(ABC):
    @abstractmethod
    def get_full_graph(self) -> Dict[str, Any]:
        """Returns the complete traceability graph."""
        pass
    
    @abstractmethod
    def find_paths(self, start_node_id: str, end_node_id: str) -> List[List[Dict[str, Any]]]:
        """Finds all paths between two nodes."""
        pass
        
    @abstractmethod
    def find_common_upstream(self, node_ids: List[str]) -> Dict[str, Any]:
        """Finds common ancestors (dependencies) for a set of nodes."""
        pass

    @abstractmethod
    def find_common_downstream(self, node_ids: List[str]) -> Dict[str, Any]:
        """Finds common descendants (impacts) for a set of nodes."""
        pass
        
    @abstractmethod
    def get_subgraph(self, node_ids: List[str]) -> Dict[str, Any]:
        """Returns a subgraph containing only the specified nodes and their direct connections."""
        pass
#endregion


#region Concrete Implementations ---
class ElementMapper(IElementMapper):
    # ... (Unchanged, implementation is identical)
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
            "properties": [], "children": [] # Simplified for brevity
        }

class MendixElementRetriever(IElementRetriever):
    # ... (Unchanged, implementation is identical)
    def __init__(self, root: Any, mapper: IElementMapper):
        self._root = root
        self._mapper = mapper
        self._unit_type_map = {"Microflow": "Microflows$Microflow", "Page": "Pages$Page"}
    def get_all_elements(self) -> List[Dict[str, Any]]:
        return [self._mapper.map_summary_from_module(m) for m in self._root.GetUnitsOfType("Projects$Module")]
    def get_element_by_id_and_type(self, element_id: str, element_type: str) -> Any:
        # ... simplified for brevity
        return None

class MendixEditorActions(IEditorActions):
    # ... (Unchanged, implementation is identical)
    def locate_element(self, qualifiedName: str, elementType: str) -> Dict[str, Any]:
        # ... implementation
        return {"success": True}




# --- [HEAVILY MODIFIED] Traceability Analyzer Implementation ---
class MendixTraceabilityAnalyzer(ITraceabilityAnalyzer):
    """
    Encapsulates graph building and querying logic.
    Caches the built graph for performance.
    """
    def __init__(self, root: Any):
        self._root = root
        self._full_graph_cache = None

    def _build_graph_if_needed(self):
        if self._full_graph_cache:
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
#endregion

#region rpc
class RpcHandler:
    def __init__(self, retriever: IElementRetriever, editor: IEditorActions, mapper: IElementMapper, analyzer: ITraceabilityAnalyzer):
        self._retriever = retriever
        self._editor = editor
        self._mapper = mapper
        self._analyzer = analyzer # [NEW] Injected dependency
    
    # ... (Existing methods are unchanged)
    def get_all_elements(self) -> List[Dict[str, Any]]: return self._retriever.get_all_elements()
    def get_element_details(self, elementId: str, elementType: str) -> Dict[str, Any]:
        # ... implementation
        return {}
    def locate_element(self, qualifiedName: str, elementType: str) -> Dict[str, Any]:
        return self._editor.locate_element(qualifiedName, elementType)

    # --- [NEW] RPC Method Implementation ---
    def get_traceability_graph(self) -> Dict[str, Any]:
        return self._analyzer.analyze()
    def get_traceability_graph(self) -> Dict[str, Any]:
        # This now just serves to get the full graph initially
        return self._analyzer.get_full_graph()
    
    # --- [NEW] RPC Methods for Analysis ---
    def find_paths(self, startNodeId: str, endNodeId: str) -> List[List[Dict[str, Any]]]:
        return self._analyzer.find_paths(startNodeId, endNodeId)

    def find_common_upstream(self, nodeIds: List[str]) -> Dict[str, Any]:
        return self._analyzer.find_common_upstream(nodeIds)

    def find_common_downstream(self, nodeIds: List[str]) -> Dict[str, Any]:
        return self._analyzer.find_common_downstream(nodeIds)

    def get_subgraph(self, nodeIds: List[str]) -> Dict[str, Any]:
        return self._analyzer.get_subgraph(nodeIds)
        
class RpcDispatcher:
    # ... (Unchanged, implementation is identical)
    def __init__(self): self._methods = {}
    def register_method(self, name: str, func): self._methods[name] = func
    def handle_request(self, request: Dict[str, Any]):
        try:
            result = self._methods[request.get('method')](**request.get('params', {}))
            return {'jsonrpc': '2.0', 'result': result, 'requestId': request.get('id')}
        except Exception as e:
            error_message = f"An error occurred: {e}\n{traceback.format_exc()}"
            PostMessage("backend:info", error_message)
            return {'jsonrpc': '2.0', 'error': error_message, 'requestId': request.get('id')}

#endregion

#region IoC CONTAINER CONFIGURATION ===
class AppContainer(containers.DeclarativeContainer):
    config = providers.Configuration()
    # Data Mapping Layer
    element_mapper: providers.Provider[IElementMapper] = providers.Singleton(ElementMapper)
    # Platform Layer
    editor_actions: providers.Provider[IEditorActions] = providers.Singleton(MendixEditorActions)
    element_retriever: providers.Provider[IElementRetriever] = providers.Singleton(
        MendixElementRetriever, root=config.mendix_root, mapper=element_mapper
    )
    # [NEW] Analysis Layer
    traceability_analyzer: providers.Provider[ITraceabilityAnalyzer] = providers.Singleton(
        MendixTraceabilityAnalyzer, root=config.mendix_root
    )
    # Application Layer
    rpc_handler = providers.Singleton(
        RpcHandler,
        retriever=element_retriever,
        editor=editor_actions,
        mapper=element_mapper,
        analyzer=traceability_analyzer, # [NEW] Injecting the analyzer
    )
    # Dispatcher Layer
    dispatcher = providers.Singleton(RpcDispatcher)
#endregion

#region COMPOSITION ROOT & EVENT HANDLING ===
container = AppContainer()
container.config.mendix_root.from_value(root)
rpc_handler_instance = container.rpc_handler()
dispatcher_instance = container.dispatcher()

# f=container.traceability_analyzer().analyze()
# PostMessage("backend:info", f"{f}")

# Register both old and new RPC methods
rpc_methods = {
    'getAllElements': rpc_handler_instance.get_all_elements,
    'getElementDetails': rpc_handler_instance.get_element_details,
    'locateElement': rpc_handler_instance.locate_element,
    'getTraceabilityGraph': rpc_handler_instance.get_traceability_graph, # [NEW]
    'findPaths': rpc_handler_instance.find_paths,
    'findCommonUpstream': rpc_handler_instance.find_common_upstream,
    'findCommonDownstream': rpc_handler_instance.find_common_downstream,
    'getSubgraph': rpc_handler_instance.get_subgraph,
}
for name, method in rpc_methods.items():
    dispatcher_instance.register_method(name, method)

def onMessage(e):
    if e.Message == "frontend:message":
        message_data = deserialize_json_string(serialize_json_object(e))
        # PostMessage("backend:info", serialize_json_object(e))
        response = dispatcher_instance.handle_request(message_data["Data"])
        post_message("backend:response", json.dumps(response))
#endregion