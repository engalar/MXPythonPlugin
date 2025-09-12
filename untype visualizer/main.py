# gh gist edit 536df8e04cd5574946a62414abb12ad8 .\main.py -f main.py

# pip install pythonnet dependency-injector

# === 0. BOILERPLATE & IMPORTS ===
import clr
from dependency_injector import containers, providers
import json
from typing import Any, Dict, List, Protocol
import traceback
import inspect

clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
PostMessage("backend:clear", '')
# ShowDevTools() # 在开发时取消注释以打开开发者工具


# === 1. CORE UTILITIES ===
def serialize_json_object(json_object: Any) -> str:
    # 将.NET对象序列化为JSON字符串
    import System.Text.Json
    return System.Text.Json.JsonSerializer.Serialize(json_object)


def deserialize_json_string(json_string: str) -> Any:
    # 将JSON字符串反序列化为Python对象
    return json.loads(json_string)


def post_message(channel: str, message: str):
    # 向前端发送消息的辅助函数
    PostMessage(channel, message)


# === 2. MODEL BROWSER IMPLEMENTATION ===
TOP_LEVEL_UNIT_TYPES = [
    'Projects$ProjectConversion',
    'Settings$ProjectSettings',
    'Texts$SystemTextCollection',
    'Navigation$NavigationDocument',
    'Security$ProjectSecurity',
    'Projects$Module',
]
MODULE_SPECIAL_UNIT_TYPES = [
    'DomainModels$DomainModel',
    'Security$ModuleSecurity',
    'Projects$ModuleSettings',
]


class ModelBrowserService:
    """
    封装所有与模型浏览相关的后端逻辑。
    """

    def __init__(self, root: Any):
        self._root = root
        self._element_cache = {}

    def _serialize_element_summary(self, element: Any, parent_id: str, index: int) -> Dict[str, Any]:
        is_unit = hasattr(element, "ID")
        element_id = f"{parent_id}:_elements:{index}"
        if is_unit:
            element_id = str(element.ID)

        self._element_cache[element_id] = element
        has_children = (element.GetUnits().Count > 0) if is_unit else False

        return {
            "id": element_id,
            "name": getattr(element, "Name", "[Unnamed]"),
            "type": element.Type,
            "isUnit": is_unit,
            "hasChildren": has_children
        }

    def _get_element_by_id(self, element_id: str) -> Any:
        if element_id in self._element_cache:
            return self._element_cache[element_id]
        raise Exception(f"Element with ID '{element_id}' not found in cache.")

    def _serialize_property(self, prop: Any, parent_id: str) -> Dict[str, Any]:
        """将属性序列化，并包含懒加载所需的信息。"""
        prop_id = f"{parent_id}:property:{prop.Name}"
        prop_value = "N/A"
        has_children = False
        value_type = "Primitive"
        prop_type_str = str(prop.Type)

        try:
            val = prop.Value
            if val is None:
                prop_value = "null"
            elif prop.IsList:
                has_children = val.Count > 0
                prop_value = f"[{val.Count} items]"
                value_type = "List"
                if has_children:
                    self._element_cache[prop_id] = val
            elif hasattr(val, "ID"):  # 这是一个可展开的Unit或Element
                has_children = True
                prop_value = getattr(val, "Name", "[Unnamed]")
                value_type = "Element"
                self._element_cache[prop_id] = val
            # --- 新增逻辑开始 ---
            elif prop_type_str in ["ElementByName", "ElementByQualifiedName"] and isinstance(val, str):
                has_children = False  # 我们在这里不解析它，所以它没有子节点
                prop_value = str(val)
                value_type = "ResolvableElement"  # 使用新的类型来标识
            # --- 新增逻辑结束 ---
            else:
                prop_value = str(val)
        except Exception:
            prop_value = "[Error reading value]"

        return {
            "id": prop_id,
            "name": prop.Name,
            "type": prop_type_str if prop_type_str!='Element' or prop.IsList or val==None else f"Element({val.Type},{val.ID})",  # 使用prop_type_str
            "value": prop_value,
            "hasChildren": has_children,
            "valueType": value_type,
        }

    def get_node_children(self, node_id: str) -> List[Dict[str, Any]]:
        children_units = []
        if node_id == "root":
            for unit_type in TOP_LEVEL_UNIT_TYPES:
                children_units.extend(self._root.GetUnitsOfType(unit_type))
        else:
            target_unit = self._get_element_by_id(node_id)
            all_descendants = list(target_unit.GetUnits())
            if not all_descendants:
                return []
            all_descendant_ids = {str(u.ID) for u in all_descendants}
            grandchildren_ids = set()
            for descendant in all_descendants:
                for grand in descendant.GetUnits():
                    grandchildren_ids.add(str(grand.ID))
            direct_child_ids = all_descendant_ids - grandchildren_ids
            direct_children = [u for u in all_descendants if str(
                u.ID) in direct_child_ids]
            if target_unit.Type == 'Projects$Module':
                special_units = []
                other_direct_children = []
                special_unit_types_set = set(MODULE_SPECIAL_UNIT_TYPES)
                for child in direct_children:
                    if child.Type in special_unit_types_set:
                        special_units.append(child)
                    else:
                        other_direct_children.append(child)
                children_units.extend(special_units)
                children_units.extend(other_direct_children)
            else:
                children_units.extend(direct_children)

        serialized_children = [self._serialize_element_summary(
            unit, node_id, i) for i, unit in enumerate(children_units)]
        return sorted(serialized_children, key=lambda x: x['name'] or '')

    def get_node_details(self, node_id: str) -> Dict[str, Any]:
        """获取单元详情，属性和内部元素都将形成可懒加载的树。"""
        if node_id == "root":
            return {"name": "Project Root", "type": "IModelRoot", "properties": [], "elements": []}

        target_unit = self._get_element_by_id(node_id)

        # --- 修改 elements_list 的生成方式 ---
        elements_list = []
        for i, element in enumerate(target_unit.GetElements()):
            element_id = f"{node_id}:element:{i}"
            self._element_cache[element_id] = element

            # 当元素没有名字时，使用其类型和索引作为备用名
            element_name = getattr(element, "Name", None)
            if not element_name:
                element_name = f"[{element.Type.split('$')[-1]} #{i}]"

            elements_list.append({
                "id": element_id,
                "name": element_name,
                "type": element.Type,
                "value": "",  # 值可以是空的，因为主要信息在其子属性中
                "hasChildren": True,  # 假定所有内部元素都有属性可以查看
                "valueType": "Element",
            })
        # --- 修改结束 ---

        properties_tree = [self._serialize_property(
            prop, node_id) for prop in target_unit.GetProperties()]

        return {
            "id": node_id,
            "name": getattr(target_unit, "Name", "[Unnamed]"),
            "type": target_unit.Type,
            "elements": sorted(elements_list, key=lambda x: x['name'] or ''),
            "properties": sorted(properties_tree, key=lambda x: x['name'] or '')
        }

    def get_property_children(self, property_id: str) -> List[Dict[str, Any]]:
        """懒加载属性的子节点。"""
        children = []
        prop_value_obj = self._element_cache.get(property_id)
        if prop_value_obj is None:
            return []

        # --- 修改开始 ---
        # 检查它是否像一个列表（ duck-typing: 检查是否有'__iter__' 和 'Count'，并且不是字符串）
        is_list_like = hasattr(prop_value_obj, '__iter__') and hasattr(prop_value_obj, 'Count') and not isinstance(prop_value_obj, str)

        if is_list_like and not hasattr(prop_value_obj, 'ID'):  # 确保它不是一个有.Count属性的Unit/Element
            for i, item in enumerate(prop_value_obj):
                child_id = f"{property_id}:item:{i}"

                # 检查列表项是否为基本类型
                if isinstance(item, (str, int, float, bool)):
                    children.append({
                        "id": child_id,
                        "name": f"[{i}]",
                        "type": type(item).__name__,  # 显示 'str', 'int', etc.
                        "value": str(item),          # 直接显示字符串的值
                        "hasChildren": False,
                        "valueType": "Primitive"
                    })
                    # 注意：基本类型不需要缓存，因为它们不能再被展开
                else: # 否则，假定它是一个复杂对象
                    self._element_cache[child_id] = item
                    children.append({
                        "id": child_id,
                        "name": f"[{i}]",
                        "type": getattr(item, "Type", "Unknown"),
                        "value": getattr(item, "Name", "[Unnamed]"),
                        "hasChildren": hasattr(item, "ID") or (hasattr(item, "GetProperties") and any(item.GetProperties())),
                        "valueType": "Element"
                    })

        elif hasattr(prop_value_obj, 'ID'):  # 是一个Element/Unit
            # 属性的值本身就是一个可展开的对象
            for prop in prop_value_obj.GetProperties():
                children.append(self._serialize_property(prop, property_id))
        # --- 修改结束 ---

        # 列表项通常按索引排序，所以这里可以不排序，或按'name'（即索引）排序
        # return sorted(children, key=lambda x: x['name'] or '')
        return children

# === 3. RPC & IoC Container ===


class IRpcModule(Protocol):
    pass


class ModelBrowserRpcModule(IRpcModule):
    def __init__(self, service: ModelBrowserService): self._service = service

    def getNodeChildren(
        self, nodeId: str = "root") -> List[Dict[str, Any]]: return self._service.get_node_children(nodeId)

    def getNodeDetails(
        self, nodeId: str) -> Dict[str, Any]: return self._service.get_node_details(nodeId)
    def getPropertyChildren(
        self, propertyId: str) -> List[Dict[str, Any]]: return self._service.get_property_children(propertyId)


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


class AppContainer(containers.DeclarativeContainer):
    config = providers.Configuration()
    model_browser_service = providers.Singleton(
        ModelBrowserService, root=config.mendix_root)
    model_browser_module = providers.Singleton(
        ModelBrowserRpcModule, service=model_browser_service)
    rpc_modules = providers.List(model_browser_module)
    dispatcher = providers.Singleton(RpcDispatcher, modules=rpc_modules)


# === 4. COMPOSITION ROOT ===
container = AppContainer()
container.config.mendix_root.from_value(root)
dispatcher_instance = container.dispatcher()

# 样板代码，接收前端请求（插件是一个长期运行的、由事件驱动）
def onMessage(e: Any):
    if e.Message == "frontend:message":
        try:
            message_data = deserialize_json_string(serialize_json_object(e))
            request_object = message_data.get("Data")
            if request_object:
                response = dispatcher_instance.handle_request(request_object)
                post_message("backend:response", json.dumps(response))
        except Exception as ex:
            PostMessage(
                "backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")
