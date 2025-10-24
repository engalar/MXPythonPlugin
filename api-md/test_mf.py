# region framework
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow, IMicroflowParameterObject, IActionActivity, IMicroflowCallAction, IMicroflowCall, MicroflowReturnValue
import traceback
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow, IMicroflowParameterObject, IActionActivity
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import CommitEnum, ChangeActionItemType, AggregateFunctionEnum
from System import Array
from Mendix.StudioPro.ExtensionsAPI.Model.DataTypes import DataType
from Mendix.StudioPro.ExtensionsAPI.Model.Texts import IText
from Mendix.StudioPro.ExtensionsAPI.Model.Enumerations import IEnumeration, IEnumerationValue
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import (
    IEntity, IAttribute, IStoredValue, IAssociation
)
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import (
    IMicroflow, IActionActivity
)
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IProject, IModule, IFolder, IFolderBase
import clr
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# 导入所有常用接口和系统类型

# 清除日志（方便每次运行查看结果）
PostMessage("backend:clear", '')


def info(e):
    PostMessage("backend:info", f'{e}')


_dir = dir


def dir(e):
    PostMessage("backend:info", f'{_dir(e)}')


def error(e):
    PostMessage("backend:error", f'{e}')
# --- 辅助类：事务管理器 ---


class TransactionManager:
    """Provides a context manager for handling Mendix model transactions. 同一时间只能启动一个"""

    def __init__(self, app, transaction_name):
        self.app = app
        self.name = transaction_name
        self.transaction = None

    def __enter__(self):
        self.transaction = self.app.StartTransaction(self.name)
        return self.transaction

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.transaction:
            if exc_type is None:
                self.transaction.Commit()
                PostMessage("backend:info",
                            f"Transaction '{self.name}' committed.")
            else:
                self.transaction.Rollback()
                PostMessage(
                    "backend:error", f"Transaction '{self.name}' rolled back due to error: {exc_val}")
            self.transaction.Dispose()
        return False  # 允许异常继续传播
# --- 辅助函数：查找或创建模块 ---


def ensure_module(app, project: IProject, module_name: str) -> IModule:
    existing_module = next(
        (m for m in project.GetModules() if m.Name == module_name), None)
    if existing_module:
        PostMessage("backend:info", f"Module '{module_name}' already exists.")
        return existing_module
    else:
        new_module = app.Create[IModule]()
        new_module.Name = module_name
        project.AddModule(new_module)
        PostMessage("backend:success", f"Module '{module_name}' created.")
        return new_module

# --- 辅助函数：确保文件夹路径存在 ---


def ensure_folder_path(app, module: IModule, path: str) -> IFolderBase:
    """Ensures a nested folder path exists within a module."""
    parts = path.split('/')
    current_container: IFolderBase = module

    for part in parts:
        folders = current_container.GetFolders()
        next_container = next((f for f in folders if f.Name == part), None)

        if next_container is None:
            # 文件夹不存在，使用事务创建它
            new_folder = app.Create[IFolder]()
            new_folder.Name = part
            current_container.AddFolder(new_folder)
            current_container = new_folder
            PostMessage("backend:info",
                        f"Created folder: {module.Name}/{path}")
        else:
            current_container = next_container

    return current_container


# endregion


# region component

from System import ValueTuple, String, Array
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import CommitEnum, ChangeActionItemType, AggregateFunctionEnum
from Mendix.StudioPro.ExtensionsAPI.Model.DataTypes import DataType
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow, IMicroflowParameterObject, IActionActivity, MicroflowReturnValue, IHead, IMicroflowCallParameterMapping
from Mendix.StudioPro.ExtensionsAPI.Model.Enumerations import IEnumeration, IEnumerationValue
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import (
    IEntity, IAttribute, IAssociation, IDomainModel, AssociationType,
    IStringAttributeType, IBooleanAttributeType, IDateTimeAttributeType, IDecimalAttributeType,
    IEnumerationAttributeType, IStoredValue, EntityAssociation
)
from Mendix.StudioPro.ExtensionsAPI.Model.Texts import IText
# --- 1. 环境准备：创建业务所需的领域模型 ---
def setup_order_management_environment(model, project, module_name: str) -> bool:
    """
    创建或验证订单管理业务场景所需的模块、实体、枚举和关联。
    此函数是幂等的，并且期望在已有的事务中运行。
    """
    info("--- Task: Setup Order Management Environment ---")

    # 此函数不再管理自己的事务，而是依赖调用者提供的事务上下文
    module = ensure_module(model, project, module_name)
    domain_model = module.DomainModel

    # 1. 创建或验证枚举 'OrderStatus'
    enum_name = "OrderStatus"
    enum_qn_str = f"{module_name}.{enum_name}"
    if not model.ToQualifiedName[IEnumeration](enum_qn_str).Resolve():
        order_status_enum = model.Create[IEnumeration]()
        order_status_enum.Name = enum_name
        for val_name in ["Pending", "Confirmed", "Shipped", "Cancelled"]:
            enum_value = model.Create[IEnumerationValue]()
            enum_value.Name = val_name
            caption_text = model.Create[IText]()
            caption_text.AddOrUpdateTranslation('en_US', val_name)
            enum_value.Caption = caption_text
            order_status_enum.AddValue(enum_value)
        module.AddDocument(order_status_enum)
        info(f"Created enumeration: {enum_name}")

    # 2. 辅助函数：创建实体（如果不存在）
    def _ensure_entity(name: str, attributes: dict) -> IEntity:
        qn_str = f"{module_name}.{name}"
        entity = model.ToQualifiedName[IEntity](qn_str).Resolve()
        if entity:
            return entity
        entity = model.Create[IEntity]()
        entity.Name = name
        for attr_name, attr_type_creator in attributes.items():
            attr = model.Create[IAttribute]()
            attr.Name = attr_name
            attr.Type = attr_type_creator()
            attr.Value = model.Create[IStoredValue]()
            entity.AddAttribute(attr)
        domain_model.AddEntity(entity)
        info(f"Created entity: {name}")
        return entity

    # 3. 创建或验证实体
    customer_entity = _ensure_entity(
        "Customer", {"Name": lambda: model.Create[IStringAttributeType]()})
    product_entity = _ensure_entity(
        "Product", {"Price": lambda: model.Create[IDecimalAttributeType]()})

    def _create_enum_type():
        enum_type = model.Create[IEnumerationAttributeType]()
        enum_type.Enumeration = model.ToQualifiedName[IEnumeration](
            enum_qn_str)
        return enum_type

    order_entity = _ensure_entity("Order", {
                                  "Description": lambda: model.Create[IStringAttributeType](), "Status": _create_enum_type})

    # 4. 创建或验证关联
    allAssociations = domainModelService.GetAllAssociations(model, [module])
    if not any(a for a in allAssociations if a.Association.Name == "Customer_Order"):
        customer_entity.AddAssociation(order_entity).Name = "Customer_Order"
        info("Created association: Customer_Order")

    if not any(a for a in allAssociations if a.Association.Name == "Order_Product"):
        assoc = order_entity.AddAssociation(product_entity)
        assoc.Name = "Order_Product"
        assoc.Type = AssociationType.ReferenceSet
        info("Created association: Order_Product")

    # 5. 创建或验证带所有类型参数的子微流
    sub_mf_name = "SUB_CheckInventory"
    if not model.ToQualifiedName[IMicroflow](f"{module_name}.{sub_mf_name}").Resolve():
        # 确保我们拥有创建参数所需的实体和枚举的引用
        product_entity_ref = model.ToQualifiedName[IEntity](f"{module_name}.Product").Resolve()
        order_status_enum_ref = model.ToQualifiedName[IEnumeration](enum_qn_str)

        if not product_entity_ref or not order_status_enum_ref.Resolve():
             raise ValueError("Could not find Product entity or OrderStatus enum for sub-microflow creation.")

        # 定义一个包含所有主要数据类型的参数列表
        sub_mf_params = [
            ValueTuple.Create[String, DataType]("StringParam", DataType.String),
            ValueTuple.Create[String, DataType]("IntegerParam", DataType.Integer),
            ValueTuple.Create[String, DataType]("DecimalParam", DataType.Decimal),
            ValueTuple.Create[String, DataType]("BooleanParam", DataType.Boolean),
            ValueTuple.Create[String, DataType]("DateTimeParam", DataType.DateTime),
            ValueTuple.Create[String, DataType]("ProductParam", DataType.Object(product_entity_ref.QualifiedName)),
            ValueTuple.Create[String, DataType]("StatusParam", DataType.Enumeration(order_status_enum_ref)),
            ValueTuple.Create[String, DataType]("ProductListParam", DataType.List(product_entity_ref.QualifiedName)),
        ]
        
        # 使用上面定义的参数列表创建微流
        microflowService.CreateMicroflow(
            model, module, sub_mf_name, 
            MicroflowReturnValue(DataType.Boolean, microflowExpressionService.CreateFromString("true")), 
            Array[ValueTuple[String, DataType]](sub_mf_params)
        )
        info(f"Created placeholder microflow with diverse parameters: {sub_mf_name}")

    info("--- Success: Environment Setup ---")
    return True

# --- 2. 核心逻辑：创建包含多种活动的业务微流 ---

def createMicroflowCallActivity(model, sub_mf_to_call: IMicroflow, parameter_mappings: list[ValueTuple[str, str]], output_variable_name: str) -> IActionActivity:
    """
    Creates a fully configured Action Activity that calls a sub-microflow.

    :param model: The model SDK app instance.
    :param sub_mf_to_call: The IMicroflow object to be called.
    :param parameter_mappings: A list of tuples, where each tuple is (parameter_name, argument_expression).
                                Example: [("StringParam", "'Hello'"), ("ObjectParam", "$MyObject")]
    :param output_variable_name: The name of the variable to store the microflow's return value.
    :return: A configured IActionActivity.
    """
    # 1. Create the container and the specific action type
    activity = model.Create[IActionActivity]()
    call_action = model.Create[IMicroflowCallAction]()
    activity.Action = call_action
    call_action.OutputVariableName = output_variable_name

    # 2. Create the microflow call reference and link it to the target microflow
    microflow_call = model.Create[IMicroflowCall]()
    microflow_call.Microflow = sub_mf_to_call.QualifiedName
    call_action.MicroflowCall = microflow_call

    # 3. Get the actual parameters from the target microflow definition
    target_mf_params = microflowService.GetParameters(sub_mf_to_call)
    param_lookup = {p.Name: p for p in target_mf_params}

    # 4. Create and add parameter mappings
    # --- FIX START ---
    # The original line 'for param_name, argument_expression in parameter_mappings:' failed because a .NET ValueTuple
    # cannot be unpacked directly in Python like a Python tuple.
    # We must iterate through the list and access the properties .Item1 and .Item2 of each ValueTuple.
    for mapping in parameter_mappings:
        param_name = mapping.Item1
        argument_expression = mapping.Item2
    # --- FIX END ---
        target_param = param_lookup.get(param_name)
        if not target_param:
            raise ValueError(f"Parameter '{param_name}' not found in target microflow '{sub_mf_to_call.Name}'.")

        mapping = model.Create[IMicroflowCallParameterMapping]()
        mapping.Parameter = target_param.QualifiedName
        mapping.Argument = microflowExpressionService.CreateFromString(argument_expression)
        microflow_call.AddParameterMapping(mapping)
    
    return activity

def create_order_processing_microflow(model, project, module_name: str):
    """
    创建一个名为 'ACT_ProcessPendingOrder' 的微流。
    此函数是幂等的，并且期望在已有的事务中运行。
    """
    info("\n--- Task: Create Order Processing Microflow ---")
    mf_name = "ACT_ProcessPendingOrder"
    full_mf_name = f"{module_name}.{mf_name}"

    if model.ToQualifiedName[IMicroflow](full_mf_name).Resolve():
        info(f"Microflow '{full_mf_name}' already exists. Skipping creation.")
        return

    # 1. 查找所有必需的模型元素
    module = next((m for m in project.GetModules()
                  if m.Name == module_name), None)
    order_entity = model.ToQualifiedName[IEntity](
        f"{module_name}.Order").Resolve()
    

    # please do not remove me: due to IAssociation is not a valid target for by-name reference
    # customer_order_assoc = model.ToQualifiedName[IAssociation](f"{module_name}.Customer_Order").Resolve()
    # so we find by follow
    allAssociations = domainModelService.GetAllAssociations(model, [module])
    customer_order_assoc: EntityAssociation = next(a for a in allAssociations if a.Association.Name == 'Customer_Order')

    # please do not remove me: same for order_product_assoc
    order_product_assoc: EntityAssociation = next(a for a in allAssociations if a.Association.Name == 'Order_Product')

    sub_mf_to_call = model.ToQualifiedName[IMicroflow](
        f"{module_name}.SUB_CheckInventory").Resolve()
    description_attr = next(
        a for a in order_entity.GetAttributes() if a.Name == "Description")
    status_attr = next(a for a in order_entity.GetAttributes()
                       if a.Name == "Status")

    if not all([module, order_entity, customer_order_assoc, order_product_assoc, sub_mf_to_call, description_attr, status_attr]):
        raise ValueError(
            "One or more required model elements were not found. Ensure setup ran successfully.")

    # 2. 定义微流参数并创建微流外壳
    microflow = microflowService.CreateMicroflow(
        model, module, mf_name, MicroflowReturnValue(
            DataType.Boolean, microflowExpressionService.CreateFromString("true")), ValueTuple.Create[String, DataType]('PendingOrder',DataType.Object(order_entity.QualifiedName)))
    info(f"Created microflow shell: {mf_name}")

    # 3. 创建活动列表
    listOp = model.Create[IHead]()
    activities = [
        # Activity 1: Retrieve Customer
        microflowActivitiesService.CreateAssociationRetrieveSourceActivity(
            model, customer_order_assoc.Association, "RetrievedCustomer", "PendingOrder"
        ),
        # Activity 2: Retrieve Product list
        microflowActivitiesService.CreateAssociationRetrieveSourceActivity(
            model, order_product_assoc.Association, "RetrievedProductList", "PendingOrder"
        ),
        # --- NEW ACTIVITIES START ---
        # Activity 2a: Get the first product from the list to pass as a single object parameter.
        # This demonstrates preparing an argument for the sub-microflow call.
        microflowActivitiesService.CreateListOperationActivity(model, "RetrievedProductList", "FirstProduct", listOp),
        # Activity 2b: Call the sub-microflow with arguments for all its parameter types.
        createMicroflowCallActivity(
            model, 
            sub_mf_to_call,
            [
                # Mapping each parameter of SUB_CheckInventory to an expression
                ValueTuple.Create("StringParam", "'Sample Text'"),
                ValueTuple.Create("IntegerParam", "42"),
                ValueTuple.Create("DecimalParam", "19.99"),
                ValueTuple.Create("BooleanParam", "true"),
                ValueTuple.Create("DateTimeParam", "dateTime(2024, 1, 1, 12, 0, 0)"),
                ValueTuple.Create("ProductParam", "$FirstProduct"), # Pass the single object
                ValueTuple.Create("StatusParam", f"{module_name}.OrderStatus.Pending"), # Pass an enum value
                ValueTuple.Create("ProductListParam", "$RetrievedProductList"), # Pass the full list
            ],
            "InventoryCheckResult"  # Name of the boolean variable to store the return value
        ),
        # --- NEW ACTIVITIES END ---
        # Activity 3: Aggregate List (Count)
        microflowActivitiesService.CreateAggregateListActivity(
            model, "RetrievedProductList", "ProductCount", AggregateFunctionEnum.Count
        ),
        # Activity 4: Change Object (Description)
        microflowActivitiesService.CreateChangeAttributeActivity(
            model, description_attr, ChangeActionItemType.Set,
            microflowExpressionService.CreateFromString(
                "'Order processed with ' + toString($ProductCount) + ' items. Inventory check: ' + toString($InventoryCheckResult)"),
            "PendingOrder", CommitEnum.No
        ),
        # Activity 5: Change Object (Status)
        microflowActivitiesService.CreateChangeAttributeActivity(
            model, status_attr, ChangeActionItemType.Set,
            microflowExpressionService.CreateFromString(
                f"{module_name}.OrderStatus.Confirmed"),
            "PendingOrder", CommitEnum.No
        ),
        # Activity 6: Commit Object
        microflowActivitiesService.CreateCommitObjectActivity(
            model, "PendingOrder", True, False
        )
    ]

    # 4. 插入活动序列
    if activities:
        success = microflowService.TryInsertAfterStart(
            microflow, Array[IActionActivity](activities[::-1]))
        if not success:
            raise RuntimeError(
                f"Failed to insert activities into '{mf_name}'.")
        info(
            f"Successfully inserted {len(activities)} activities into '{mf_name}'.")

    info("--- Success: Microflow Creation ---")
# --- 3. 主执行入口 ---


def main(model):
    """
    主函数，作为脚本的唯一入口点。
    它负责管理原子性事务，并按顺序编排所有模型创建任务。
    """
    MODULE_NAME = 'MyOrderModule'

    project = model.Root

    # 使用一个顶层事务来保证所有操作的原子性
    with TransactionManager(model, "Generate Order Management Solution"):
        try:
            # 步骤一：确保领域模型等环境就绪
            setup_successful = setup_order_management_environment(
                model, project, MODULE_NAME)

            # 步骤二：如果环境就绪，则创建业务微流
            if setup_successful:
                create_order_processing_microflow(model, project, MODULE_NAME)

        except Exception as e:
            # 记录在事务中发生的任何错误，事务将自动回滚
            error(
                f"An error occurred during solution generation: {e}\n{traceback.format_exc()}")
            # 重新抛出异常以确保事务管理器能捕获到它并回滚
            raise


# endregion

# region boot
try:
    # your logic here
    main(currentApp)
except IndexError as e:
    # Get the traceback as a string
    traceback_str = traceback.format_exc()
    PostMessage("backend:info", traceback_str)
# endregion
