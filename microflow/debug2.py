import os
import clr
import traceback
from System import Exception as SystemException

clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType

# ==============================================================================
# 1. 核心框架 (Core Framework)
# ==============================================================================

#region 1. 核心框架 (Core Framework)
_MENDIX_TYPE_REGISTRY = {}


def MendixMap(mendix_type_str):
    """装饰器：建立 Mendix 类型与 Python 类的映射"""

    def decorator(cls):
        _MENDIX_TYPE_REGISTRY[mendix_type_str] = cls
        return cls

    return decorator


class MendixContext:
    """运行上下文：负责日志管理、全局搜索缓存和 Unit 查找"""

    def __init__(self,model, root_node):
        self.root = root_node
        self.model = model
        self.log_buffer = []
        self._entity_qname_cache = {}
        self._is_initialized = False

    def _ensure_initialized(self):
        if self._is_initialized:
            return
        # 预扫描所有模块和实体，建立 O(1) 查询表
        modules = self.root.GetUnitsOfType("Projects$Module")
        for mod in modules:
            dm_units = mod.GetUnitsOfType("DomainModels$DomainModel")
            for dm in dm_units:
                # 注意：此处使用原始 SDK 访问以防初始化循环
                ents = dm.GetProperty("entities").GetValues()
                for e in ents:
                    qname = f"{mod.Name}.{e.GetProperty('name').Value}"
                    self._entity_qname_cache[qname] = e
        self._is_initialized = True

    def log(self, msg, indent=0):
        prefix = "  " * indent
        self.log_buffer.append(f"{prefix}{msg}")

    def flush_logs(self):
        return "\n".join(self.log_buffer)

    def find_module(self, module_name):
        modules = list(self.root.GetUnitsOfType("Projects$Module"))
        raw = next((m for m in modules if m.Name == module_name), None)
        return ElementFactory.create(raw, self) if raw else None

    def find_entity_by_qname(self, qname):
        self._ensure_initialized()
        raw = self._entity_qname_cache.get(qname)
        return ElementFactory.create(raw, self) if raw else None


class ElementFactory:
    """工厂类：负责对象的动态封装"""

    @staticmethod
    def create(raw_obj, context):
        if raw_obj is None:
            return MendixElement(None, context)

        # 处理基础类型
        if isinstance(raw_obj, (str, int, float, bool)):
            return raw_obj

        try:
            full_type = raw_obj.Type
        except AttributeError:
            return MendixElement(raw_obj, context)

        target_cls = _MENDIX_TYPE_REGISTRY.get(full_type, MendixElement)
        return target_cls(raw_obj, context)


class MendixElement:
    """动态代理基类：支持属性缓存、多态摘要和 snake_case 自动转换"""

    def __init__(self, raw_obj, context):
        self._raw = raw_obj
        self.ctx = context
        self._cache = {}  # 性能优化：缓存属性结果

    @property
    def is_valid(self):
        return self._raw is not None

    @property
    def id(self):
        return self._raw.ID.ToString() if self.is_valid else "0"

    @property
    def type_name(self):
        if not self.is_valid:
            return "Null"
        return self._raw.Type.split("$")[-1]

    def __getattr__(self, name):
        """核心魔法：映射 snake_case 到 CamelCase 并自动封装结果"""
        if not self.is_valid:
            return None
        if name in self._cache:
            return self._cache[name]

        # 1. 转换命名: cross_associations -> crossAssociations
        parts = name.split("_")
        camel_name = parts[0] + "".join(x.title() for x in parts[1:])

        # 2. 从 SDK 获取
        prop = self._raw.GetProperty(camel_name)
        if prop is None:
            prop = self._raw.GetProperty(name)  # 备用尝试原始名

        if prop is None:
            raise AttributeError(f"'{self.type_name}' has no property '{name}'")

        # 3. 处理并缓存结果
        if prop.IsList:
            result = [ElementFactory.create(v, self.ctx) for v in prop.GetValues()]
        else:
            val = prop.Value
            if hasattr(val, "Type") or hasattr(val, "ID"):
                result = ElementFactory.create(val, self.ctx)
            elif isinstance(val, str):
                result = val.replace("\r\n", "\\n").strip()
            else:
                result = val

        self._cache[name] = result
        return result

    def get_summary(self):
        """[多态方法] 默认摘要实现"""
        name_val = ""
        try:
            name_val = self.name
        except:
            pass
        return f"[{self.type_name}] {name_val}".strip()

    def __str__(self):
        return self.get_summary()

#endregion

#region 2. 类型定义 (Wrapper Classes)

#region 2.1 Projects
@MendixMap("Projects$Module")
class Projects_Module(MendixElement):
    def get_domain_model(self):
        raw_dm = next(iter(self._raw.GetUnitsOfType("DomainModels$DomainModel")), None)
        return ElementFactory.create(raw_dm, self.ctx)

    def find_microflow(self, mf_name):
        raw_mf = next(
            (
                m
                for m in self._raw.GetUnitsOfType("Microflows$Microflow")
                if m.Name == mf_name
            ),
            None,
        )
        return ElementFactory.create(raw_mf, self.ctx)
#endregion
#region 2.1 DomainModels
@MendixMap("DomainModels$Entity")
class DomainModels_Entity(MendixElement):
    def is_persistable(self):
        gen = self.generalization
        if not gen.is_valid:
            return True  # 默认持久化
        # 如果是 NoGeneralization，看其自身的 persistable 属性
        if gen.type_name == "NoGeneralization":
            return gen.persistable
        # 如果是继承，递归看父类
        parent_qname = gen.generalization
        parent = self.ctx.find_entity_by_qname(parent_qname)
        return parent.is_persistable() if parent and parent.is_valid else True

@MendixMap("DomainModels$Association")
class DomainModels_Association(MendixElement):
    def get_info(self, lookup):
        p_name = lookup.get(str(self.parent), "Unknown")
        c_name = lookup.get(str(self.child), "Unknown")
        return f"- [Assoc] {self.name}: {p_name} -> {c_name} [Type:{self.type}, Owner:{self.owner}]"

@MendixMap("DomainModels$CrossAssociation")
class DomainModels_CrossAssociation(MendixElement):
    def get_info(self, lookup):
        p_name = lookup.get(str(self.parent), "Unknown")
        # CrossAssociation 的 child 属性通常已经是字符串全名
        return f"- [Cross] {self.name}: {p_name} -> {self.child} [Type:{self.type}, Owner:{self.owner}]"

@MendixMap("DomainModels$AssociationOwner")
class DomainModels_AssociationOwner(MendixElement):
    def __str__(self): return self.type_name

@MendixMap("DomainModels$AssociationCapabilities")
class DomainModels_AssociationCapabilities(MendixElement):
    def __str__(self): return self.type_name

# --- 属性类型定义 (Attribute Types) ---
@MendixMap("DomainModels$Attribute")
class DomainModels_Attribute(MendixElement):
    def get_summary(self):
        doc = f" // {self.documentation}" if self.documentation else ""
        return f"- {self.name}: {self.type}{doc}"


@MendixMap("DomainModels$EnumerationAttributeType")
class DomainModels_EnumerationAttributeType(MendixElement):
    def __str__(self):
        # enumeration 是属性，返回枚举的全名
        return f"Enum({self.enumeration})"


@MendixMap("DomainModels$StringAttributeType")
class DomainModels_StringAttributeType(MendixElement):
    def __str__(self):
        return f"String({self.length if self.length > 0 else 'Unlimited'})"


@MendixMap("DomainModels$IntegerAttributeType")
class DomainModels_IntegerAttributeType(MendixElement):
    def __str__(self):
        return "Integer"


@MendixMap("DomainModels$DateTimeAttributeType")
class DomainModels_DateTimeAttributeType(MendixElement):
    def __str__(self):
        return "DateTime"


@MendixMap("DomainModels$BooleanAttributeType")
class DomainModels_BooleanAttributeType(MendixElement):
    def __str__(self):
        return "Boolean"


@MendixMap("DomainModels$DecimalAttributeType")
class DomainModels_DecimalAttributeType(MendixElement):
    def __str__(self):
        return "Decimal"


@MendixMap("DomainModels$LongAttributeType")
class DomainModels_LongAttributeType(MendixElement):
    def __str__(self):
        return "Long"
#endregion
#region 2.1 Microflows
@MendixMap("Microflows$ActionActivity")
class Microflows_ActionActivity(MendixElement):
    def get_summary(self):
        # Activity 代理其内部 Action 的摘要
        return self.action.get_summary()


@MendixMap("Microflows$MicroflowCallAction")
class Microflows_MicroflowCallAction(MendixElement):
    def get_summary(self):
        call = self.microflow_call
        target = call.microflow if call else "Unknown"

        # 解析参数映射
        params = []
        if call and call.parameter_mappings:
            for m in call.parameter_mappings:
                p_name = m.parameter.split(".")[-1]  # 只取参数名
                params.append(f"{p_name}={m.argument}")
        param_str = f"({', '.join(params)})" if params else "()"

        out = f" -> ${self.output_variable_name}" if self.use_return_variable else ""
        return f"⚡ Call: {target}{param_str}{out}"


@MendixMap("Microflows$RetrieveAction")
class Microflows_RetrieveAction(MendixElement):
    def get_summary(self):
        src = self.retrieve_source
        entity = getattr(src, "entity", "Unknown")
        xpath = getattr(src, "x_path_constraint", "")
        xpath_str = f" [{xpath}]" if xpath else ""
        return f"🔍 Retrieve: {entity}{xpath_str} -> ${self.output_variable_name}"


@MendixMap("Microflows$CreateVariableAction")
class Microflows_CreateVariableAction(MendixElement):
    def get_summary(self):
        value_format = self.initial_value.replace("\n", "\\n")
        return f"💎 Create: ${self.variable_name} ({self.variable_type}) = {value_format}"


@MendixMap("Microflows$ChangeVariableAction")
class Microflows_ChangeVariableAction(MendixElement):
    def get_summary(self):
        return f"📝 Change: ${self.variable_name} = {self.value}"


@MendixMap("Microflows$ExclusiveSplit")
class Microflows_ExclusiveSplit(MendixElement):
    def get_summary(self):
        expr = self.split_condition.expression
        caption = f" [{self.caption}]" if self.caption and self.caption != expr else ""
        return f"❓ Split{caption}: {expr}"


@MendixMap("Microflows$EndEvent")
class Microflows_EndEvent(MendixElement):
    def get_summary(self):
        ret = f" (Return: {self.return_value})" if self.return_value else ""
        return f"🛑 End{ret}"

#endregion
#region 2.1 DataTypes
# --- 数据类型定义 ---
@MendixMap("DataTypes$StringType")
class DataTypes_StringType(MendixElement):
    def __str__(self):
        return "String"


@MendixMap("DataTypes$VoidType")
class DataTypes_VoidType(MendixElement):
    def __str__(self):
        return "Void"


@MendixMap("DataTypes$BooleanType")
class DataTypes_BooleanType(MendixElement):
    def __str__(self):
        return "Boolean"
#endregion

#region 2.1 Pages
#endregion

#region 2.1 Projects
#endregion

#endregion

#region 3. 业务逻辑层 (Business Logic)
class DomainModelAnalyzer:
    def __init__(self, context):
        self.ctx = context

    def execute(self, module_name):
        module = self.ctx.find_module(module_name)
        if not module: return
        
        self.ctx.log(f"# DOMAIN MODEL: {module.name}\n")
        dm = module.get_domain_model()
        if not dm.is_valid: return

        # 构建局部 Lookup Table，避免全局耦合
        id_map = {}

        # 1. 分析实体
        for ent in dm.entities:
            # 记录 ID 到全名的映射
            id_map[ent.id] = f"{module.name}.{ent.name}"
            
            p_tag = " [P]" if ent.is_persistable() else " [NP]"
            gen_info = f" extends {ent.generalization.generalization}" if ent.generalization.type_name == "Generalization" else ""
            self.ctx.log(f"## Entity: {ent.name}{p_tag}{gen_info}")
            
            if ent.documentation: self.ctx.log(f"> {ent.documentation}")
            for attr in ent.attributes:
                self.ctx.log(attr.get_summary(), indent=1)
            self.ctx.log("")

        # 2. 分析关联关系 (使用 get_info 传递查找表)
        if dm.associations:
            self.ctx.log("## Associations (Internal)")
            for assoc in dm.associations:
                self.ctx.log(assoc.get_info(id_map))
            self.ctx.log("")

        if dm.cross_associations:
            self.ctx.log("## Associations (Cross)")
            for assoc in dm.cross_associations:
                self.ctx.log(assoc.get_info(id_map))
            self.ctx.log("")

class MicroflowAnalyzer:
    def __init__(self, context):
        self.ctx = context

    def execute(self, module_name, mf_name):
        module = self.ctx.find_module(module_name)
        if not module:
            return
        mf = module.find_microflow(mf_name)
        if not mf.is_valid:
            return

        # 修改点1：打印全名
        self.ctx.log(f"# MICROFLOW: {module_name}.{mf.name}\n'''")

        nodes = {obj.id: obj for obj in mf.object_collection.objects}
        adj = {}
        for flow in mf.flows:
            src, dst = str(flow.origin), str(flow.destination)
            if src not in adj:
                adj[src] = []
            adj[src].append((flow, dst))

        start_node = next(
            (n for n in nodes.values() if "StartEvent" in n.type_name), None
        )
        if not start_node:
            return

        stack = [(start_node.id, 0, "")]
        visited = set()

        while stack:
            node_id, indent, flow_label = stack.pop()
            node = nodes.get(node_id)
            if not node:
                continue

            label_str = f"--({flow_label})--> " if flow_label else ""
            self.ctx.log(f"{label_str}{node.get_summary()}", indent=indent)

            if node_id in visited:
                self.ctx.log("└─ (Jump/Loop)", indent=indent + 1)
                continue
            visited.add(node_id)

            out_flows = adj.get(node_id, [])
            # 修改点2：同一 flow 不增加缩进，只有分叉(Condition)才增加
            has_branches = len(out_flows) > 1

            for flow, target_id in reversed(out_flows):
                case_val = ""
                if has_branches and len(flow.case_values) > 0:
                    cv = flow.case_values[0]
                    case_val = getattr(cv, "value", cv.type_name)

                # 如果是单线流，indent不变；如果是分叉流，indent+1
                new_indent = indent + 1 if has_branches else indent
                stack.append((target_id, new_indent, case_val))

        self.ctx.log(f"'''")

#endregion

#region 4. 执行入口 (Execution)
try:
    PostMessage("backend:clear", "")
    ctx = MendixContext(currentApp, root)

    # 分析领域模型
    DomainModelAnalyzer(ctx).execute("AmazonBedrockConnector")  # 替换为你的模块名

    # 分析微流
    MicroflowAnalyzer(ctx).execute(
        "AltairIntegration", "Tool_SparqlConverter"
    )  # 替换为你的微流

    # --- 获取分析报告内容 ---
    final_report = ctx.flush_logs()

    # --- 保存并打开文件 ---
    try:
        # 1. 构建文件路径 (用户根目录/Mendix_Report.md)
        user_home = os.path.expanduser("~")
        file_path = os.path.join(user_home, "Mendix_Analysis_Report.md")

        # 2. 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(final_report)

        PostMessage("backend:info", f"✅ Report saved to: {file_path}")

        # 3. 使用系统默认程序打开文件 (仅限 Windows)
        if os.name == "nt":
            os.startfile(file_path)
        else:
            # 兼容其他系统(如果适用)
            import subprocess

            subprocess.call(
                ("open" if os.name == "posix" else "start", file_path), shell=True
            )

    except Exception as file_err:
        PostMessage("backend:error", f"File operation failed: {str(file_err)}")

    # 依然在 Studio Pro 后端控制台打印一份
    PostMessage("backend:info", final_report)

except Exception as e:
    PostMessage("backend:error", f"Error: {str(e)}\n{traceback.format_exc()}")
#endregion