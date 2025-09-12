import json
from typing import Any, Dict, List, Type

# --- 1. LIBRARY IMPORTS ---
# Assuming 'dependency-injector' is available in the Mendix Python environment.
# pip install dependency-injector
from dependency_injector import containers, providers

# Standard imports remain the same
import clr
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow
from Mendix.StudioPro.ExtensionsAPI.Model.Pages import IPage
from abc import ABC, abstractmethod

# ShowDevTools()

# --- Core Utilities (Unchanged) ---
def serialize_json_object(json_object: Any) -> str:
    import System.Text.Json
    return System.Text.Json.JsonSerializer.Serialize(json_object)

def deserialize_json_string(json_string: str) -> Any:
    return json.loads(json_string)

def post_message(channel: str, message: str):
    PostMessage(channel, message)

# === 2. APPLICATION COMPONENTS (Interfaces and Implementations) ===
# These classes are now completely decoupled from the IoC mechanism.
# Their __init__ methods simply declare their dependencies via type hints.

# --- Abstractions (Interfaces - Unchanged) ---
class IElementMapper(ABC):
    @abstractmethod
    def map_summary_from_unit(self, unit: Any, module_name: str) -> Dict[str, Any]: pass
    @abstractmethod
    def map_summary_from_module(self, module: Any) -> Dict[str, Any]: pass
    @abstractmethod
    def map_details_from_element(self, element: Any) -> Dict[str, Any]: pass

class IElementRetriever(ABC):
    @abstractmethod
    def get_all_elements(self) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_domain_model_elements(self) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_microflows(self) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_pages(self) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_element_by_id_and_type(self, element_id: str, element_type: str) -> Any: pass

class IEditorActions(ABC):
    @abstractmethod
    def locate_element(self, qualified_name: str, element_type: str) -> Dict[str, Any]: pass

# --- Concrete Implementations (Unchanged logic, only dependency declarations) ---
class ElementMapper(IElementMapper):
    """(Implementation is identical to the previous version)"""
    def map_summary_from_unit(self, unit: Any, module_name: str) -> Dict[str, Any]:
        return {
            "id": str(unit.ID), "name": f"{module_name}.{unit.Name}",
            "type": unit.Type.split("$")[-1],
            "qualifiedName": unit.QualifiedName if hasattr(unit, "QualifiedName") else None
        }
    def map_summary_from_module(self, module: Any) -> Dict[str, Any]:
        return {"id": str(module.ID), "name": f"{module.Name}", "type": module.Type.split("$")[-1]}
    def map_details_from_element(self, element: Any) -> Dict[str, Any]:
        return {
            "name": element.Name, "type": element.Type, "qualifiedName": element.QualifiedName,
            "properties": self._map_properties(element.GetProperties()),
            "children": self._map_children(element.GetElements())
        }
    def _map_properties(self, properties: Any) -> List[Dict[str, Any]]:
        prop_list = []
        for prop in properties:
            value = str(prop.Value) if prop.Value is not None else "N/A"
            if prop.Type == PropertyType.Element:
                value = f"[{len(list(prop.Value))} elements]" if prop.IsList and prop.Value else (str(prop.Value.Name) if prop.Value else "N/A")
            prop_list.append({"name": prop.Name, "type": str(prop.Type), "value": value})
        return prop_list
    def _map_children(self, children: Any) -> List[Dict[str, str]]:
        return [{"name": child.Name if hasattr(child, "Name") else "Unnamed", "type": child.Type} for child in children]

class MendixElementRetriever(IElementRetriever):
    def __init__(self, root: Any, mapper: IElementMapper):
        self._root = root
        self._mapper = mapper
        self._unit_type_map = {
            "Module": "Projects$Module", "DomainModel": "DomainModels$DomainModel",
            "Microflow": "Microflows$Microflow", "Page": "Pages$Page", "Entity": "DomainModels$Entity"
        }
    # (Implementation methods are identical to the previous version)
    def get_all_elements(self) -> List[Dict[str, Any]]:
        return [self._mapper.map_summary_from_module(m) for m in self._get_modules()]
    def get_domain_model_elements(self) -> List[Dict[str, Any]]:
        elements = []
        for module in self._get_modules():
            for dm in module.GetUnitsOfType("DomainModels$DomainModel"):
                elements.append(self._mapper.map_summary_from_unit(dm, module.Name))
                for entity in dm.GetElementsOfType("DomainModels$Entity"):
                    elements.append(self._mapper.map_summary_from_unit(entity, module.Name))
        return elements
    def get_microflows(self) -> List[Dict[str, Any]]: return self._get_elements_by_type("Microflows$Microflow")
    def get_pages(self) -> List[Dict[str, Any]]: return self._get_elements_by_type("Pages$Page")
    def get_element_by_id_and_type(self, element_id: str, element_type: str) -> Any:
        unit_type = self._unit_type_map.get(element_type)
        if not unit_type: return None
        if element_type == "Entity":
            for module in self._get_modules():
                for dm in module.GetUnitsOfType("DomainModels$DomainModel"):
                    for entity in dm.GetElementsOfType("DomainModels$Entity"):
                        if str(entity.ID) == element_id: return entity
            return None
        for unit in self._root.GetUnitsOfType(unit_type):
            if str(unit.ID) == element_id: return unit
        return None
    def _get_modules(self): return self._root.GetUnitsOfType("Projects$Module")
    def _get_elements_by_type(self, unit_type: str) -> List[Dict[str, Any]]:
        return [self._mapper.map_summary_from_unit(unit, module.Name)
                for module in self._get_modules() for unit in module.GetUnitsOfType(unit_type)]

class MendixEditorActions(IEditorActions):
    def locate_element(self, qualifiedName: str, elementType: str) -> Dict[str, Any]:
        unit_type_map = {"Microflows$Microflow": IMicroflow, "Pages$Page": IPage}
        api_type = unit_type_map.get(elementType)
        if not api_type: raise Exception(f"Unsupported element type: {elementType}")
        element = currentApp.ToQualifiedName[api_type](qualifiedName).Resolve()
        if not element: raise Exception("Element not found")
        TryOpenEditor(element)
        return {"success": True, "message": f"Opened element: {qualifiedName}"}

class RpcHandler:
    def __init__(self, retriever: IElementRetriever, editor: IEditorActions, mapper: IElementMapper):
        self._retriever = retriever
        self._editor = editor
        self._mapper = mapper
    # (Implementation methods are identical to the previous version)
    def get_all_elements(self) -> List[Dict[str, Any]]: return self._retriever.get_all_elements()
    def get_domain_models(self) -> List[Dict[str, Any]]: return self._retriever.get_domain_model_elements()
    def get_microflows(self) -> List[Dict[str, Any]]: return self._retriever.get_microflows()
    def get_pages(self) -> List[Dict[str, Any]]: return self._retriever.get_pages()
    def get_element_details(self, elementId: str, elementType: str) -> Dict[str, Any]:
        element = self._retriever.get_element_by_id_and_type(elementId, elementType)
        if not element: raise Exception(f"Element with ID {elementId} and type {elementType} not found")
        return self._mapper.map_details_from_element(element)
    def locate_element(self, qualifiedName: str, elementType: str) -> Dict[str, Any]:
        return self._editor.locate_element(qualifiedName, elementType)
        
class RpcDispatcher:
    """(Implementation is identical to the previous version)"""
    def __init__(self):
        self._methods = {}
    def register_method(self, name: str, func):
        self._methods[name] = func
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method_name = request.get('method')
        params = request.get('params', {})
        request_id = request.get('id')
        if method_name not in self._methods:
            return {'jsonrpc': '2.0', 'error': f'Method "{method_name}" not found', 'requestId': request_id}
        try:
            result = self._methods[method_name](**params)
            return {'jsonrpc': '2.0', 'result': result, 'requestId': request_id}
        except Exception as e:
            return {'jsonrpc': '2.0', 'error': str(e), 'requestId': request_id}

# === 3. IoC CONTAINER CONFIGURATION ===
# This is the new heart of the dependency management system.

class AppContainer(containers.DeclarativeContainer):
    """Defines the application's dependency injection container."""

    # Configuration provider for values that come from outside the container, like globals.
    config = providers.Configuration()

    # --- Service Providers ---

    # Data Mapping Layer
    element_mapper: providers.Provider[IElementMapper] = providers.Singleton(ElementMapper)

    # Platform Layer
    editor_actions: providers.Provider[IEditorActions] = providers.Singleton(MendixEditorActions)
    element_retriever: providers.Provider[IElementRetriever] = providers.Singleton(
        MendixElementRetriever,
        root=config.mendix_root,  # Inject the 'root' object from configuration
        mapper=element_mapper,    # Inject the mapper service
    )

    # Application Layer
    rpc_handler = providers.Singleton(
        RpcHandler,
        retriever=element_retriever,
        editor=editor_actions,
        mapper=element_mapper,
    )

    # Dispatcher Layer
    dispatcher = providers.Singleton(RpcDispatcher)


# === 4. COMPOSITION ROOT & EVENT HANDLING ===
# This is where we create, configure, and use the container.

# 1. Create the container instance
container = AppContainer()

# 2. Provide external configuration. 'root' is a global from the Mendix environment.
container.config.mendix_root.from_value(root)

# 3. Wire the container. This step is optional here since we are not using @inject,
# but it's good practice for more complex scenarios.
# container.wire(modules=[__name__])

# 4. Manually compose the final objects by resolving them from the container.
# This approach is clear and avoids issues with framework-controlled entry points.
rpc_handler_instance = container.rpc_handler()
dispatcher_instance = container.dispatcher()

# 5. Register the RPC methods with the dispatcher
rpc_methods = {
    'getAllElements': rpc_handler_instance.get_all_elements,
    'getDomainModels': rpc_handler_instance.get_domain_models,
    'getMicroflows': rpc_handler_instance.get_microflows,
    'getPages': rpc_handler_instance.get_pages,
    'getElementDetails': rpc_handler_instance.get_element_details,
    'locateElement': rpc_handler_instance.locate_element,
}
for name, method in rpc_methods.items():
    dispatcher_instance.register_method(name, method)

# 6. Set up the event listener, which is the application's entry point.
def onMessage(e):
    """
    Handles incoming messages from the frontend.
    It uses the pre-configured dispatcher instance to process requests.
    """
    if e.Message == "frontend:message":# get request from client
        message_data = deserialize_json_string(serialize_json_object(e))
        # The dispatcher is already fully configured and ready to use.
        response = dispatcher_instance.handle_request(message_data["Data"])
        # send response to client
        post_message("backend:response", json.dumps(response))