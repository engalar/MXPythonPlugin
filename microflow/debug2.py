import clr
import traceback
from System import Exception as SystemException

clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType

# ==============================================================================
# 1. CORE FRAMEWORK: 核心框架 (动态代理 + 注册表工厂)
# ==============================================================================

# 全局类型注册表: "MendixTypeString" -> PythonClass
_MENDIX_TYPE_REGISTRY = {}


def MendixMap(mendix_type_str):
    """
    [装饰器] 将 Python 类注册到工厂，绑定特定的 Mendix SDK 类型。
    """

    def decorator(cls):
        _MENDIX_TYPE_REGISTRY[mendix_type_str] = cls
        return cls

    return decorator


class MendixContext:
    def __init__(self, root_node):
        self.root = root_node
        self.log_buffer = []

    def log(self, msg, indent=0):
        self.log_buffer.append(f"{'  ' * indent}{msg}")

    def flush_logs(self):
        return "\n".join(self.log_buffer)

    def find_module(self, module_name):
        """查找模块并包装"""
        modules = list(self.root.GetUnitsOfType("Projects$Module"))
        raw = next((m for m in modules if m.Name == module_name), None)
        return ElementFactory.create(raw, self) if raw else None

    def find_entity_by_qname(self, qname):
        """根据 'Module.Entity' 字符串查找对象"""
        if not qname or "." not in qname:
            return None
        mod_name, ent_name = qname.split(".", 1)

        module = self.find_module(mod_name)
        if not module or not module.is_valid:
            return None

        # 注意：这里调用的是封装后的 domain_model 方法
        dm = module.get_domain_model()
        if not dm.is_valid:
            return None

        # 遍历实体 (属性访问已简化为 .entities)
        for ent in dm.entities:
            if ent.name == ent_name:
                return ent
        return None


class ElementFactory:
    """
    [工厂模式 - 终极版] 基于注册表查表，符合开闭原则。
    """

    @staticmethod
    def create(raw_obj, context):
        if raw_obj is None:
            return MendixElement(None, context)

        # 处理 Python 原生基础类型 (int, str, bool)
        if isinstance(raw_obj, (str, int, float, bool)):
            return raw_obj

        # 获取类型字符串
        try:
            full_type = raw_obj.Type  # e.g. "DomainModels$Entity"
        except AttributeError:
            # 无法识别的对象，返回基础封装
            return MendixElement(raw_obj, context)

        # 查表实例化 (如果未注册，回退到 MendixElement)
        target_cls = _MENDIX_TYPE_REGISTRY.get(full_type, MendixElement)
        return target_cls(raw_obj, context)


class MendixElement:
    """
    [通用基类] 包含动态属性映射魔法。
    """

    def __init__(self, raw_obj, context):
        self._raw = raw_obj
        self.ctx = context

    @property
    def is_valid(self):
        return self._raw is not None

    @property
    def id(self):
        return self._raw.ID.ToString() if self.is_valid else None

    @property
    def type_name(self):
        if not self.is_valid:
            return "Unknown"
        return self._raw.Type.split("$")[-1]

    @property
    def full_type(self):
        return self._raw.Type if self.is_valid else "Unknown"

    def __getattr__(self, name):
        """
        核心逻辑：将 snake_case 属性访问自动映射为 Mendix CamelCase 属性获取。
        例如: entity.domain_model -> raw.GetProperty("domainModel")
        """
        if not self.is_valid:
            return None

        # 1. 转换命名: cross_associations -> crossAssociations
        components = name.split("_")
        camel_name = components[0] + "".join(x.title() for x in components[1:])

        # 2. 调用 SDK
        prop = self._raw.GetProperty(camel_name)

        # 容错：如果 camelCase 找不到，尝试直接用原始名称
        if prop is None:
            prop = self._raw.GetProperty(name)

        # 如果还是找不到，返回 None (或者 raise AttributeError)
        if prop is None:
            raise AttributeError(
                f"'{self.type_name}' object has no attribute '{name}' (mapped to '{camel_name}')"
            )

        # 3. 自动装箱
        if prop.IsList:
            return [ElementFactory.create(v, self.ctx) for v in prop.GetValues()]

        val = prop.Value

        # 如果是 SDK 对象，递归封装
        if hasattr(val, "Type") or hasattr(val, "ID"):
            return ElementFactory.create(val, self.ctx)

        # 如果是字符串，清理换行
        if isinstance(val, str):
            return val.replace("\r\n", "\\n").replace("\n", "\\n").strip()

        return val

    def __str__(self):
        # 尝试显示名字，没有则显示类型和ID
        n = getattr(self, "name", "")
        return f"<{self.type_name}:{n} ID={self.id}>"


# ==============================================================================
# 2. WRAPPER CLASSES: 具体类型定义 (使用 @MendixMap)
# ==============================================================================


@MendixMap("Projects$Module")
class Projects_Module(MendixElement):
    def get_domain_model(self):
        # 特殊逻辑：DomainModel 不是属性，而是 Unit，需保留此方法
        dm_units = self._raw.GetUnitsOfType("DomainModels$DomainModel")
        raw_dm = next(iter(dm_units), None)
        return ElementFactory.create(raw_dm, self.ctx)

    def find_microflow(self, mf_name):
        mf_units = self._raw.GetUnitsOfType("Microflows$Microflow")
        raw_mf = next((m for m in mf_units if m.Name == mf_name), None)
        return ElementFactory.create(raw_mf, self.ctx)


@MendixMap("DomainModels$DomainModel")
class DomainModels_DomainModel(MendixElement):
    # 完全依靠 __getattr__ 处理 .entities, .associations 等
    pass


# --- 关联关系 ---


class BaseAssociation(MendixElement):
    """关联基类，包含通用逻辑"""

    def get_info(self, entity_lookup):
        p_guid = str(self.parent)  # 使用 .parent 自动映射
        p_name = entity_lookup.get(p_guid, "UnknownParent")
        c_name = self.get_child_name(entity_lookup)

        # 使用 .type, .owner 自动映射
        arrow = "<->" if "Reference" == self.type else "<==>"
        return f"{self.name}: {p_name} {arrow} {c_name} [Type:{self.type} | Owner:{self.owner}]"


@MendixMap("DomainModels$Association")
class DomainModels_Association(BaseAssociation):
    def get_child_name(self, entity_lookup):
        # Association 存储的是 Child 的 GUID
        c_guid = str(self.child)
        return entity_lookup.get(c_guid, f"UnknownChild({c_guid})")


@MendixMap("DomainModels$CrossAssociation")
class DomainModels_CrossAssociation(BaseAssociation):
    def get_child_name(self, entity_lookup):
        # CrossAssociation 存储的是 Child 的字符串全名
        return self.child


# --- 实体与属性 ---


@MendixMap("DomainModels$Entity")
class DomainModels_Entity(MendixElement):
    pass  # .name, .attributes, .generalization 均自动处理


@MendixMap("DomainModels$Attribute")
class DomainModels_Attribute(MendixElement):
    def get_type_summary(self):
        # 使用 .type 访问属性
        type_obj = self.type
        return str(type_obj) if type_obj.is_valid else "UnknownType"


# 属性类型
@MendixMap("DomainModels$EnumerationAttributeType")
class DomainModels_EnumerationAttributeType(MendixElement):
    def __str__(self):
        return f"Enumeration[{self.enumeration}]"  # .enumeration


@MendixMap("DomainModels$StringAttributeType")
class DomainModels_StringAttributeType(MendixElement):
    def __str__(self):
        limit = "Unlimited" if self.length == 0 else f"Length: {self.length}"
        return f"String[{limit}]"  # .length


@MendixMap("DomainModels$DateTimeAttributeType")
class DomainModels_DateTimeAttributeType(MendixElement):
    def __str__(self):
        loc = "Localized" if self.localize_date else "UTC"  # .localize
        return f"DateTime[{loc}]"


@MendixMap("DomainModels$BooleanAttributeType")
class DomainModels_BooleanAttributeType(MendixElement):
    def __str__(self):
        return "Boolean"


@MendixMap("DomainModels$IntegerAttributeType")
class DomainModels_IntegerAttributeType(MendixElement):
    def __str__(self):
        return "Integer"


@MendixMap("DomainModels$LongAttributeType")
class DomainModels_LongAttributeType(MendixElement):
    def __str__(self):
        return "Long"


@MendixMap("DomainModels$DecimalAttributeType")
class DomainModels_DecimalAttributeType(MendixElement):
    def __str__(self):
        return f"Decimal"


@MendixMap("DomainModels$AutoNumberAttributeType")
class DomainModels_AutoNumberAttributeType(MendixElement):
    def __str__(self):
        return "AutoNumber"


@MendixMap("DomainModels$BinaryAttributeType")
class DomainModels_BinaryAttributeType(MendixElement):
    def __str__(self):
        return "Binary"


# --- 泛化 (Generalization) ---


class GeneralizationBase(MendixElement):
    def is_persistable(self):
        return False


@MendixMap("DomainModels$NoGeneralization")
class DomainModels_NoGeneralization(GeneralizationBase):
    def is_persistable(self):
        return self.persistable  # 自动映射


@MendixMap("DomainModels$Generalization")
class DomainModels_Generalization(GeneralizationBase):
    def is_persistable(self):
        # 这里 logic 比较复杂，保留显式代码，但利用属性访问
        qname = self.generalization  # 父实体全名
        if qname:
            parent_entity = self.ctx.find_entity_by_qname(qname)
            if parent_entity and parent_entity.is_valid:
                parent_gen = parent_entity.generalization
                if parent_gen.is_valid:
                    return parent_gen.is_persistable()
        return False


# --- 微流 ---


@MendixMap("Microflows$Microflow")
class Microflows_Microflow(MendixElement):
    # .object_collection, .flows 等由基类接管
    # .object_collection.objects
    pass


@MendixMap("Microflows$ExclusiveSplit")
class Microflows_ExclusiveSplit(MendixElement):
    # .caption:string
    # .split_condition.expression
    pass


@MendixMap("Microflows$ActionActivity")
class Microflows_ActionActivity(MendixElement):
    # .caption:string
    # .documentation:string
    # .action:Microflows$MicroflowCallAction
    pass


@MendixMap("Microflows$MicroflowCallAction")
class Microflows_MicroflowCallAction(MendixElement):
    # .errorHandlingType
    # .useReturnVariable
    # .outputVarableName
    # .microflowCall:Microflows$MicroflowCall
    pass


@MendixMap("Microflows$MicroflowCall")
class Microflows_MicroflowCall(MendixElement):
    # .parameterMappings:Microflows$MicroflowParameterMapping
    # .microflow:string
    pass


@MendixMap("Microflows$MicroflowParameterMapping")
class Microflows_MicroflowParameterMapping(MendixElement):
    # .argument
    # .parameter
    pass


@MendixMap("Microflows$MicroflowParameterObject")
class Microflows_MicroflowParameterObject(MendixElement):
    """
    get from Microflows_Microflow.object_collection.objects[]
    """

    # name
    # document
    # is_required
    # default_value
    # variable_type
    pass


@MendixMap("DataTypes$StringType")
class DataTypes_StringType(MendixElement):
    pass


# ==============================================================================
# 3. LOGIC LAYER: 业务分析器 (已更新为使用新语法)
# ==============================================================================


class DomainModelAnalyzer:
    def __init__(self, context):
        self.ctx = context
        self.entity_lookup = {}

    def execute(self, module_name):
        module = self.ctx.find_module(module_name)
        if not module or not module.is_valid:
            self.ctx.log(f"[Error] Module '{module_name}' not found.")
            return

        self.ctx.log(f"DOMAIN ANALYSIS: {module.name}")
        self.ctx.log("-" * 60)

        # 1. 访问 DomainModel
        dm = module.get_domain_model()
        if not dm.is_valid:
            return

        # 2. 分析实体 (使用 .entities)
        entities = dm.entities
        self.ctx.log(f"Entities ({len(entities)} found):")

        for e in entities:
            self.entity_lookup[e.id] = f"{module.name}.{e.name}"

            # 使用 .generalization
            gen = e.generalization
            is_persist = gen.is_persistable() if gen.is_valid else False
            tag = "[Persistable]" if is_persist else "[Non-Persistable]"

            # 使用 .documentation
            parent_info = ""
            if gen.type_name == "Generalization":
                # Generalization 对象有一个同名属性 generalization 存储父实体全名
                parent_info = f" extends {gen.generalization}"

            doc_str = f" // {e.documentation}" if e.documentation else ""
            self.ctx.log(f"  [Entity] {e.name} {tag}{parent_info}{doc_str}")

            # 遍历属性 (使用 .attributes)
            for attr in e.attributes:
                # 链式访问: attr.value.default_value
                def_val_obj = attr.value
                def_val = def_val_obj.default_value if def_val_obj.is_valid else None
                def_str = f" = {def_val}" if def_val else ""

                doc_suffix = f" // {attr.documentation}" if attr.documentation else ""
                self.ctx.log(
                    f"    - {attr.name}: {attr.get_type_summary()}{def_str}{doc_suffix}"
                )

        # 3. 分析关联 (使用 .associations 和 .cross_associations)
        internal = dm.associations
        cross = dm.cross_associations

        if internal or cross:
            self.ctx.log(
                f"\nAssociations (Internal: {len(internal)}, Cross: {len(cross)}):"
            )
            for a in internal:
                self.ctx.log(f"    {a.get_info(self.entity_lookup)}")
            for a in cross:
                self.ctx.log(f"    {a.get_info(self.entity_lookup)}")

        self.ctx.log("=" * 60)


class MicroflowAnalyzer:
    def __init__(self, context):
        self.ctx = context
        self.visited = set()
        self.node_map = {}
        self.adj_list = {}

    def execute(self, module_name, mf_name):
        module = self.ctx.find_module(module_name)
        if not module:
            return

        mf = module.find_microflow(mf_name)
        if not mf.is_valid:
            self.ctx.log(f"Microflow '{mf_name}' not found.")
            return

        self.ctx.log(f"MICROFLOW ANALYSIS: {mf.name}")
        self.ctx.log("-" * 60)

        # 构建图: 使用 .object_collection.objects
        objects = mf.object_collection.objects
        self.node_map = {obj.id: obj for obj in objects}

        # 构建连接: 使用 .flows
        for flow in mf.flows:
            # origin / destination 是引用对象
            org = str(flow.origin)
            dst = str(flow.destination)
            if org and dst:
                if org not in self.adj_list:
                    self.adj_list[org] = []
                self.adj_list[org].append((flow, dst))

        # 寻找起点
        start = next((n for n in objects if "StartEvent" in n.type_name), None)
        if start:
            self._traverse(start.id)
        else:
            self.ctx.log("Error: StartEvent not found.")
        self.ctx.log("=" * 60)

    def _traverse(self, node_id, prefix=""):
        if node_id in self.visited:
            self.ctx.log(f"{prefix}(Loop)")
            return
        self.visited.add(node_id)

        node = self.node_map.get(node_id)
        if not node:
            return

        self.ctx.log(f"{prefix}{self._get_node_details(node)}")

        outgoing = self.adj_list.get(node_id, [])
        for flow, target_id in outgoing:
            label = ""
            # case_value 是对象
            case_val = (
                flow.case_values[0] if len(flow.case_values) > 0 else None
            )  # 为空，或者仅有一个 Microflows$NoCase Microflows$EnumerationCase.value [String true or false]
            if (
                case_val
                and case_val.is_valid
                and case_val.full_type == "Microflows$EnumerationCase"
            ):
                # value 是属性
                val = case_val.value
                label = f"--[{val if val else case_val.type_name}]--> "
            elif len(outgoing) > 1:
                label = "--> "

            if len(outgoing) > 1:
                self.ctx.log(f"{prefix}  {label}")
                self._traverse(target_id, prefix + "    ")
            else:
                self._traverse(target_id, prefix)

    def _get_node_details(self, node):
        """完全使用动态属性访问的详情解析"""
        base_type = node.type_name
        summary = f"[{base_type}]"

        # 1. ActionActivity
        if "ActionActivity" in base_type:
            action = node.action  # 自动映射
            act_type = action.type_name
            summary = f"[{act_type}]"

            # A. MicroflowCall
            if "MicroflowCall" in act_type:
                mf_call = action.microflow_call
                t_name = mf_call.microflow
                summary += f" Target: {t_name}"

                # 处理参数映射
                mappings = mf_call.parameter_mappings
                if mappings:
                    params = []
                    for m in mappings:
                        # argument 是表达式字符串，parameter 是目标参数名
                        params.append(f"{m.parameter.split('.')[-1]}={m.argument}")
                    summary += f" ({', '.join(params)})"

                if action.output_variable_name:
                    summary += f" -> ${action.output_variable_name}"

            # B. Retrieve
            elif "Retrieve" in act_type:
                src = action.retrieve_source
                e_name = src.entity

                xpath = src.x_path_constraint
                summary += f" Entity: {e_name}"
                if xpath:
                    summary += f" | XPath: {xpath}"
                if action.output_variable_name:
                    summary += f" -> ${action.output_variable_name}"

            # C. CreateVariable
            elif "CreateVariable" in act_type:
                # initialValue 是 CodeSnippet 对象
                val = getattr(action.initial_value, "code", str(action.initial_value))
                summary += f" ${action.variable_name} = {val}"

            # D. ChangeVariable
            elif "ChangeVariable" in act_type:
                summary += f" ${action.variable_name} = {action.value}"

        # 2. EndEvent
        elif "EndEvent" in base_type:
            if node.return_value:
                summary += f" Return: {node.return_value}"

        # 3. Parameter
        elif "Parameter" in base_type:
            v_type = node.variable_type.type_name
            summary = f"[Parameter] {node.name} ({v_type})"

        # 4. ExclusiveSplit
        elif "ExclusiveSplit" in base_type:
            expr = node.split_condition.expression
            summary += f" ? {expr}"
            if node.caption and node.caption != expr:
                summary += f" ({node.caption})"

        return summary


# ==============================================================================
# 4. EXECUTION
# ==============================================================================
try:
    PostMessage("backend:clear", "")
    context = MendixContext(root)

    # 替换为实际的模块名称
    DomainModelAnalyzer(context).execute("AmazonBedrockConnector")

    # 替换为实际的微流
    MicroflowAnalyzer(context).execute("AltairIntegration", "Tool_SparqlConverter")

    PostMessage("backend:info", context.flush_logs())

except Exception as e:
    err_msg = f"Script Error: {str(e)}\n{traceback.format_exc()}"
    PostMessage("backend:error", err_msg)
