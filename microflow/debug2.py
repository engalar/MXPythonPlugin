from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType
import clr
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# ==========================================
# 1. 初始化日志缓冲区
# ==========================================
log_buffer = []

def log_line(msg):
    log_buffer.append(msg)

def safe_str(val):
    if val is None: return "None"
    # 【关键修改】不截断内容，仅将物理换行符转换为字符 '\n'，保证单行显示且内容完整
    return str(val).replace('\n', '\\n').strip()

# ==========================================
# 2. 核心：解析节点业务逻辑 (完整参数版)
# ==========================================
def get_node_summary(node):
    if not node: return "Unknown Node"
    
    node_type = node.Type.split('$')[-1]
    summary = ""
    
    try:
        # --- A. ActionActivity ---
        if "ActionActivity" in node_type:
            action = node.GetProperty('action').Value
            if not action: return f"[{node_type}] (Empty Action)"
            
            action_type = action.Type.split('$')[-1]
            summary = f"[{action_type}]" # 明确活动类型
            
            # 1. 微流调用
            if "MicroflowCall" in action_type:
                mf_call = action.GetProperty('microflowCall').Value
                mf_name = mf_call.GetProperty('microflow').Value
                summary += f" Target: {mf_name}"
                
                # 【关键修改】完整遍历参数列表
                param_mappings_prop = mf_call.GetProperty('parameterMappings')
                if param_mappings_prop and param_mappings_prop.IsList:
                    params = list(param_mappings_prop.GetValues())
                    if params:
                        summary += " | Params: ("
                        p_list = []
                        for p in params:
                            # parameter通常是 'Module.Microflow.ParamName'，只取最后一段保持简洁
                            raw_p_name = safe_str(p.GetProperty('parameter').Value)
                            p_name = raw_p_name.split('.')[-1] 
                            p_arg = safe_str(p.GetProperty('argument').Value)
                            p_list.append(f"{p_name}={p_arg}")
                        summary += ", ".join(p_list) + ")"
            
            # 2. 变量创建
            elif "CreateVariable" in action_type:
                var_name = action.GetProperty('variableName').Value
                # 完整显示初始值
                init_val = safe_str(action.GetProperty('initialValue').Value)
                summary += f" ${var_name} = {init_val}"
                
            # 3. 数据库获取
            elif "Retrieve" in action_type:
                source = action.GetProperty('retrieveSource').Value
                entity = source.GetProperty('entity').Value
                xpath = safe_str(source.GetProperty('xPathConstraint').Value)
                output = action.GetProperty('outputVariableName').Value
                summary += f" Entity: {entity} | XPath: {xpath} | Output: ${output}"
            
            else:
                summary += f" (Details: {action_type})"

        # --- B. ExclusiveSplit ---
        elif "ExclusiveSplit" in node_type:
            caption = safe_str(node.GetProperty('caption').Value)
            condition = node.GetProperty('splitCondition').Value
            expr = safe_str(condition.GetProperty('expression').Value)
            summary = f"[{node_type}] Caption: '{caption}' | Expr: {expr}"

        # --- C. EndEvent ---
        elif "EndEvent" in node_type:
            ret_val = safe_str(node.GetProperty('returnValue').Value)
            summary = f"[{node_type}] Return: {ret_val}"
            
        # --- D. Parameters ---
        elif "Parameter" in node_type:
             name = node.GetProperty('name').Value
             type_info = node.GetProperty('variableType').Value.Type.split('$')[-1]
             summary = f"[{node_type}] {name} ({type_info})"

        else:
            summary = f"[{node_type}]"

    except Exception as e:
        summary += f" (Parse Error: {e})"
        
    return summary

# ==========================================
# 3. 增强：解析流向分支 (修复 caseValues 列表解析)
# ==========================================
def get_flow_label(flow_obj):
    try:
        # 【关键修改】从数据看，caseValues 是一个列表 (plural)
        case_vals_prop = flow_obj.GetProperty('caseValues')
        
        val_obj = None
        
        # 如果属性存在且是列表，取第一个 case 对象
        if case_vals_prop and case_vals_prop.IsList:
            items = list(case_vals_prop.GetValues())
            if items:
                val_obj = items[0]
        
        # 兼容性备用：如果不是列表，尝试读取单数属性 caseValue
        if not val_obj:
            case_val_prop = flow_obj.GetProperty('caseValue')
            if case_val_prop and case_val_prop.Type == PropertyType.Element:
                val_obj = case_val_prop.Value

        # 如果都没有 Case 对象，则是普通连线
        if not val_obj:
            return "-->"

        # 解析 Case 类型
        case_type = val_obj.Type.split('$')[-1]

        # 1. NoCase: 普通连线 或 默认Else路径
        if "NoCase" in case_type:
            return "-->" 
            
        # 2. EnumerationCase: 通常包含 value 属性 (true/false/枚举值)
        if "EnumerationCase" in case_type:
            val_prop = val_obj.GetProperty('value')
            if val_prop:
                return f"-- [{val_prop.Value}] -->" # 输出: -- [true] -->
        
        return f"-- [{case_type}] -->"

    except Exception as e:
        return f"--> (LabelErr: {e})"

# ==========================================
# 4. 主程序
# ==========================================
PostMessage("backend:clear", '')

unit = root
units = unit.GetUnitsOfType('Projects$Module')
unit = next((u for u in units if u.Name == 'AltairIntegration'), None)

if unit:
    units = unit.GetUnitsOfType('Microflows$Microflow')
    target_microflow = next((u for u in units if u.Name == 'Tool_SparqlConverter'), None)
    
    if target_microflow:
        log_line(f"MICROFLOW ANALYSIS: {target_microflow.Name}")
        log_line("="*100)

        object_collection = target_microflow.GetProperty('objectCollection').Value
        # 使用 list() 转换确保兼容性
        objects_list = list(object_collection.GetProperty('objects').GetValues())
        flows_list = list(target_microflow.GetProperty('flows').GetValues())

        node_map = {obj.ID.ToString(): obj for obj in objects_list}
        
        # 构建邻接表
        adj_list = {} 
        for flow in flows_list:
            origin = flow.GetProperty('origin').Value.ToString()
            dest = flow.GetProperty('destination').Value.ToString()
            if origin not in adj_list: adj_list[origin] = []
            adj_list[origin].append((flow, dest))

        start_node = next((n for n in objects_list if "StartEvent" in n.Type), None)
        visited = set()

        def traverse(node_id, prefix=""):
            if node_id in visited:
                log_line(f"{prefix}(Loop/Merge point detected)")
                return
            
            visited.add(node_id)
            current_node = node_map.get(node_id)
            if not current_node: return

            # 打印节点
            node_desc = get_node_summary(current_node)
            log_line(f"{prefix}{node_desc}")

            # 打印流向
            outgoing = adj_list.get(node_id, [])
            
            if len(outgoing) == 1:
                # 线性流程
                traverse(outgoing[0][1], prefix)
            
            elif len(outgoing) > 1:
                # 分支流程
                for flow, target_id in outgoing:
                    label = get_flow_label(flow)
                    log_line(f"{prefix}  {label}")
                    traverse(target_id, prefix + "    ")

        if start_node:
            traverse(start_node.ID.ToString())
        else:
            log_line("Error: No StartEvent found")

        log_line("="*100)
        PostMessage("backend:info", "\n".join(log_buffer))

    else:
         PostMessage("backend:error", "Microflow not found.")
else:
    PostMessage("backend:error", "Module not found.")