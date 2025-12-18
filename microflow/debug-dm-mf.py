import clr
import traceback
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType

clr.AddReference("Mendix.StudioPro.ExtensionsAPI")


# ==============================================================================
# 1. CORE LAYER: 基础设施与工具 (Technical Concerns)
#    负责处理 Mendix SDK 的底层交互、日志记录和异常防御
# ==============================================================================
class MendixContext:
    def __init__(self, root_node):
        self.root = root_node
        self.log_buffer = []

    def log(self, msg, indent=0):
        """记录日志，支持缩进"""
        prefix = "  " * indent
        self.log_buffer.append(f"{prefix}{msg}")

    def safe_str(self, val):
        """安全转换为字符串，处理换行符"""
        if val is None:
            return ""
        return str(val).replace("\r\n", "\\n").replace("\n", "\\n").strip()

    def safe_get(self, node, prop_name):
        """安全获取属性值"""
        if node is None:
            return None
        prop = node.GetProperty(prop_name)
        return prop.Value if prop else None

    def safe_get_list(self, node, prop_name):
        """安全获取列表属性"""
        if node is None:
            return []
        prop = node.GetProperty(prop_name)
        if prop and prop.IsList:
            return list(prop.GetValues())
        return []

    def find_module(self, module_name):
        """查找指定模块"""
        modules = list(self.root.GetUnitsOfType("Projects$Module"))
        return next((m for m in modules if m.Name == module_name), None)

    def flush_logs(self):
        """输出所有日志到 Mendix 控制台"""
        return "\n".join(self.log_buffer)

    def find_entity_by_qname(self, qualified_name):
        """
        根据 "Module.Entity" 字符串查找实体对象
        """
        if not qualified_name or "." not in qualified_name:
            return None

        try:
            mod_name, ent_name = qualified_name.split(".", 1)

            # 1. 在模型中查找对应模块
            # 注意：这里假设 model.GetModules() 或 model.get_modules() 可用，取决于SDK版本
            # Python.net 通常使用 C# 风格的方法名，但也可能属性化
            target_module = self.find_module(mod_name)

            if not target_module:
                return None

            # 2. 获取该模块的 DomainModel
            dm_units = target_module.GetUnitsOfType("DomainModels$DomainModel")
            dm = next(iter(dm_units), None)
            if not dm:
                return None

            # 3. 在 DomainModel 中查找实体
            dm_entities = self.safe_get_list(dm, "entities")
            for e in dm_entities:
                if e.Name == ent_name:
                    return e

        except Exception as e:
            # print(f"Lookup failed for {qualified_name}: {e}")
            pass

        return None


# ==============================================================================
# 2. LOGIC LAYER A: 领域模型分析器 (Business Logic)
#    专注于实体、属性、关联的解析规则
# ==============================================================================
class DomainModelAnalyzer:
    def __init__(self, context):
        self.ctx = context
        self.entity_lookup = {}  # 缓存 ID -> Name 映射

    def execute(self, module_name):
        module = self.ctx.find_module(module_name)
        if not module:
            self.ctx.log(f"[Error] Module '{module_name}' not found.")
            return

        self.ctx.log(f"DOMAIN MODEL ANALYSIS: {module_name}")
        self.ctx.log("=" * 80)

        # 查找 DomainModel 单元
        dm_units = module.GetUnitsOfType("DomainModels$DomainModel")
        dm = next(iter(dm_units), None)

        if not dm:
            self.ctx.log("No Domain Model found.")
            return

        self._analyze_entities(dm, module_name)
        self._analyze_associations(dm)
        self.ctx.log("=" * 80)

    def _analyze_entities(self, dm, module_name):
        entities = self.ctx.safe_get_list(dm, "entities")
        self.ctx.log(f"Entities ({len(entities)} found):")

        for entity in entities:
            # 建立缓存
            self.entity_lookup[entity.ID.ToString()] = f"{module_name}.{entity.Name}"

            # 解析特征
            is_persistable = self._is_entity_persistable(entity)
            persist_tag = "[Persistable]" if is_persistable else "[Non-Persistable]"
            gen_info = self._get_generalization_info(entity)
            doc = self._get_doc(entity)

            self.ctx.log(
                f"\n[Entity] {entity.Name} {persist_tag}{gen_info}{doc}", indent=1
            )

            # 解析属性
            for attr in self.ctx.safe_get_list(entity, "attributes"):
                a_info = self._parse_attribute(attr)
                self.ctx.log(f"- {a_info}", indent=2)

    def _analyze_associations(self, dm):
        assocs = self.ctx.safe_get_list(dm, "associations")
        assocs.extend(self.ctx.safe_get_list(dm, "crossAssociations"))

        if assocs:
            self.ctx.log(f"\nAssociations ({len(assocs)} found):", indent=1)
            for assoc in assocs:
                try:
                    # 1. 获取端点名称
                    p_ref = self.ctx.safe_get(assoc, "parent")
                    c_ref = self.ctx.safe_get(assoc, "child")

                    # 优先使用 QualifiedName
                    p_name = getattr(
                        p_ref,
                        "QualifiedName",
                        self.entity_lookup.get(str(p_ref), str(p_ref)),
                    )
                    c_name = getattr(
                        c_ref,
                        "QualifiedName",
                        self.entity_lookup.get(str(c_ref), str(c_ref)),
                    )

                    # 2. 获取关键元数据
                    # Type: Reference (1-*) 或 ReferenceSet (*-*)
                    raw_type = str(self.ctx.safe_get(assoc, "type") or "Unknown")
                    type_label = (
                        "Ref" if "Reference" == raw_type.split("$")[-1] else "RefSet"
                    )
                    arrow = "<->" if type_label == "Ref" else "<==>"

                    # Owner: Default (通常在Parent), Both, etc.
                    owner_val = str(self.ctx.safe_get(assoc, "owner"))

                    # 3. 格式化输出
                    # 格式: [Rel] Name: (Parent) A <-> (Child) B [Type: RefSet | Owner: Default]
                    self.ctx.log(
                        f"[Rel] {assoc.Name}: (Parent) {p_name} {arrow} (Child) {c_name} "
                        f"[Type: {type_label} | Owner: {owner_val}]",
                        indent=2,
                    )
                except Exception as e:
                    self.ctx.log(
                        f"[Rel Error] {assoc.Name if assoc else '?'}: {str(e)}",
                        indent=2,
                    )

    # --- 辅助逻辑 ---
    def _is_entity_persistable(self, entity):
        """递归判断实体是否可持久化，严禁隐式默认值"""
        gen_obj = self.ctx.safe_get(entity, "generalization")
        if not gen_obj:
            raise ValueError(
                f"Entity '{entity.Name}' is missing generalization definition."
            )

        gen_type = gen_obj.Type.split("$")[-1]

        # 1. 无继承：必须显式读取 persistable 属性
        if "NoGeneralization" in gen_type:
            prop = gen_obj.GetProperty("persistable")
            if prop is None:
                raise ValueError(
                    f"Entity '{entity.Name}' [NoGeneralization] missing 'persistable' property."
                )
            return prop.Value

        # 2. 有继承：递归检查父实体
        elif "Generalization" in gen_type:
            qname = self.ctx.safe_get(gen_obj, "generalization")
            parent_entity = self.ctx.find_entity_by_qname(qname)
            if parent_entity:
                # 递归调用
                return self._is_entity_persistable(parent_entity)
            else:
                # 有继承类型但找不到父类对象，报错而不给默认值
                raise ValueError(
                    f"Entity '{entity.Name}' defines Generalization but parent entity '{qname}' is missing."
                )

        raise ValueError(f"Unknown generalization type: {gen_type}")

    def _get_generalization_info(self, entity):
        gen = self.ctx.safe_get(entity, "generalization")
        if gen and "Generalization" in gen.Type.split("$")[-1]:
            parent = self.ctx.safe_get(gen, "generalization")
            if parent:
                return f" extends {getattr(parent, 'Name', str(parent))}"
        return ""

    def _get_doc(self, obj):
        val = self.ctx.safe_get(obj, "documentation")
        return f" // {self.ctx.safe_str(val)}" if val else ""

    def _parse_attribute(self, attr):
        type_obj = self.ctx.safe_get(attr, "type")
        if not type_obj:
            return f"{attr.Name}: UnknownType"

        type_meta = type_obj.Type.split("$")[-1]
        type_str = type_meta.replace("AttributeType", "")

        details = ""
        # 字符串长度
        if "String" in type_meta:
            length = self.ctx.safe_get(type_obj, "length")
            details = f"({length if length else 'Unlimited'})"

        # 枚举名称 (修复点)
        elif "Enumeration" in type_meta:
            enum_ref = self.ctx.safe_get(type_obj, "enumeration")
            # 确保获取 Name 属性
            enum_name = (
                getattr(enum_ref, "Name", str(enum_ref)) if enum_ref else "MISSING"
            )
            details = f"<{enum_name}>"

        # 默认值
        def_val = ""
        val_obj = self.ctx.safe_get(attr, "value")
        if val_obj:
            d = self.ctx.safe_get(val_obj, "defaultValue")
            if d:
                def_val = f" = {self.ctx.safe_str(d)}"

        # 文档注释 (新增点)
        doc = self._get_doc(attr)

        return f"{attr.Name}: {type_str}{details}{def_val}{doc}"


# ==============================================================================
# 3. LOGIC LAYER B: 微流分析器 (Business Logic)
#    专注于流程节点、分支、连线的解析规则
# ==============================================================================
class MicroflowAnalyzer:
    def __init__(self, context):
        self.ctx = context
        self.visited = set()
        self.node_map = {}
        self.adj_list = {}

    def execute(self, module_name, microflow_name):
        module = self.ctx.find_module(module_name)
        if not module:
            self.ctx.log(f"[Error] Module '{module_name}' not found.")
            return

        mf_units = module.GetUnitsOfType("Microflows$Microflow")
        target_mf = next((m for m in mf_units if m.Name == microflow_name), None)

        if not target_mf:
            self.ctx.log(
                f"[Error] Microflow '{microflow_name}' not found in {module_name}."
            )
            return

        self.ctx.log(f"MICROFLOW ANALYSIS: {target_mf.Name}")
        self.ctx.log("=" * 80)

        # 1. 准备数据结构
        obj_coll = self.ctx.safe_get(target_mf, "objectCollection")
        objects = self.ctx.safe_get_list(obj_coll, "objects")
        flows = self.ctx.safe_get_list(target_mf, "flows")

        self.node_map = {obj.ID.ToString(): obj for obj in objects}
        self.adj_list = {}

        for flow in flows:
            origin = self.ctx.safe_get(flow, "origin").ToString()
            dest = self.ctx.safe_get(flow, "destination").ToString()
            if origin not in self.adj_list:
                self.adj_list[origin] = []
            self.adj_list[origin].append((flow, dest))

        # 2. 开始遍历
        start_node = next((n for n in objects if "StartEvent" in n.Type), None)
        if start_node:
            self._traverse(start_node.ID.ToString())
        else:
            self.ctx.log("Error: No StartEvent found")

        self.ctx.log("=" * 80)

    def _traverse(self, node_id, prefix=""):
        if node_id in self.visited:
            self.ctx.log(f"{prefix}(Loop/Merge point detected)")
            return

        self.visited.add(node_id)
        node = self.node_map.get(node_id)
        if not node:
            return

        # 打印当前节点
        self.ctx.log(f"{prefix}{self._get_node_summary(node)}")

        # 处理流向
        outgoing = self.adj_list.get(node_id, [])

        if len(outgoing) == 1:
            self._traverse(outgoing[0][1], prefix)
        elif len(outgoing) > 1:
            for flow, target_id in outgoing:
                label = self._get_flow_label(flow)
                self.ctx.log(f"{prefix}  {label}")
                self._traverse(target_id, prefix + "    ")

    def _get_node_summary(self, node):
        if not node:
            return "Unknown Node"

        node_type = node.Type.split("$")[-1]
        summary = ""

        try:
            # --- A. ActionActivity (各种活动节点) ---
            if "ActionActivity" in node_type:
                action = self.ctx.safe_get(node, "action")
                if not action:
                    return f"[{node_type}] (Empty Action)"

                action_type = action.Type.split("$")[-1]
                summary = f"[{action_type}]"

                # 1. 微流调用 (MicroflowCall)
                if "MicroflowCall" in action_type:
                    mf_call = self.ctx.safe_get(action, "microflowCall")
                    target = self.ctx.safe_get(mf_call, "microflow")

                    # 获取目标微流名称
                    t_name = getattr(
                        target, "QualifiedName", getattr(target, "Name", str(target))
                    )
                    summary += f" Target: {t_name}"

                    # 【新增】获取返回变量名
                    out_var = self.ctx.safe_get(action, "outputVariableName")
                    if out_var:
                        summary += f" | Output: ${out_var}"

                    # 获取参数映射
                    param_mappings_prop = mf_call.GetProperty("parameterMappings")
                    if param_mappings_prop and param_mappings_prop.IsList:
                        params = list(param_mappings_prop.GetValues())
                        if params:
                            p_list = []
                            for p in params:
                                # 【修复】参数名获取逻辑：优先取 QualifiedName (Module.Mf.Param) 再分割
                                raw_p_ref = self.ctx.safe_get(p, "parameter")
                                if raw_p_ref:
                                    full_p_name = getattr(
                                        raw_p_ref,
                                        "QualifiedName",
                                        getattr(raw_p_ref, "Name", str(raw_p_ref)),
                                    )
                                    p_name = full_p_name.split(".")[-1]
                                else:
                                    p_name = "?"

                                p_arg = self.ctx.safe_str(
                                    self.ctx.safe_get(p, "argument")
                                )
                                p_list.append(f"{p_name}={p_arg}")
                            summary += " | Params: (" + ", ".join(p_list) + ")"

                # 2. 创建变量 (CreateVariable)
                elif "CreateVariable" in action_type:
                    var_name = self.ctx.safe_get(action, "variableName")
                    init_val = self.ctx.safe_str(
                        self.ctx.safe_get(action, "initialValue")
                    )
                    summary += f" ${var_name} = {init_val}"

                # 3. 数据库获取 (Retrieve)
                elif "Retrieve" in action_type:
                    source = self.ctx.safe_get(action, "retrieveSource")
                    entity_ref = self.ctx.safe_get(source, "entity")

                    # 【修复】获取实体全名 (Module.Entity)
                    if entity_ref:
                        e_name = getattr(
                            entity_ref,
                            "QualifiedName",
                            getattr(entity_ref, "Name", str(entity_ref)),
                        )
                    else:
                        e_name = "?"

                    xpath = self.ctx.safe_str(
                        self.ctx.safe_get(source, "xPathConstraint")
                    )
                    output = self.ctx.safe_get(action, "outputVariableName")

                    summary += f" Entity: {e_name} | XPath: {xpath} | Output: ${output}"

                else:
                    summary += f" (Details: {action_type})"

            # --- B. ExclusiveSplit (互斥网关) ---
            elif "ExclusiveSplit" in node_type:
                caption = self.ctx.safe_str(self.ctx.safe_get(node, "caption"))
                condition = self.ctx.safe_get(node, "splitCondition")
                expr = self.ctx.safe_str(self.ctx.safe_get(condition, "expression"))
                summary = f"[{node_type}] Caption: '{caption}' | Expr: {expr}"

            # --- C. EndEvent (结束节点) ---
            elif "EndEvent" in node_type:
                ret_val = self.ctx.safe_str(self.ctx.safe_get(node, "returnValue"))
                summary = f"[{node_type}] Return: {ret_val}"

            # --- D. Parameter (输入参数) ---
            elif "Parameter" in node_type:
                name = self.ctx.safe_get(node, "name")
                v_type_obj = self.ctx.safe_get(node, "variableType")
                type_info = v_type_obj.Type.split("$")[-1] if v_type_obj else "Unknown"
                summary = f"[{node_type}] {name} ({type_info})"

            # --- E. 其他通用节点 ---
            else:
                summary = f"[{node_type}]"

        except Exception as e:
            summary += f" (Parse Error: {e})"

        return summary

    def _get_flow_label(self, flow):
        # 处理 Case Value (列表或单值兼容)
        vals = self.ctx.safe_get_list(flow, "caseValues")
        val_obj = vals[0] if vals else None

        if not val_obj:
            single = self.ctx.safe_get(flow, "caseValue")
            if single and single.Type == PropertyType.Element:
                val_obj = single.Value

        if not val_obj:
            return "-->"

        case_type = val_obj.Type.split("$")[-1]
        if "EnumerationCase" in case_type:
            v = self.ctx.safe_get(val_obj, "value")
            return f"-- [{v}] -->"

        return f"-- [{case_type}] -->"


# ==============================================================================
# 4. EXECUTION LAYER: 配置与执行
# ==============================================================================
try:
    PostMessage("backend:clear", "")

    # 初始化上下文
    context = MendixContext(root)

    # --- 配置 A: 领域模型分析 ---
    MODULE_TO_ANALYZE = "AmazonBedrockConnector"
    domain_analyzer = DomainModelAnalyzer(context)
    domain_analyzer.execute(MODULE_TO_ANALYZE)

    # --- 配置 B: 微流分析 ---
    MF_MODULE = "AltairIntegration"
    MF_NAME = "Tool_SparqlConverter"
    mf_analyzer = MicroflowAnalyzer(context)
    mf_analyzer.execute(MF_MODULE, MF_NAME)

    # 输出结果
    PostMessage("backend:info", context.flush_logs())

except Exception as e:
    import traceback

    err_msg = f"Fatal Script Error: {str(e)}\n{traceback.format_exc()}"
    PostMessage("backend:error", err_msg)
