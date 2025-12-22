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
        traceId = None  # [Telemetry] 初始化 traceId
        try:
            # Dual-layer deserialization safety
            json_str = System.Text.Json.JsonSerializer.Serialize(message_wrapper)
            data = json.loads(json_str)
            raw_request = data.get("Data")
            if not raw_request: return
            
            request = json.loads(raw_request) if isinstance(raw_request, str) else raw_request
            if not isinstance(request, dict): return

            req_id = request.get("id")
            traceId = request.get("traceId") # [Telemetry] 提取前端传入的 traceId
            method = request.get("method")
            params = request.get("params", {})

            if method not in self._routes:
                raise Exception(f"Method '{method}' not found.")

            result = self._routes[method](**params)
            
            # Send Success
            # [Telemetry] 将 traceId 原样返回给前端
            response = {"jsonrpc": "2.0", "result": result, "requestId": req_id, "traceId": traceId}
            PostMessage("backend:response", json.dumps(response))

        except Exception as e:
            # Send Error
            err_msg = f"{str(e)}\n{traceback.format_exc()}"
            PostMessage("backend:info", err_msg)
            if req_id is not None:
                # [Telemetry] 错误响应也携带 traceId
                response = {"jsonrpc": "2.0", "error": {"message": str(e)}, "requestId": req_id, "traceId": traceId}
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

# ==========================================
# [CORE] Mendix Untyped API Wrapper
# ==========================================
class MxNode:
    """
    一个Pythonic的Mendix对象包装器，屏蔽底层的GetProperties/Type/Value复杂性。
    用法:
       node = MxNode(element)
       name = node['Name']
       attrs = node.children('Attributes') # 返回 MxNode 列表
    """
    def __init__(self, raw_element):
        self.raw = raw_element
        self._props = {}
        if raw_element and hasattr(raw_element, "GetProperties"):
            for p in raw_element.GetProperties():
                self._props[p.Name] = p

    @property
    def type(self):
        # 检查 1: 如果 self.raw 是一个字符串，直接返回 "String"
        if isinstance(self.raw, str):
            return "String"

        # 检查 2: 如果 self.raw 存在（非 None, 非空列表等）并且具有 'Type' 属性
        # 注意：如果 self.raw 是字符串，此分支不会被执行，因为它已经在上面被捕获了
        if self.raw and hasattr(self.raw, 'Type'):
            # 确保 self.raw.Type 存在后，执行分割逻辑
            return str(self.raw.Type).split('$')[-1]
        
        # 否则，返回默认值 "Null"
        return "Null"

    @property
    def full_type(self):
        return str(self.raw.Type) if self.raw else "Null"
    
    def has(self, key):
        return key in self._props

    def get(self, key, default=None):
        """获取简单值 (String, Bool, Int, Enum)"""
        if key not in self._props: return default
        val = self._props[key].Value
        return str(val) if val is not None else default

    def resolve(self, key):
        """获取引用对象 (Reference)，返回 MxNode"""
        if key not in self._props: return None
        val = self._props[key].Value
        return MxNode(val) if val else None

    def children(self, key):
        """获取列表子项 (List)，返回 [MxNode]"""
        if key not in self._props: return []
        prop = self._props[key]
        if not prop.IsList or not prop.Value: return []
        return [MxNode(item) for item in prop.Value]

    def __getitem__(self, key):
        return self.get(key)
    
    def __repr__(self):
        return f"<MxNode {self.type}: {self.get('Name', 'NoName')}>"
    
# 1. 默认 DSL 配置 (可以从文件加载)
# 格式: "类型名": { "include": [字段], "rename": {内:外}, "recurse": {内: 规则名} }
DEFAULT_DSL = {
    # === 1. 全局默认 (Fallback) ===
    # 如果没有匹配到特定类型，则默认输出所有属性，但限制深度
    "__DEFAULT__": {
        "include": ["*"], 
        "recurse": { "*": None }
    },
}

class YamlExtractor:
    def __init__(self, dsl_config=None):
        self.config = dsl_config if dsl_config else DEFAULT_DSL

    def extract(self, element, rule_name=None, depth=0, max_depth=5):
        # 1. 深度保护
        if depth > max_depth:
            return "..." 

        node = MxNode(element)
        if not node.raw: return None
        if node.type == "String": return node.raw

        # 2. 确定规则
        rule_key = rule_name if rule_name else node.type
        rule = self.config.get(rule_key, self.config.get("__DEFAULT__"))

        result = {}
        
        include_list = rule.get("include", [])
        include_all = "*" in include_list
        
        recurse_map = rule.get("recurse", {})
        recurse_all = "*" in recurse_map

        # === 遍历属性 ===
        for prop_name, prop_obj in node._props.items():
            
            is_list = prop_obj.IsList
            val = prop_obj.Value
            
            # 判断引用类型
            is_ref = val is not None and not is_list and hasattr(val, "GetProperties")
            
            # --- 分支 A: 处理 List 或 Reference ---
            if is_list or is_ref:
                target_rule = None
                should_recurse = False

                if recurse_all:
                    should_recurse = True
                    target_rule = None 
                elif prop_name in recurse_map:
                    should_recurse = True
                    target_rule = recurse_map[prop_name]

                if should_recurse:
                    out_key = rule.get("rename", {}).get(prop_name, prop_name)
                    
                    if is_list:
                        # [修复点] C# List 不能直接切片
                        # 必须先用 list() 将其转换为 Python 列表
                        raw_collection = val if val else []
                        py_list = list(raw_collection) 
                        
                        children_data = []
                        # 现在可以安全地切片了
                        for item in py_list[:20]: 
                            child_res = self.extract(item, target_rule, depth + 1, max_depth)
                            if child_res: children_data.append(child_res)
                            
                        if children_data:
                            result[out_key] = children_data
                    else:
                        # 单引用
                        child_res = self.extract(val, target_rule, depth + 1, max_depth)
                        if child_res:
                            result[out_key] = child_res

            # --- 分支 B: 处理普通值 ---
            else:
                should_include = False
                if include_all:
                    should_include = True
                elif prop_name in include_list:
                    should_include = True
                
                if should_include:
                    out_key = rule.get("rename", {}).get(prop_name, prop_name)
                    v_str = str(val) if val is not None else "null"
                    if v_str != "null" and v_str != "":
                        result[out_key] = v_str

        # 补充 Type 标识
        if "_Type" not in result:
            result = {"_Type": node.type, **result}

        return result

    def to_yaml(self, data):
        # 保持之前的 YAML 转换逻辑不变
        def dump(obj, depth=0):
            indent = "  " * depth
            if obj is None: return "null"
            if isinstance(obj, (str, int, float, bool)): return str(obj)
            
            lines = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if v is None: continue
                    if isinstance(v, list) and len(v) == 0: continue
                    
                    if isinstance(v, list):
                        lines.append(f"{indent}{k}:")
                        for item in v:
                            if isinstance(item, dict):
                                keys = list(item.keys())
                                if keys:
                                    first_k = keys[0]
                                    rest_obj = item.copy()
                                    del rest_obj[first_k]
                                    lines.append(f"{indent}  - {first_k}: {dump(item[first_k], 0)}")
                                    if rest_obj:
                                        lines.append(dump(rest_obj, depth + 2))
                            else:
                                lines.append(f"{indent}  - {dump(item, 0)}")
                    elif isinstance(v, dict):
                         lines.append(f"{indent}{k}:\n{dump(v, depth + 1)}")
                    else:
                        val_str = str(v).replace('\n', '\\n')
                        lines.append(f"{indent}{k}: {val_str}")
            return "\n".join(lines)
        return dump(data)

extractor = YamlExtractor()

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
    
    # 逻辑：直接子节点 = 所有后代 - 子文件夹中的后代
    if hasattr(parent, "GetUnits"):
        # 1. 获取当前节点下所有的单元 (递归列表，包含直接和间接)
        all_descendants = list(parent.GetUnits())
        
        # 2. 获取当前节点下所有的文件夹
        sub_folders = list(parent.GetUnitsOfType('Projects$Folder'))
        
        # 3. 收集所有“间接节点”的 ID
        # 如果一个单元存在于任意一个子文件夹中，那它对于当前 parent 来说就是间接的
        indirect_ids = set()
        for folder in sub_folders:
            # 这里的 folder.GetUnits() 会返回该文件夹下的所有内容
            for sub_unit in folder.GetUnits():
                indirect_ids.add(str(sub_unit.ID))
        
        # 4. 筛选：保留不在 indirect_ids 集合中的节点
        for u in all_descendants:
            if str(u.ID) not in indirect_ids:
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

# ==========================================
# [新增] 结构化元数据生成器
# ==========================================
class StructureExplorer:
    @staticmethod
    def explore(node):
        if node is None: return None
        
        # 获取类型名称
        type_name = getattr(node, "Type", type(node).__name__)
        
        result = {
            "metaType": str(type_name),
            "attributes": [],  # 普通属性 (String, Bool, Enum)
            "children": []     # 结构化属性 (Element, List)
        }

        # 防御性编程：如果没有 GetProperties 方法（比如是基础字符串），直接返回
        if not hasattr(node, "GetProperties"):
            return {"metaType": "Value", "value": str(node)}

        try:
            for p in node.GetProperties():
                p_type = str(p.Type)
                
                # 1. 处理结构化嵌套 (Element / ElementByName)
                if "Element" in p_type:
                    # 如果是列表 (List of Elements)
                    if p.IsList:
                        child_nodes = []
                        if p.Value: 
                            for item in list(p.Value):
                                child_nodes.append(StructureExplorer.explore(item))
                        
                        result["children"].append({
                            "key": p.Name,
                            "type": "List<Element>",
                            "data": child_nodes,
                            "count": len(p.Value) if p.Value else 0
                        })
                    
                    # 如果是单体对象 (如 microflowSettings)
                    else:
                        nested_data = StructureExplorer.explore(p.Value)
                        # 只有当非空时才加入，或者标记为空
                        result["children"].append({
                            "key": p.Name,
                            "type": p_type,
                            "data": nested_data,
                            "isEmpty": p.Value is None
                        })
                
                # 2. 处理普通属性
                else:
                    result["attributes"].append({
                        "key": p.Name,
                        "type": p_type,
                        "value": str(p.Value) if p.Value is not None else "null"
                    })
        except Exception as e:
            print(f"Error exploring node: {e}")

        return result

# [新增路由]
@app.route("get_structure")
def get_structure(node_id: str):
    target = app.get_cached(node_id)
    if not target: raise Exception("Node not found")
    return StructureExplorer.explore(target)
@app.route("get_ai_yaml")
def get_ai_yaml(node_id: str, max_depth: int = 15):
    """
    专门为 LLM 设计的端点。
    根据 DSL 清洗数据，并返回纯文本 YAML。
    """
    target = app.get_cached(node_id)
    if not target: return "Error: Node not found"

    # 执行提取
    try:
        clean_data = extractor.extract(target, max_depth=max_depth)
        # 生成 YAML 字符串
        yaml_text = extractor.to_yaml(clean_data)
        
        # 加上头部注释，帮助 LLM 理解上下文
        header = f"# Mendix Object Context\n# Type: {target.Type}\n# ID: {node_id}\n\n"
        return header + yaml_text
    except Exception as e:
        return f"Error generating YAML: {str(e)}\n{traceback.format_exc()}"

# === 3. ENTRY POINT ===
PostMessage("backend:clear", '')
def onMessage(e: Any):
    if e.Message == "frontend:message":
        app.handle_message(e)
PostMessage("backend:info", "Plugin Backend Ready.")