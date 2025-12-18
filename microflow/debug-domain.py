from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType
import clr
import re

clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# ==========================================
# 1. 基础工具函数
# ==========================================
log_buffer = []


def log_line(msg):
    log_buffer.append(msg)


def safe_str(val):
    if val is None:
        return ""
    # 将实际的换行符替换为 "\n" 字符串，保持单行打印但保留格式
    return str(val).replace("\r\n", "\\n").replace("\n", "\\n").strip()


# 【新增】安全获取属性值，避免 NoneType 报错
def safe_get(node, prop_name):
    if node is None:
        return None
    prop = node.GetProperty(prop_name)
    return prop.Value if prop else None


# 【新增】安全获取列表属性
def safe_get_list(node, prop_name):
    if node is None:
        return []
    prop = node.GetProperty(prop_name)
    if prop and prop.IsList:
        return list(prop.GetValues())
    return []


def get_doc(obj):
    """提取文档并清理格式"""
    doc_val = safe_get(obj, "documentation")
    if doc_val:
        return f"  // {safe_str(doc_val)}"
    return ""


def find_entity_by_qname(qualified_name):
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
        target_module = None
        # 遍历所有模块寻找
        all_modules = list(root.GetUnitsOfType("Projects$Module"))
        for m in all_modules:
            if m.Name == mod_name:
                target_module = m
                break

        if not target_module:
            return None

        # 2. 获取该模块的 DomainModel
        dm_units = target_module.GetUnitsOfType("DomainModels$DomainModel")
        dm = next(iter(dm_units), None)
        if not dm:
            return None

        # 3. 在 DomainModel 中查找实体
        dm_entities = safe_get_list(dm, "entities")
        for e in dm_entities:
            if e.Name == ent_name:
                return e

    except Exception as e:
        # print(f"Lookup failed for {qualified_name}: {e}")
        pass

    return None


def is_entity_persistable(entity):
    """递归判断实体是否可持久化"""
    gen_obj = safe_get(entity, "generalization")
    if not gen_obj:
        return True

    gen_type = str(gen_obj.Type)
    # 如果没有继承，直接看本身的 persistable 属性
    if "NoGeneralization" in gen_type:
        return safe_get(gen_obj, "persistable")

    # 如果有继承，递归查找父实体
    if "Generalization" in gen_type:
        parent_entity_qname = safe_get(gen_obj, "generalization")
        parent_entity = find_entity_by_qname(parent_entity_qname)
        if parent_entity:
            return is_entity_persistable(parent_entity)

    return True


# ==========================================
# 2. 类型解析器
# ==========================================
def parse_attribute_type(attr_obj):
    try:
        type_obj = safe_get(attr_obj, "type")
        if not type_obj:
            return "UnknownType"

        type_meta = type_obj.Type.split("$")[-1]  # e.g., StringAttributeType

        details = ""

        # 字符串：提取长度
        if "String" in type_meta:
            length = safe_get(type_obj, "length")
            details = f"({length if length and length > 0 else 'Unlimited'})"

        # 枚举：提取枚举名称
        elif "Enumeration" in type_meta:
            enum_ref = safe_get(type_obj, "enumeration")
            if enum_ref:
                # 【修改】安全获取 Name，防止 enum_ref 为字符串
                enum_name = (
                    enum_ref.Name if hasattr(enum_ref, "Name") else str(enum_ref)
                )
                details = f"<{enum_name}>"
            else:
                details = "<Unknown>"

        # 数值/其他
        elif "Integer" in type_meta:
            details = "(Int)"
        elif "Long" in type_meta:
            details = "(Long)"
        elif "Decimal" in type_meta:
            details = "(Dec)"
        elif "Boolean" in type_meta:
            details = "(Bool)"
        elif "DateTime" in type_meta:
            details = "(Date)"
        elif "AutoNumber" in type_meta:
            details = "(AutoNum)"

        base_type = type_meta.replace("AttributeType", "")
        return f"{base_type}{details}"
    except Exception as e:
        return f"TypeErr({e})"


def get_default_value(attr_obj):
    try:
        val_obj = safe_get(attr_obj, "value")
        if not val_obj:
            return ""

        # StoredValue 通常包含 defaultValue 属性
        default_val = safe_get(val_obj, "defaultValue")
        if default_val:
            return f" = {safe_str(default_val)}"
    except:
        pass
    return ""


# ==========================================
# 3. 核心：解析领域模型
# ==========================================
# 【修改】参数改为直接接收 domain_model 对象
def analyze_domain_model(dm, module_name):
    if not dm:
        log_line("  No Domain Model provided.")
        return

    # 用于 ID 到 名称 的映射 (GUID -> Module.Entity)
    entity_lookup = {}

    # --- A. 解析实体 (Entities) ---
    entities = safe_get_list(dm, "entities")
    log_line(f"  Entities ({len(entities)} found):")

    # --- 在 analyze_domain_model 内部，替换实体循环中的持久化和继承逻辑 ---
    for entity in entities:
        e_name = entity.Name
        e_id = entity.ID.ToString()
        entity_lookup[e_id] = f"{module_name}.{e_name}"

        # 1. 使用递归函数判断持久化状态
        is_persistable = is_entity_persistable(entity)
        persist_tag = "[Persistable]" if is_persistable else "[Non-Persistable]"

        # 2. 解析继承 (Generalization) - 仅用于显示父类名称
        gen_info = ""
        gen_obj = safe_get(entity, "generalization")
        if gen_obj:
            gen_type = gen_obj.Type.split("$")[-1]
            if "Generalization" in gen_type:
                parent = safe_get(gen_obj, "generalization")
                if parent:
                    p_name = parent.Name if hasattr(parent, "Name") else str(parent)
                    gen_info = f" extends {p_name}"

        e_doc = get_doc(entity)
        log_line(f"\n    [Entity] {e_name} {persist_tag}{gen_info}{e_doc}")

        # 解析属性
        attributes = safe_get_list(entity, "attributes")
        for attr in attributes:
            a_name = attr.Name
            a_type = parse_attribute_type(attr)
            a_def = get_default_value(attr)
            a_doc = get_doc(attr)

            log_line(f"      - {a_name}: {a_type}{a_def}{a_doc}")

    # --- B. 解析关联 (Associations) ---
    associations = safe_get_list(dm, "associations")
    cross_assocs = safe_get_list(dm, "crossAssociations")
    associations.extend(cross_assocs)

    # --- 在 analyze_domain_model 内部，替换关联解析循环 ---
    if associations:
        log_line(f"\n  Associations ({len(associations)} found):")
        for assoc in associations:
            try:
                # 获取关联两端的引用对象
                p_ref = safe_get(assoc, "parent")
                c_ref = safe_get(assoc, "child")

                # 优先获取 QualifiedName (例如 "System.User")，如果拿不到则查表或显示 GUID
                p_name = getattr(
                    p_ref, "QualifiedName", entity_lookup.get(str(p_ref), str(p_ref))
                )
                c_name = getattr(
                    c_ref, "QualifiedName", entity_lookup.get(str(c_ref), str(c_ref))
                )

                # 类型和拥有者
                raw_type = str(safe_get(assoc, "type") or "Unknown")
                type_symbol = "<->" if "ReferenceSet" not in raw_type else "<==>"
                owner = str(safe_get(assoc, "owner") or "?")

                log_line(
                    f"    [Rel] {assoc.Name}: (Parent) {p_name} {type_symbol} (Child) {c_name} [Owner: {owner}]"
                )
            except Exception as e:
                log_line(f"    [Rel] Error parsing association: {e}")


# ==========================================
# 4. 主程序
# ==========================================
PostMessage("backend:clear", "")

unit = root
all_modules = list(unit.GetUnitsOfType("Projects$Module"))
target_module_name = "AmazonBedrockConnector"

# 1. 查找指定模块
target_module = next((u for u in all_modules if u.Name == target_module_name), None)

if target_module:
    log_line(f"DOMAIN MODEL DSL EXTRACT: {target_module.Name}")
    log_line("=" * 80)

    # 2. 【关键修改】在模块内查找 DomainModel 单元，而不是读取属性
    dm_units = target_module.GetUnitsOfType("DomainModels$DomainModel")
    target_dm = next(iter(dm_units), None)

    if target_dm:
        try:
            analyze_domain_model(target_dm, target_module.Name)
        except Exception as e:
            log_line(f"Fatal Error analyzing domain model: {e}")
            import traceback

            log_line(traceback.format_exc())
    else:
        log_line(f"  No Domain Model unit found inside module '{target_module_name}'.")

    log_line("=" * 80)
    PostMessage("backend:info", "\n".join(log_buffer))
else:
    PostMessage("backend:error", f"Module '{target_module_name}' not found.")
