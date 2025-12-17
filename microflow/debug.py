import clr
import traceback
from System import ValueTuple, String, Array, Decimal, Boolean
import System

# 引入 Mendix 核心命名空间
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
from Mendix.StudioPro.ExtensionsAPI.Model import Location
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import (
    IEntity, IAttribute, IStoredValue, IEnumerationAttributeType, 
    IStringAttributeType, IDecimalAttributeType, IIntegerAttributeType,
    AssociationType
)
from Mendix.StudioPro.ExtensionsAPI.Model.Enumerations import (
    IEnumeration, IEnumerationValue
)
from Mendix.StudioPro.ExtensionsAPI.Model.Texts import IText
from Mendix.StudioPro.ExtensionsAPI.Model.DataTypes import DataType
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import (
    IMicroflow, IActionActivity, IMicroflowCallAction, IMicroflowCall, 
    MicroflowReturnValue, IMicroflowCallParameterMapping, IHead
)
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import (
    CommitEnum, ChangeActionItemType, AggregateFunctionEnum
)

# 清除控制台并设置日志辅助函数
PostMessage("backend:clear", '')

def log(msg):
    PostMessage("backend:info", f"[INFO] {msg}")

def error_log(msg):
    PostMessage("backend:error", f"[ERROR] {msg}")

# ==========================================
# 1. 事务管理器 (复用你的设计)
# ==========================================
class TransactionManager:
    def __init__(self, currentApp, transaction_name):
        self.currentApp = currentApp
        self.transaction_name = transaction_name
        self.transaction = None

    def __enter__(self):
        if not hasattr(self.currentApp, 'StartTransaction'):
            raise AttributeError("currentApp object missing StartTransaction.")
        self.transaction = self.currentApp.StartTransaction(self.transaction_name)
        return self.transaction

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.transaction:
            if exc_type:
                self.transaction.Rollback()
                error_log(f"Transaction '{self.transaction_name}' rolled back: {exc_val}")
            else:
                self.transaction.Commit()
                log(f"Transaction '{self.transaction_name}' committed successfully.")
            self.transaction.Dispose()
        return False # 让异常冒泡以便调试

# ==========================================
# 2. 全功能演示脚本
# ==========================================
def run_comprehensive_api_demo(app):
    """
    演示全套 API 操作：
    1. 构建 Domain Model (Enum, Entity, Association)
    2. 构建 Sub Microflow (Params, Return)
    3. 构建 Main Microflow (Retrieve, Call, Change, Commit)
    """
    
    MODULE_NAME = "DemoReferenceModule"
    
    with TransactionManager(app, "Create Full Mendix Demo") as t:
        
        # --- 步骤 0: 模块初始化 ---
        log("--- 步骤 0: 模块 ---")
        module = next((m for m in app.Root.GetModules() if m.Name == MODULE_NAME), None)
        if not module:
            module = app.Create[IModule]()
            module.Name = MODULE_NAME
            app.Root.AddModule(module)
            log(f"创建新模块: {MODULE_NAME}")
        else:
            log(f"使用现有模块: {MODULE_NAME}")

        # 简单的布局游标
        layout_x = 100
        def next_loc():
            nonlocal layout_x
            loc = Location(layout_x, 100)
            layout_x += 400
            return loc

        # --- 步骤 1: Domain Model (复杂类型构建) ---
        log("--- 步骤 1: 领域模型 ---")
        
        # 1.1 创建枚举 (Enumeration)
        enum_name = "ProcessStatus"
        enum_qn_str = f"{MODULE_NAME}.{enum_name}"
        status_enum = app.ToQualifiedName[IEnumeration](enum_qn_str).Resolve()
        
        if not status_enum:
            status_enum = app.Create[IEnumeration]()
            status_enum.Name = enum_name
            for key in ["Draft", "Processing", "Completed"]:
                val = app.Create[IEnumerationValue]()
                val.Name = key
                caption = app.Create[IText]()
                caption.AddOrUpdateTranslation("en_US", key)
                val.Caption = caption
                status_enum.AddValue(val)
            module.AddDocument(status_enum)
            log(f"创建枚举: {enum_name}")

        # 1.2 创建实体 (Entity) - Product
        prod_ent = app.ToQualifiedName[IEntity](f"{MODULE_NAME}.Product").Resolve()
        if not prod_ent:
            prod_ent = app.Create[IEntity]()
            prod_ent.Name = "Product"
            prod_ent.Location = next_loc()
            
            # Decimal 属性
            attr_price = app.Create[IAttribute]()
            attr_price.Name = "Price"
            attr_price.Type = app.Create[IDecimalAttributeType]()
            attr_price.Value = app.Create[IStoredValue]()
            prod_ent.AddAttribute(attr_price)
            
            module.DomainModel.AddEntity(prod_ent)
            log("创建实体: Product")

        # 1.3 创建实体 - Order (包含枚举属性)
        order_ent = app.ToQualifiedName[IEntity](f"{MODULE_NAME}.Order").Resolve()
        if not order_ent:
            order_ent = app.Create[IEntity]()
            order_ent.Name = "Order"
            order_ent.Location = next_loc()

            # String 属性
            attr_desc = app.Create[IAttribute]()
            attr_desc.Name = "OrderNumber"
            attr_desc.Type = app.Create[IStringAttributeType]()
            attr_desc.Value = app.Create[IStoredValue]()
            order_ent.AddAttribute(attr_desc)

            # Enum 属性 (关键点：使用 QualifiedName 对象)
            attr_status = app.Create[IAttribute]()
            attr_status.Name = "Status"
            enum_type = app.Create[IEnumerationAttributeType]()
            enum_type.Enumeration = status_enum.QualifiedName # 必须传对象引用，不是字符串
            attr_status.Type = enum_type
            attr_status.Value = app.Create[IStoredValue]()
            order_ent.AddAttribute(attr_status)

            module.DomainModel.AddEntity(order_ent)
            log("创建实体: Order (含枚举属性)")

        # 1.4 创建关联 (Association) - M:N
        assoc_name = "Order_Product"
        assoc = next((a for a in domainModelService.GetAllAssociations(app, [module]) if a.Association.Name == assoc_name), None)
        if not assoc:
            new_assoc = order_ent.AddAssociation(prod_ent)
            new_assoc.Name = assoc_name
            new_assoc.Type = AssociationType.ReferenceSet # 多对多
            log(f"创建关联: {assoc_name} (*-*)")
        
        # 重新获取关联对象以便后续使用
        assoc_obj = next(a.Association for a in domainModelService.GetAllAssociations(app, [module]) if a.Association.Name == assoc_name)

        # --- 步骤 2: 构建子微流 (参数与返回值) ---
        log("--- 步骤 2: 子微流 ---")
        sub_mf_name = "SUB_CalculateTotal"
        sub_mf = app.ToQualifiedName[IMicroflow](f"{MODULE_NAME}.{sub_mf_name}").Resolve()

        if not sub_mf:
            # 参数定义：关键是 DataType 的构建
            # DataType.List 需要实体的 QualifiedName 对象
            params = [
                ValueTuple.Create[String, DataType]("ProductList", DataType.List(prod_ent.QualifiedName)),
                ValueTuple.Create[String, DataType]("TaxRate", DataType.Decimal)
            ]
            
            sub_mf = microflowService.CreateMicroflow(
                app, module, sub_mf_name,
                MicroflowReturnValue(DataType.Decimal, microflowExpressionService.CreateFromString("0.0")),
                Array[ValueTuple[String, DataType]](params) # 显式转为 C# 数组
            )
            log(f"创建子微流: {sub_mf_name} (入参: List, Decimal; 返回: Decimal)")

        # --- 步骤 3: 构建主微流 (活动编排) ---
        log("--- 步骤 3: 主微流逻辑 ---")
        main_mf_name = "ACT_ProcessOrder"
        main_mf = app.ToQualifiedName[IMicroflow](f"{MODULE_NAME}.{main_mf_name}").Resolve()

        if not main_mf:
            # 创建微流壳子，传入 Order 对象
            main_mf = microflowService.CreateMicroflow(
                app, module, main_mf_name,
                MicroflowReturnValue(DataType.Boolean, microflowExpressionService.CreateFromString("true")),
                ValueTuple.Create[String, DataType]("OrderContext", DataType.Object(order_ent.QualifiedName))
            )

            activities = []

            # 活动 A: 通过关联检索 (Retrieve by Association)
            # 参数: Model, Association, OutputVarName, StartObjectVarName
            act_retrieve = microflowActivitiesService.CreateAssociationRetrieveSourceActivity(
                app, assoc_obj, "RetrievedProducts", "OrderContext"
            )
            activities.append(act_retrieve)

            # 活动 B: 聚合列表 (Aggregate List - Count)
            # 参数: Model, ListVarName, OutputVarName, Function
            act_count = microflowActivitiesService.CreateAggregateListActivity(
                app, "RetrievedProducts", "ProductCount", AggregateFunctionEnum.Count
            )
            activities.append(act_count)

            # 活动 C: 调用子微流 (Call Microflow)
            act_call = app.Create[IActionActivity]()
            call_action = app.Create[IMicroflowCallAction]()
            act_call.Action = call_action
            call_action.OutputVariableName = "CalculatedTotal"
            
            mf_call = app.Create[IMicroflowCall]()
            mf_call.Microflow = sub_mf.QualifiedName # 链接子微流
            call_action.MicroflowCall = mf_call

            # 参数映射 (Parameter Mapping)
            # 获取子微流的参数定义
            target_params = {p.Name: p for p in microflowService.GetParameters(sub_mf)}
            
            # 映射 ProductList -> $RetrievedProducts
            map1 = app.Create[IMicroflowCallParameterMapping]()
            map1.Parameter = target_params["ProductList"].QualifiedName
            map1.Argument = microflowExpressionService.CreateFromString("$RetrievedProducts")
            mf_call.AddParameterMapping(map1)

            # 映射 TaxRate -> 0.15
            map2 = app.Create[IMicroflowCallParameterMapping]()
            map2.Parameter = target_params["TaxRate"].QualifiedName
            map2.Argument = microflowExpressionService.CreateFromString("0.15")
            mf_call.AddParameterMapping(map2)
            
            activities.append(act_call)

            # 活动 D: 修改对象 (Change Object)
            # 需要找到特定的 Attribute 对象
            attr_status = next(a for a in order_ent.GetAttributes() if a.Name == "Status")
            
            act_change = microflowActivitiesService.CreateChangeAttributeActivity(
                app, attr_status, ChangeActionItemType.Set,
                # 枚举值的表达式写法: Module.Enum.Value
                microflowExpressionService.CreateFromString(f"{MODULE_NAME}.ProcessStatus.Processing"),
                "OrderContext", CommitEnum.No
            )
            activities.append(act_change)

            # 活动 E: 提交对象 (Commit)
            # 参数: Model, ObjectVarName, RefreshClient, Events
            act_commit = microflowActivitiesService.CreateCommitObjectActivity(
                app, "OrderContext", True, True
            )
            activities.append(act_commit)

            # 批量插入活动
            # 注意：MicroflowService.TryInsertAfterStart 会把数组反向插入到 Start 之后
            # 所以为了保持 A->B->C->D->E 的顺序，我们需要把数组反转传递，或者一个个插
            # 这里我们直接用 SDK 推荐的批量插入，通常需要传递 Python List 的切片 [::-1] 来反转以保持直观顺序
            if microflowService.TryInsertAfterStart(main_mf, Array[IActionActivity](activities[::-1])):
                log(f"成功插入 {len(activities)} 个活动到主微流")
            else:
                error_log("插入微流活动失败")

        log("API 演示完成，等待事务提交...")

# ==========================================
# 3. 执行入口
# ==========================================
try:
    run_comprehensive_api_demo(currentApp)
except Exception as e:
    error_log(f"脚本执行崩溃: {str(e)}")
    error_log(traceback.format_exc())