好的，这里是使用 `pythonnet` 创建各种常见微流活动类型的关键 Python 代码片段。

### 前提条件

在运行这些代码片段之前，你需要准备好以下对象。这些对象通常从你的 C# 引导程序传入，或者通过 API 查询得到。

```python
# --- 必要的服务 ---
# model: IModel
# activity_service: IMicroflowActivitiesService
# expression_service: IMicroflowExpressionService

# --- 必要的模型元素 ---
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import IEntity, IAttribute, IAssociation
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow
from Mendix.StudioPro.ExtensionsAPI.Model.JavaActions import IJavaAction

# 假设这些元素已经存在于你的模型中
customer_qn = model.ToQualifiedName[IEntity]("MyFirstModule.Customer")
customer_entity: IEntity = customer_qn.Resolve()

name_attribute: IAttribute = next(a for a in customer_entity.GetAttributes() if a.Name == "Name")
age_attribute: IAttribute = next(a for a in customer_entity.GetAttributes() if a.Name == "Age")

order_association_qn = model.ToQualifiedName[IAssociation]("MyFirstModule.Customer_Order")
order_association: IAssociation = order_association_qn.Resolve()

sub_microflow_qn = model.ToQualifiedName[IMicroflow]("MyFirstModule.SUB_ProcessCustomer")
sub_microflow_to_call: IMicroflow = sub_microflow_qn.Resolve()

java_action_qn = model.ToQualifiedName[IJavaAction]("MyFirstModule.JA_CalculateScore")
java_action_to_call: IJavaAction = java_action_qn.Resolve()


# --- 常用枚举和系统类型 ---
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import CommitEnum, ChangeActionItemType, ChangeListActionOperation, AggregateFunctionEnum
from System import Array
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import AttributeSorting

# --- 常用变量名 ---
customer_var = "NewCustomer"
customer_list_var = "CustomerList"
other_customer_var = "OtherCustomer"
order_var = "AssociatedOrder"
```

---

### 1. 对象活动 (Object Activities)

#### 创建对象 (Create Object)
```python
create_activity = activity_service.CreateCreateObjectActivity(
    model,
    customer_entity,
    customer_var,
    CommitEnum.No,  # 稍后手动提交
    False,          #不在客户端刷新
    None            # 没有初始值
)
```

#### 修改对象 (Change Object)
```python
# 修改属性
new_name_expr = expression_service.CreateFromString("'John Doe'")
change_attr_activity = activity_service.CreateChangeAttributeActivity(
    model,
    name_attribute,
    ChangeActionItemType.Set,
    new_name_expr,
    customer_var,
    CommitEnum.No
)

# 修改关联 (假设 order_var 已经存在)
assoc_value_expr = expression_service.CreateFromString(f"${order_var}")
change_assoc_activity = activity_service.CreateChangeAssociationActivity(
    model,
    order_association,
    ChangeActionItemType.Set,
    assoc_value_expr,
    customer_var,
    CommitEnum.No
)
```

#### 提交、删除和回滚 (Commit, Delete, Rollback)
```python
# 提交对象
commit_activity = activity_service.CreateCommitObjectActivity(
    model, 
    customer_var, 
    True,  # WithEvents
    False  # RefreshInClient
)

# 删除对象
delete_activity = activity_service.CreateDeleteObjectActivity(model, customer_var)

# 回滚对象
rollback_activity = activity_service.CreateRollbackObjectActivity(
    model, 
    customer_var, 
    True # RefreshInClient
)
```

#### 检索 (Retrieve)
```python
# 从数据库检索 (列表)
retrieve_list_activity = activity_service.CreateDatabaseRetrieveSourceActivity(
    model,
    customer_list_var,
    customer_entity,
    f"[{name_attribute.Name} = 'John Doe']",  # XPath constraint
    None,  # Range (ValueTuple)
    None   # Sorting
)

# 从数据库检索 (单个对象)
retrieve_single_activity = activity_service.CreateDatabaseRetrieveSourceActivity(
    model,
    customer_var,
    customer_entity,
    "",    # No constraint
    True,  # 只检索第一个
    None   # Sorting
)

# 通过关联检索
# 假设 customer_var 是一个已存在的对象变量
retrieve_by_assoc_activity = activity_service.CreateAssociationRetrieveSourceActivity(
    model,
    order_association,
    "RetrievedOrderList", # 输出变量名
    customer_var          # 起始对象变量名
)
```

---

### 2. 列表活动 (List Activities)

#### 创建和修改列表 (Create and Change List)
```python
# 创建空列表
create_list_activity = activity_service.CreateCreateListActivity(
    model, 
    customer_entity, 
    customer_list_var
)

# 向列表中添加元素 (假设 other_customer_var 已存在)
add_value_expr = expression_service.CreateFromString(f"${other_customer_var}")
change_list_activity = activity_service.CreateChangeListActivity(
    model,
    ChangeListActionOperation.Add,
    customer_list_var,
    add_value_expr
)
```

#### 聚合列表 (Aggregate List)
```python
# 计算列表中的对象数量
count_activity = activity_service.CreateAggregateListActivity(
    model,
    customer_list_var,
    "CustomerCount",  # 输出变量名
    AggregateFunctionEnum.Count
)

# 计算列表中某个属性的总和
sum_age_activity = activity_service.CreateAggregateListByAttributeActivity(
    model,
    age_attribute,
    customer_list_var,
    "TotalAge", # 输出变量名
    AggregateFunctionEnum.Sum
)
```

#### 列表操作 (List Operations - Filter, Sort)
```python
# 过滤列表
filter_expr = expression_service.CreateFromString(f"[{age_attribute.Name} > 30]")
filter_activity = activity_service.CreateFilterListByAttributeActivity(
    model,
    age_attribute,
    customer_list_var,
    "FilteredCustomerList", # 输出变量名
    filter_expr
)

# 排序列表
# 注意：需要创建一个 .NET 数组
sorting_rule = AttributeSorting()
sorting_rule.Attribute = age_attribute
sorting_rule.SortByDescending = True
sort_array = Array[AttributeSorting]([sorting_rule]) # 创建数组

sort_activity = activity_service.CreateSortListActivity(
    model,
    customer_list_var,
    "SortedCustomerList", # 输出变量名
    sort_array
)
```

---

### 3. 动作调用活动 (Action Call Activities)

这些活动通常需要先用 `model.Create()` 创建动作本身，然后包装在 `IActionActivity` 中。

#### 调用微流 (Call Microflow)
```python
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IActionActivity, IMicroflowCallAction, IMicroflowCall, IMicroflowCallParameterMapping

# 1. 创建一个通用的 ActionActivity
call_mf_activity = model.Create[IActionActivity]()
call_mf_activity.Caption = f"Call {sub_microflow_to_call.Name}"

# 2. 创建微流调用动作
mf_call_action = model.Create[IMicroflowCallAction]()
mf_call_action.OutputVariableName = "ResultFromSub"
mf_call_action.UseReturnVariable = True

# 3. 配置微流调用详情
mf_call = model.Create[IMicroflowCall]()
mf_call.Microflow = sub_microflow_to_call.QualifiedName

# 4. (如果需要) 映射参数
# 假设子微流有一个名为 'InputCustomer' 的参数
param_mapping = model.Create[IMicroflowCallParameterMapping]()
# 通过 QualifiedName 引用参数
param_qn = model.ToQualifiedName(f"{sub_microflow_to_call.QualifiedName.FullName}.InputCustomer")
param_mapping.Parameter = param_qn
param_mapping.Argument = expression_service.CreateFromString(f"${customer_var}")
mf_call.AddParameterMapping(param_mapping)

# 5. 组装
mf_call_action.MicroflowCall = mf_call
call_mf_activity.Action = mf_call_action
```

#### 调用 Java 动作 (Call Java Action)
```python
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IJavaActionCallAction
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IJavaActionParameterMapping, IBasicCodeActionParameterValue

# 1. 创建一个通用的 ActionActivity
call_ja_activity = model.Create[IActionActivity]()
call_ja_activity.Caption = f"Call {java_action_to_call.Name}"

# 2. 创建 Java 动作调用
ja_call_action = model.Create[IJavaActionCallAction]()
ja_call_action.JavaAction = java_action_to_call.QualifiedName
ja_call_action.OutputVariableName = "Score"
ja_call_action.UseReturnVariable = True

# 3. 映射参数
# 假设 Java Action 有一个名为 'CustomerToProcess' 的参数
param_mapping = model.Create[IJavaActionParameterMapping]()
param_qn = model.ToQualifiedName(f"{java_action_to_call.QualifiedName.FullName}.CustomerToProcess")
param_mapping.Parameter = param_qn

# 参数值本身也是一个对象
arg_value = model.Create[IBasicCodeActionParameterValue]()
arg_value.Argument = expression_service.CreateFromString(f"${customer_var}")
param_mapping.ParameterValue = arg_value
ja_call_action.AddParameterMapping(param_mapping)

# 4. 组装
call_ja_activity.Action = ja_call_action
```

---

### 4. 流程控制 (Flow Control)

这些不是通过 `activity_service` 创建的，而是直接通过 `model.Create()` 创建，因为它们是流程对象而不是活动。

```python
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IEndEvent, IDecision

# 创建结束事件
end_event = model.Create[IEndEvent]()
# 你可以设置它的返回值
end_event.ReturnValue = expression_service.CreateFromString("true")

# 创建决策
decision = model.Create[IDecision]()
decision.Caption = "Is customer active?"
decision.Expression = expression_service.CreateFromString(f"${customer_var}/IsActive")
```