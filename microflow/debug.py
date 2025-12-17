import clr
import traceback
import time

# 1. 引入 Mendix 扩展 API 及系统程序集
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
from System import ValueTuple, String, Array, Decimal
from Mendix.StudioPro.ExtensionsAPI.Model import Location
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import (
    IMicroflow, IActionActivity, IMicroflowCallAction, IMicroflowCall, 
    MicroflowReturnValue, IHead, IMicroflowCallParameterMapping
)
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import (
    CommitEnum, ChangeActionItemType, AggregateFunctionEnum
)
from Mendix.StudioPro.ExtensionsAPI.Model.DataTypes import DataType
from Mendix.StudioPro.ExtensionsAPI.Model.Texts import IText
from Mendix.StudioPro.ExtensionsAPI.Model.Enumerations import IEnumeration, IEnumerationValue
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import (
    IEntity, IAttribute, IStoredValue, IAssociation, AssociationType,
    IStringAttributeType, IBooleanAttributeType, IDateTimeAttributeType, 
    IDecimalAttributeType, IEnumerationAttributeType
)
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule

# ==========================================
# 辅助工具类 (简化版)
# ==========================================

def log(message):
    PostMessage("backend:info", f"[LOG] {message}")

def error(message):
    PostMessage("backend:error", f"[ERROR] {message}")

class SimpleLayout:
    def __init__(self, x=100, y=100):
        self.x = x
        self.y = y
    def next(self):
        loc = Location(self.x, self.y)
        self.x += 300
        return loc

# ==========================================
# 核心验证逻辑
# ==========================================

PostMessage("backend:clear", "")
log("=== 开始微流生成逻辑验证 ===")

MODULE_NAME = "GeneratedTestModule"

try:
    # 开启事务
    transaction = currentApp.StartTransaction("Verify Microflow Generation")
    
    # 1. 确保模块存在
    module = next((m for m in currentApp.Root.GetModules() if m.Name == MODULE_NAME), None)
    if not module:
        module = currentApp.Create[IModule]()
        module.Name = MODULE_NAME
        currentApp.Root.AddModule(module)
        log(f"创建模块: {MODULE_NAME}")

    layout = SimpleLayout()

    # 2. 生成领域模型 (Enum & Entities)
    log("步骤 1: 生成领域模型...")
    
    # 枚举
    enum_name = "OrderStatus"
    enum_qn_str = f"{MODULE_NAME}.{enum_name}"
    enum = currentApp.ToQualifiedName[IEnumeration](enum_qn_str).Resolve()
    if not enum:
        enum = currentApp.Create[IEnumeration]()
        enum.Name = enum_name
        for val_name in ["Pending", "Shipped"]:
            v = currentApp.Create[IEnumerationValue]()
            v.Name = val_name
            txt = currentApp.Create[IText]()
            txt.AddOrUpdateTranslation('en_US', val_name)
            v.Caption = txt
            enum.AddValue(v)
        module.AddDocument(enum)
        log("✅ 创建枚举: OrderStatus")

    # 实体: Order
    entity_name = "Order"
    order_entity = currentApp.ToQualifiedName[IEntity](f"{MODULE_NAME}.{entity_name}").Resolve()
    if not order_entity:
        order_entity = currentApp.Create[IEntity]()
        order_entity.Name = entity_name
        order_entity.Location = layout.next()
        
        # 属性: Status (Enum)
        attr = currentApp.Create[IAttribute]()
        attr.Name = "Status"
        attr_type = currentApp.Create[IEnumerationAttributeType]()
        attr_type.Enumeration = enum.QualifiedName # 直接使用 QualifiedName 对象
        attr.Type = attr_type
        attr.Value = currentApp.Create[IStoredValue]()
        order_entity.AddAttribute(attr)
        
        module.DomainModel.AddEntity(order_entity)
        log("✅ 创建实体: Order")

    # 3. 生成子微流 (SUB_CheckInventory)
    log("步骤 2: 生成子微流...")
    sub_mf_name = "SUB_CheckInventory"
    sub_mf = currentApp.ToQualifiedName[IMicroflow](f"{MODULE_NAME}.{sub_mf_name}").Resolve()
    
    if not sub_mf:
        # 定义参数
        params = [
            ValueTuple.Create[String, DataType]("OrderParam", DataType.Object(order_entity.QualifiedName)),
            ValueTuple.Create[String, DataType]("Comment", DataType.String)
        ]
        
        sub_mf = microflowService.CreateMicroflow(
            currentApp, module, sub_mf_name,
            MicroflowReturnValue(DataType.Boolean, microflowExpressionService.CreateFromString("true")),
            Array[ValueTuple[String, DataType]](params)
        )
        log(f"✅ 创建微流: {sub_mf_name}")

    # 4. 生成主微流 (ACT_ProcessOrder)
    log("步骤 3: 生成主微流及活动...")
    main_mf_name = "ACT_ProcessOrder"
    main_mf = currentApp.ToQualifiedName[IMicroflow](f"{MODULE_NAME}.{main_mf_name}").Resolve()
    
    if not main_mf:
        main_mf = microflowService.CreateMicroflow(
            currentApp, module, main_mf_name,
            MicroflowReturnValue(DataType.Boolean, microflowExpressionService.CreateFromString("true")),
            ValueTuple.Create[String, DataType]('OrderObj', DataType.Object(order_entity.QualifiedName))
        )
        
        activities = []

        # 活动 A: 调用子微流
        call_act = currentApp.Create[IActionActivity]()
        call_action = currentApp.Create[IMicroflowCallAction]()
        call_act.Action = call_action
        call_action.OutputVariableName = "IsAvailable"
        
        mf_call = currentApp.Create[IMicroflowCall]()
        mf_call.Microflow = sub_mf.QualifiedName
        call_action.MicroflowCall = mf_call
        
        # 参数映射
        target_params = {p.Name: p for p in microflowService.GetParameters(sub_mf)}
        
        m1 = currentApp.Create[IMicroflowCallParameterMapping]()
        m1.Parameter = target_params["OrderParam"].QualifiedName
        m1.Argument = microflowExpressionService.CreateFromString("$OrderObj")
        mf_call.AddParameterMapping(m1)

        m2 = currentApp.Create[IMicroflowCallParameterMapping]()
        m2.Parameter = target_params["Comment"].QualifiedName
        m2.Argument = microflowExpressionService.CreateFromString("'Verified via script'")
        mf_call.AddParameterMapping(m2)
        
        activities.append(call_act)

        # 活动 B: 修改订单状态
        status_attr = next(a for a in order_entity.GetAttributes() if a.Name == "Status")
        change_act = microflowActivitiesService.CreateChangeAttributeActivity(
            currentApp, status_attr, ChangeActionItemType.Set,
            microflowExpressionService.CreateFromString(f"{MODULE_NAME}.OrderStatus.Shipped"),
            "OrderObj", CommitEnum.No
        )
        activities.append(change_act)

        # 插入活动 (注意：Array 需要是 IActionActivity 类型)
        # TryInsertAfterStart 会按数组顺序从 Start 节点后插入，
        # 如果想让 A 在 B 前面，需要注意插入逻辑或反转数组。
        if microflowService.TryInsertAfterStart(main_mf, Array[IActionActivity](activities[::-1])):
            log("✅ 成功插入活动到主微流")
        else:
            log("❌ 插入活动失败")

    # 提交事务
    transaction.Commit()
    log("🎉 验证脚本执行成功，所有更改已提交。")

except Exception as e:
    if 'transaction' in locals():
        transaction.Rollback()
    error(f"严重错误: {str(e)}")
    log(traceback.format_exc())
finally:
    if 'transaction' in locals():
        transaction.Dispose()