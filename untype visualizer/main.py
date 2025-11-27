# ID=536df8e04cd5574946a62414abb12ad8
# gh gist edit <ID> .\main.py -f main.py
# pip install pythonnet

import clr
import json
import traceback
from typing import Any, Dict, List, Callable
# ShowDevTools() 

# === 1. FRAMEWORK CORE ===
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
import System.Text.Json

if 'PostMessage' not in globals():
    def PostMessage(channel, msg): print(f"[MOCK] {channel}: {msg}")
if 'root' not in globals():
    root = None 

class MendixApp:
    def __init__(self):
        self._routes: Dict[str, Callable] = {}
        self._element_cache = {}

    def route(self, method_name: str = None):
        def decorator(func):
            name = method_name or func.__name__
            self._routes[name] = func
            return func
        return decorator

    def handle_message(self, message_wrapper: Any):
        req_id = None
        try:
            # Dual-layer deserialization safety
            json_str = System.Text.Json.JsonSerializer.Serialize(message_wrapper)
            data = json.loads(json_str)
            raw_request = data.get("Data")
            if not raw_request: return
            
            request = json.loads(raw_request) if isinstance(raw_request, str) else raw_request
            if not isinstance(request, dict): return

            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            if method not in self._routes:
                raise Exception(f"Method '{method}' not found.")

            result = self._routes[method](**params)
            
            # Send Success
            response = {"jsonrpc": "2.0", "result": result, "requestId": req_id}
            PostMessage("backend:response", json.dumps(response))

        except Exception as e:
            # Send Error
            err_msg = f"{str(e)}\n{traceback.format_exc()}"
            PostMessage("backend:info", err_msg)
            if req_id is not None:
                response = {"jsonrpc": "2.0", "error": {"message": str(e)}, "requestId": req_id}
                PostMessage("backend:response", json.dumps(response))
    
    def cache_element(self, element):
        # 统一生成 ID，无论是 Unit, Element 还是 List
        if element is None: return None
        
        # 如果已有 ID (Unit)，直接使用
        if hasattr(element, "ID"):
            uid = str(element.ID)
            self._element_cache[uid] = element
            return uid
            
        # 如果是 Element 或 List，生成临时 ID
        # 使用 Python 的 id() 作为临时键值 (注意：仅在单次会话有效，生产环境建议用 UUID)
        uid = f"tmp_{id(element)}"
        self._element_cache[uid] = element
        return uid

    def get_cached(self, uid):
        return self._element_cache.get(uid)

app = MendixApp()

# === 2. BUSINESS LOGIC ===

def get_node_type_category(element_type: str, is_unit: bool) -> str:
    """Helper to determine icon category"""
    if element_type in ['Projects$Module', 'Projects$Folder']:
        return 'folder'
    if is_unit:
        return 'file'
    return 'element'

def serialize_summary(element: Any) -> Dict:
    """Lightweight serialization for Tree View"""
    uid = app.cache_element(element)
    is_unit = hasattr(element, "ID")
    e_type = str(element.Type)
    
    # Determine safe name
    raw_name = getattr(element, "Name", None)
    name = raw_name if raw_name else f"[{e_type.split('$')[-1]}]"

    # Determine children existence (lazy check)
    has_children = False
    if is_unit:
        # For Units, children = other Units (sub-folders)
        has_children = element.GetUnits().Count > 0
    
    return {
        "id": uid,
        "name": name,
        "type": e_type,
        "category": get_node_type_category(e_type, is_unit),
        "hasChildren": has_children
    }

@app.route("get_root_nodes")
def get_root_nodes():
    nodes = []
    # Explicit order for Project Explorer feel
    TOP_LEVEL = [
        'Projects$Module',
        'Projects$ProjectConversion', 
        'Settings$ProjectSettings', 
        'Security$ProjectSecurity',
        'Navigation$NavigationDocument',
        'Texts$SystemTextCollection',
    ]
    
    # Generic fetch for top levels
    for t in TOP_LEVEL:
        units = root.GetUnitsOfType(t)
        for u in units:
            nodes.append(serialize_summary(u))
            
    return sorted(nodes, key=lambda x: (x['category'] != 'folder', x['name']))

@app.route("get_children")
def get_children(parent_id: str):
    parent = app.get_cached(parent_id)
    if not parent: raise Exception("Node expired")
    
    children = []
    # Only drill down into Units (Folders/Modules) for the TreeView
    if hasattr(parent, "GetUnits"):
        for u in parent.GetUnits():
            children.append(serialize_summary(u))
            
    return sorted(children, key=lambda x: (x['category'] != 'folder', x['name']))

@app.route("get_details")
def get_details(node_id: str):
    target = app.get_cached(node_id)
    if not target: raise Exception("Node not found")

    # === 新增逻辑：计算项目路径 (Module/Folder/Name) ===
    path_segments = []
    # 仅当目标是 Unit (文件/模块) 或 Element 时尝试计算路径
    if hasattr(target, "Container"):
        curr = target
        while curr:
            # 排除 Project 根节点，通常不需要显示在路径里
            if getattr(curr, "Type", "") == "Projects$Project":
                break
            
            c_name = getattr(curr, "Name", None)
            if c_name:
                path_segments.insert(0, c_name)
            
            # 向上遍历
            try: curr = curr.Container
            except: break
    
    full_path = "/".join(path_segments) if path_segments else getattr(target, "Name", "Unknown")
    # =======================================================

    response = {
        "id": node_id,
        "name": getattr(target, "Name", "[List]" if isinstance(target, list) or hasattr(target, "Count") else "[Element]"),
        "type": getattr(target, "Type", "List"),
        "path": full_path, # <--- 将计算好的路径放入响应
        "category": "element",
        "properties": [],
        "elements": {} 
    }

    # === 辅助函数：标准化元素信息 ===
    def format_el(el):
        e_name = getattr(el, "Name", None)
        if not e_name: e_name = f"[{el.Type.split('$')[-1]}]"
        return {
            "id": app.cache_element(el),
            "name": e_name,
            "type": str(el.Type)
        }

    # === 情况 A: Mendix 对象 (Unit/Element) ===
    if hasattr(target, "GetProperties"):
        response["category"] = get_node_type_category(target.Type, hasattr(target, "ID"))
        
        # 1. 属性 (Properties) - 包含原始类型和直接引用
        for p in target.GetProperties():
            val = None
            try: val = p.Value
            except: pass
            
            prop_data = {
                "name": p.Name,
                "value": "null",
                "metaType": "Primitive",
                "type": str(p.Type),
                "refId": None
            }
            
            if val is not None:
                if p.IsList:
                    prop_data["value"] = f"List [{val.Count}]"
                    prop_data["metaType"] = "List"
                    if val.Count > 0: prop_data["refId"] = app.cache_element(val)
                elif hasattr(val, "ID") or hasattr(val, "GetProperties"):
                    prop_data["value"] = getattr(val, "Name", f"[{val.Type.split('$')[-1]}]")
                    prop_data["metaType"] = "Ref"
                    prop_data["refId"] = app.cache_element(val)
                else:
                    prop_data["value"] = str(val)
            response["properties"].append(prop_data)

        # 2. 内部结构 (Internal Structure) - 级联/分组
        # 策略：如果是Unit(如Module)，取GetUnits(子Unit)；如果是Element(如Entity)，取GetElements(子Element)
        raw_children = []
        if hasattr(target, "GetUnits") and target.GetUnits().Count > 0:
            raw_children = list(target.GetUnits())
        elif hasattr(target, "GetElements"):
            raw_children = list(target.GetElements())
            
        # 分组逻辑
        grouped = {}
        for child in raw_children:
            t = child.Type.split('$')[-1] # 简化的类型名
            if t not in grouped: grouped[t] = []
            grouped[t].append(format_el(child))
        response["elements"] = grouped

    # === 情况 B: 列表 (List) ===
    # 将列表项作为“索引属性”返回，以便在 Properties Tab 中显示 [0], [1]...
    elif hasattr(target, "__iter__"):
        response["type"] = "List"
        idx = 0
        for item in target:
            # 获取安全的 Item Name
            i_name = getattr(item, "Name", None)
            if not i_name and hasattr(item, "Type"): 
                i_name = f"[{item.Type.split('$')[-1]}]"
            if not i_name: i_name = f"Item"

            # 构造属性条目
            # Name 设为 "[n]"，这样前端拼接路径时会形成 .prop[n]
            response["properties"].append({
                "name": f"[{idx}]", 
                "value": i_name,
                "metaType": "Ref", # 列表项通常都是对象引用，支持钻取
                "type": getattr(item, "Type", "Unknown"),
                "refId": app.cache_element(item)
            })
            idx += 1
            
        # 列表本身没有内部结构，都在属性里展示了
        response["elements"] = {}

    return response

# === 3. ENTRY POINT ===
PostMessage("backend:clear", '')
def onMessage(e: Any):
    if e.Message == "frontend:message":
        app.handle_message(e)
PostMessage("backend:info", "Plugin Backend Ready.")