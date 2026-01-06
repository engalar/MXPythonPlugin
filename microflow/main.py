# region FRAMEWORK CODE
import json
import urllib.request
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod

# Mendix and .NET related imports
import clr

clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
import threading
import uuid
from dependency_injector import containers, providers
from System.Text.Json import JsonSerializer

# ShowDevTools()

# ===================================================================
# ===================     FRAMEWORK CODE     ========================
# ===================================================================
# This section contains the reusable, application-agnostic core.
# You should not need to modify this section to add new features.
# -------------------------------------------------------------------

# 1. FRAMEWORK: CORE ABSTRACTIONS AND INTERFACES


class MendixEnvironmentService:
    """Abstracts the Mendix host environment global variables."""

    def __init__(self, app_context, window_service, post_message_func: Callable):
        self.app = app_context
        self.window_service = window_service
        self.post_message = post_message_func

    def get_project_path(self) -> str:
        return self.app.Root.DirectoryPath


# ===================================================================
# ===================    CORE ABSTRACTIONS     ======================
# ===================================================================
from abc import ABC, abstractmethod
from typing import Any, Dict, Callable, Iterable, Optional, Protocol
import uuid
import threading
import json
import traceback


class ProgressUpdate:
    """Structured progress data."""

    def __init__(
        self,
        percent: float,
        message: str,
        stage: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        self.percent = percent
        self.message = message
        self.stage = stage
        self.metadata = metadata

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


class IMessageHub(Protocol):
    """Abstraction for sending messages to the frontend (DIP)."""

    def send(self, message: Dict): ...
    def broadcast(self, channel: str, data: Any): ...
    def push_to_session(self, session_id: str, data: Any): ...


class IJobContext(Protocol):
    """Context object provided to a running job handler."""

    job_id: str

    def report_progress(self, progress: ProgressUpdate): ...


# --- Handler Interfaces (OCP) ---
class IHandler(ABC):
    @property
    @abstractmethod
    def command_type(self) -> str: ...


class IRpcHandler(IHandler):
    @abstractmethod
    def execute(self, payload: Dict) -> Any: ...


class IJobHandler(IHandler):
    @abstractmethod
    def run(self, payload: Dict, context: IJobContext): ...


class ISessionHandler(IHandler):
    @abstractmethod
    def on_connect(self, session_id: str, payload: Optional[Dict]): ...
    @abstractmethod
    def on_disconnect(self, session_id: str): ...


# 2. FRAMEWORK: CENTRAL DISPATCHER
# ===================================================================
# ===================     FRAMEWORK CORE     ========================
# ===================================================================
class MendixMessageHub:
    """Low-level implementation of IMessageHub for Mendix."""

    def __init__(self, post_message_func: Callable):
        self._post_message = post_message_func

    def send(self, message: Dict):
        self._post_message("backend:response", json.dumps(message))

    def broadcast(self, channel: str, data: Any):
        self.send({"type": "EVENT_BROADCAST", "channel": channel, "data": data})

    def push_to_session(self, session_id: str, data: Any):
        self.send({"type": "EVENT_SESSION", "sessionId": session_id, "data": data})

def forward_telemetry_to_jaeger(endpoint, spans):
    """使用 Python 后端转发追踪数据，规避浏览器 CORS"""
    if not endpoint or not spans:
        return

    try:
        body = json.dumps(spans).encode("utf-8")
        req = urllib.request.Request(
            endpoint, data=body, headers={"Content-Type": "application/json"}
        )
        # 设置较短的超时，避免阻塞主线程
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status >= 300:
                pass
    except Exception as e:
        traceback.print_exc()

class PythonTelemetryService:
    def __init__(self, hub: IMessageHub):
        self._hub = hub
        self.service_name = "studio-plugin[microflow]"

    def gen_id(self, length):
        import secrets
        return secrets.token_hex(length // 2)

    def start_span(self, name, trace_id=None, parent_id=None, attributes=None):
        trace_id = trace_id or self.gen_id(32)
        span_id = self.gen_id(16)
        start_time = time.time()
        
        # 返回一个简单的对象来模拟 Span 行为
        class Span:
            def __init__(self, svc, t_id, s_id, p_id, n, attrs):
                self.svc, self.traceId, self.spanId, self.parentId, self.name, self.attrs = svc, t_id, s_id, p_id, n, attrs or {}
            def end(self, end_attrs=None):
                duration = (time.time() - start_time) * 1000000
                span_data = {
                    "traceId": self.traceId, "id": self.spanId, "name": self.name,
                    "timestamp": int(start_time * 1000000), "duration": int(duration),
                    "localEndpoint": {"serviceName": self.svc.service_name},
                    "tags": {**self.attrs, **(end_attrs or {})}
                }
                if self.parentId: span_data["parentId"] = self.parentId
                # 直接通过转发函数发送
                forward_telemetry_to_jaeger("http://localhost:9411/api/v2/spans", [span_data])
        
        return Span(self, trace_id, span_id, parent_id, name, attributes)

class AppController:
    def __init__(self, rpc_handlers, job_handlers, session_handlers, message_hub, telemetry: PythonTelemetryService):
        self._rpc = {h.command_type: h for h in rpc_handlers}
        self._jobs = {h.command_type: h for h in job_handlers}
        self._sessions = {h.command_type: h for h in session_handlers}
        self._hub = message_hub
        self._telemetry = telemetry

    def dispatch(self, request: Dict):
        msg_type = request.get("type")
        trace_id = request.get("traceId")
        parent_id = request.get("spanId") # 前端的 Span 是后端的 Parent
        
        try:
            if msg_type == "RPC":
                self._handle_rpc(request, trace_id, parent_id)
            elif msg_type == "JOB_START":
                self._handle_job_start(request, trace_id, parent_id)
            elif msg_type == "SESSION_CONNECT":
                self._handle_session_connect(request)
            elif msg_type == "SESSION_DISCONNECT":
                self._handle_session_disconnect(request)
            else:
                raise ValueError(f"Unknown message type: {msg_type}")
        except Exception as e:
            # 错误处理保持原有逻辑
            self._hub.send({"type": "RPC_ERROR", "reqId": request.get("reqId"), "message": str(e), "traceback": traceback.format_exc()})

    def _handle_rpc(self, request, trace_id, parent_id):
        handler = self._rpc.get(request["method"])
        span = self._telemetry.start_span(f"PY_RPC:{request['method']}", trace_id, parent_id)
        try:
            result = handler.execute(request.get("params"))
            span.end({"status": "success"})
            self._hub.send({"type": "RPC_SUCCESS", "reqId": request["reqId"], "data": result})
        except Exception as e:
            span.end({"error": "true", "message": str(e)})
            raise

    def _handle_job_start(self, request, trace_id, parent_id):
        handler = self._jobs.get(request["method"])
        job_id = f"job-{uuid.uuid4()}"
        span = self._telemetry.start_span(f"PY_JOB_EXEC:{request['method']}", trace_id, parent_id, {"jobId": job_id})

        class JobContext(IJobContext):
            def __init__(self, j_id, hub, telemetry_span):
                self.job_id = j_id
                self._hub = hub
                self.span = telemetry_span # 传递 span 供业务代码使用
            def report_progress(self, progress: ProgressUpdate):
                self._hub.send({"type": "JOB_PROGRESS", "jobId": self.job_id, "progress": progress.to_dict()})

        def job_runner():
            try:
                result = handler.run(request.get("params"), JobContext(job_id, self._hub, span))
                span.end({"status": "success"})
                self._hub.send({"type": "JOB_SUCCESS", "jobId": job_id, "data": result})
            except Exception as e:
                span.end({"error": "true", "exception": str(e)})
                self._hub.send({"type": "JOB_ERROR", "jobId": job_id, "message": str(e), "traceback": traceback.format_exc()})

        threading.Thread(target=job_runner, daemon=True).start()
        self._hub.send({"type": "JOB_STARTED", "reqId": request["reqId"], "jobId": job_id})

# endregion

# region BUSINESS LOGIC CODE
# ===================================================================
# ===============     BUSINESS LOGIC CODE     =======================
# ===================================================================

# region Mendix SDK Imports
import time
from System import ValueTuple, String, Array
from Mendix.StudioPro.ExtensionsAPI.Model import Location
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import (
    IMicroflow,
    IActionActivity,
    IMicroflowCallAction,
    IMicroflowCall,
    MicroflowReturnValue,
    IHead,
    IMicroflowCallParameterMapping,
)
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import (
    CommitEnum,
    ChangeActionItemType,
    AggregateFunctionEnum,
)
from Mendix.StudioPro.ExtensionsAPI.Model.DataTypes import DataType
from Mendix.StudioPro.ExtensionsAPI.Model.Texts import IText
from Mendix.StudioPro.ExtensionsAPI.Model.Enumerations import (
    IEnumeration,
    IEnumerationValue,
)
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import (
    IEntity,
    IAttribute,
    IStoredValue,
    IAssociation,
    AssociationType,
    IStringAttributeType,
    IBooleanAttributeType,
    IDateTimeAttributeType,
    IDecimalAttributeType,
    IEnumerationAttributeType,
)
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule

from pymx.model import microflow
import importlib
importlib.reload(microflow)

from pymx.model.dto.type_microflow import (
    CreateMicroflowsToolInput,
    MicroflowParameter,
)

from pymx.mcp import mendix_context as ctx
# importlib.reload(ctx)
ctx.set_mendix_services(
    currentApp,
    messageBoxService,
    extensionFileService,
    microflowActivitiesService,
    microflowExpressionService,
    microflowService,
    untypedModelAccessService,
    dockingWindowService,
    domainModelService,
    backgroundJobService,
    configurationService,
    extensionFeaturesService,
    httpClientService,
    nameValidationService,
    navigationManagerService,
    pageGenerationService,
    appService,
    dialogService,
    entityService,
    findResultsPaneService,
    localRunConfigurationsService,
    notificationPopupService,
    runtimeService,
    selectorDialogService,
    versionControlService
)

# endregion

# --- Helpers: Layout & SDK Facade ---


class LayoutManager:
    """Handles the visual positioning of elements in Studio Pro."""

    def __init__(self, start_x=100, start_y=200, spacing_x=300):
        self.x = start_x
        self.y = start_y
        self.spacing_x = spacing_x

    def next_pos(self) -> Location:
        """Returns the current location and advances the cursor."""
        loc = Location(self.x, self.y)
        self.x += self.spacing_x
        return loc


class MendixSdkFacade:
    """
    Wraps the verbose Mendix SDK calls.
    Distinguishes between 'model' (Factory/Transaction) and 'project' (Structure).
    """

    def __init__(self, model, project, module_name: str, report_func):
        self.model = model  # IModel: Creates objects, resolves names
        self.project = project  # IProject: Holds modules
        self.module_name = module_name
        self.report = report_func

        # Resolve or Create Module
        self.module = next(
            (m for m in self.project.GetModules() if m.Name == module_name), None
        )
        if not self.module:
            self.module = self.model.Create[IModule]()
            self.module.Name = module_name
            self.project.AddModule(self.module)
            self.report(f"Created module: '{module_name}'", percent_increment=5)

    def ensure_enum(self, enum_name, values: list):
        qn = f"{self.module_name}.{enum_name}"
        existing = self.model.ToQualifiedName[IEnumeration](qn).Resolve()
        if existing:
            return existing

        enum = self.model.Create[IEnumeration]()
        enum.Name = enum_name
        for val_name in values:
            val = self.model.Create[IEnumerationValue]()
            val.Name = val_name
            txt = self.model.Create[IText]()
            txt.AddOrUpdateTranslation("en_US", val_name)
            val.Caption = txt
            enum.AddValue(val)
        self.module.AddDocument(enum)
        self.report(f"Created enumeration: {enum_name}")
        return enum

    def ensure_entity(self, name, attributes: dict, location: Location):
        qn = f"{self.module_name}.{name}"
        entity = self.model.ToQualifiedName[IEntity](qn).Resolve()

        if entity:
            entity.Location = location
            self.report(f"Repositioned existing entity '{name}'.")
            return entity

        entity = self.model.Create[IEntity]()
        entity.Name = name
        entity.Location = location

        for attr_name, type_creator in attributes.items():
            attr = self.model.Create[IAttribute]()
            attr.Name = attr_name
            # type_creator is a callable that takes 'model' as arg
            attr.Type = (
                type_creator(self.model) if callable(type_creator) else type_creator
            )
            attr.Value = self.model.Create[IStoredValue]()
            entity.AddAttribute(attr)

        self.module.DomainModel.AddEntity(entity)
        self.report(f"Created entity: {name}")
        return entity

    def ensure_association(
        self, source: IEntity, target: IEntity, name: str, is_ref_set=False
    ):
        # Check existence
        all_assocs = domainModelService.GetAllAssociations(self.model, [self.module])
        if any(a for a in all_assocs if a.Association.Name == name):
            return

        assoc = source.AddAssociation(target)
        assoc.Name = name
        if is_ref_set:
            assoc.Type = AssociationType.ReferenceSet
        self.report(f"Created association: {name}")

    def get_qualified_entity(self, name):
        # Use self.model to resolve names
        return self.model.ToQualifiedName[IEntity](
            f"{self.module_name}.{name}"
        ).Resolve()


# --- Main Job Logic ---


class GenerateMicroflowJob(IJobHandler):
    command_type = "microflow:generate"

    def __init__(self):
        # self._app is the IModel instance (currentApp)
        self._app = currentApp

    def run(self, payload: Dict, context: IJobContext):
        state = {"p": 0, "logs": []}
        def report(msg, stage=None, percent_increment=2):
            state["p"] = min(state["p"] + percent_increment, 99)
            state["logs"].append(msg)
            context.report_progress(ProgressUpdate(percent=state["p"], message=msg.replace("---", "").strip(), 
                                                   stage=stage or "Processing", metadata={"logs": list(state["logs"])}))

        try:
            # 使用 context 中携带的 span 记录具体的业务阶段
            report("--- Starting Generation ---", "Init", 5)
            generator = OrderManagementGenerator(self._app, report)
            generator.execute()

            report("--- Generation Complete ---", "Done", 100)
            return {"status": "Success", "module": "MyOrderModule"}
        except Exception as e:
            raise RuntimeError(f"Job failed: {str(e)}")

class OrderManagementGenerator:
    """
    Organizes the specific business logic.
    """

    MODULE = "MyOrderModule"

    def __init__(self, app, report_func):
        self.model = app  # IModel (Factory, Transaction)
        self.project = app.Root  # IProject (Structure)
        self.report = report_func
        self.builder = None
        self.layout = LayoutManager()

    def execute(self):
        # Transaction is started on the IModel
        transaction = self.model.StartTransaction("Generate Order Solution")
        try:
            # Pass both model and project to the facade
            self.builder = MendixSdkFacade(
                self.model, self.project, self.MODULE, self.report
            )

            self.step_domain_model()
            self.step_sub_microflows()
            self.step_main_microflow()
            self.step_test(transaction)

            transaction.Commit()
            self.report("Transaction committed successfully.")
        except Exception:
            transaction.Rollback()
            raise
        finally:
            transaction.Dispose()
    
    def step_test(self, tx):
        # 演示：构建一个涵盖 Database/Association Retrieve, ListOperation(Union/Head), Aggregate, Change, Commit 的全功能微流
        mf_path = f"{self.MODULE}/ComplexLogic/Test_All_Capabilities"
        
        # 准备全限定名
        order_qn = f"{self.MODULE}.Order"
        product_qn = f"{self.MODULE}.Product"
        customer_qn = f"{self.MODULE}.Customer"
        
        # 关联名称 (需与 Domain Model 建立的名称一致)
        assoc_order_product = f"{self.MODULE}.Order_Product"
        assoc_customer_order = f"{self.MODULE}.Customer_Order"
        
        data = {
            "requests": [
                {
                    "FullPath": mf_path,
                    "ReturnType": {"TypeName": "Boolean", "QualifiedName": None},
                    "ReturnExp": "true",
                    "Parameters": [
                        {
                            "Name": "OrderParam",
                            "Type": {
                                "TypeName": "Object",
                                "QualifiedName": order_qn,
                            },
                        }
                    ],
                    "Activities": [
                        # 1. [Retrieve: Database] 查找数据库中价格 > 50 的产品
                        {
                            "ActivityType": "Retrieve",
                            "SourceType": "Database",
                            "EntityName": product_qn,
                            "XPathConstraint": "[Price > 50]",
                            "RangeIndex": "1",
                            "RangeAmount": "5",
                            # RetrieveJustFirstItem and [RangeIndex RangeAmount]只能二选一
                            # "RetrieveJustFirstItem": True,
                            "Sorting": [{"AttributeName": "Price", "Ascending": False}],
                            "OutputVariable": "HighValueDbProducts",
                        },
                        
                        # 2. [Retrieve: Association] 获取当前订单关联的已有产品列表
                        {
                            "ActivityType": "Retrieve",
                            "SourceType": "Association",
                            "SourceVariable": "OrderParam",
                            "AssociationName": assoc_order_product,
                            "OutputVariable": "ExistingOrderProducts",
                        },

                        # 3. [ListOperation: Binary] 将数据库查询结果与已有产品取并集 (Union)
                        # 目前API不支持Union
                        # {
                        #     "ActivityType": "ListOperation",
                        #     "OperationType": "Union",
                        #     "InputListVariable": "ExistingOrderProducts",
                        #     "BinaryOperationListVariable": "HighValueDbProducts",
                        #     "OutputVariable": "MergedProductList",
                        # },

                        # 4. [ListOperation: Unary] 获取合并列表的第一个产品 (Head)
                        {
                            "ActivityType": "ListOperation",
                            "OperationType": "Head",
                            "InputListVariable": "ExistingOrderProducts",
                            "OutputVariable": "TopProduct",
                        },

                        # 5. [Retrieve: Association] 获取订单关联的客户 (单对象)
                        {
                            "ActivityType": "Retrieve",
                            "SourceType": "Association",
                            "SourceVariable": "OrderParam",
                            "AssociationName": assoc_customer_order,
                            "OutputVariable": "OrderCustomer",
                        },

                        # 6. [Aggregate] 计算合并后的产品数量
                        {
                            "ActivityType": "AggregateList",
                            "Function": "Count",
                            "InputListVariable": "ExistingOrderProducts",
                            "OutputVariable": "TotalCount",
                        },

                        # 7. [Change] 更新订单描述
                        # 逻辑：描述 = 客户名 + ": " + 数量
                        {
                            "ActivityType": "Change",
                            "VariableName": "OrderParam",
                            "EntityName": order_qn,
                            "Changes": [
                                {
                                    "AttributeName": "Description",
                                    "Action": "Set", 
                                    "ValueExpression": "$TopProduct/Price + ': Potential Items ' + toString($TotalCount)",
                                }
                            ],
                            "Commit": "No", 
                        },
                        
                        # 8. [Commit] 提交订单并刷新客户端
                        {
                            "ActivityType": "Commit",
                            "VariableName": "OrderParam",
                            "RefreshClient": True
                        }
                    ],
                }
            ]
        }
        
        self.report(f"Generating comprehensive test microflow: {mf_path}")
        # 验证 DTO 并执行
        input_dto = CreateMicroflowsToolInput(**data)
        
        # 调用 microflow.py 中的逻辑
        result_log = microflow.create_microflows(ctx, input_dto, tx)
        self.report(result_log)

    def step_domain_model(self):
        self.report("--- Building Domain Model ---", "Domain Model", 10)

        # 1. Enum
        enum = self.builder.ensure_enum(
            "OrderStatus", ["Pending", "Confirmed", "Shipped", "Cancelled"]
        )

        # Helper for Enum Attribute Type
        def enum_type_creator(m):
            t = m.Create[IEnumerationAttributeType]()
            # [FIXED]: Assign the QualifiedName property directly.
            # enum.QualifiedName IS ALREADY the IQualifiedName object required here.
            # Do NOT wrap it in m.ToQualifiedName().
            t.Enumeration = enum.QualifiedName
            return t

        # 2. Entities (using Layout Manager)
        # We pass lambdas so the Facade uses the correct 'model' to Create types
        self.builder.ensure_entity(
            "Customer",
            {"Name": lambda m: m.Create[IStringAttributeType]()},
            self.layout.next_pos(),
        )

        self.builder.ensure_entity(
            "Order",
            {
                "Description": lambda m: m.Create[IStringAttributeType](),
                "Status": enum_type_creator,
            },
            self.layout.next_pos(),
        )

        self.builder.ensure_entity(
            "Product",
            {"Price": lambda m: m.Create[IDecimalAttributeType]()},
            self.layout.next_pos(),
        )

        # 3. Associations
        cust = self.builder.get_qualified_entity("Customer")
        order = self.builder.get_qualified_entity("Order")
        prod = self.builder.get_qualified_entity("Product")

        self.builder.ensure_association(cust, order, "Customer_Order")
        self.builder.ensure_association(order, prod, "Order_Product", is_ref_set=True)

    def step_sub_microflows(self):
        mf_name = "SUB_CheckInventory"
        # Resolution uses IModel
        if self.model.ToQualifiedName[IMicroflow](f"{self.MODULE}.{mf_name}").Resolve():
            return

        self.report(f"Creating {mf_name}...", "Microflows")

        # [FIX]: Convert strings to IQualifiedName objects first
        prod_qn_str = f"{self.MODULE}.Product"
        enum_qn_str = f"{self.MODULE}.OrderStatus"

        # 1. Create QualifiedName for Entity (Required for DataType.Object/List)
        prod_qn = self.model.ToQualifiedName[IEntity](prod_qn_str)

        # 2. Create QualifiedName for Enumeration (Required for DataType.Enumeration)
        # Note: Do NOT call .Resolve() here. DataType expects the name reference, not the object.
        enum_qn = self.model.ToQualifiedName[IEnumeration](enum_qn_str)

        # Create Types using the QualifiedName objects
        params = [
            ValueTuple.Create[String, DataType]("StringParam", DataType.String),
            ValueTuple.Create[String, DataType]("IntegerParam", DataType.Integer),
            # Pass the QualifiedName object, NOT the string
            ValueTuple.Create[String, DataType](
                "ProductParam", DataType.Object(prod_qn)
            ),
            # Pass the QualifiedName object
            ValueTuple.Create[String, DataType](
                "StatusParam", DataType.Enumeration(enum_qn)
            ),
            # Pass the QualifiedName object
            ValueTuple.Create[String, DataType](
                "ProductListParam", DataType.List(prod_qn)
            ),
        ]

        microflowService.CreateMicroflow(
            self.model,
            self.builder.module,
            mf_name,
            MicroflowReturnValue(
                DataType.Boolean, microflowExpressionService.CreateFromString("true")
            ),
            Array[ValueTuple[String, DataType]](params),
        )

    def step_main_microflow(self):
        mf_name = "ACT_ProcessPendingOrder"
        if self.model.ToQualifiedName[IMicroflow](f"{self.MODULE}.{mf_name}").Resolve():
            self.report(f"Microflow {mf_name} already exists.")
            return

        self.report(f"--- Building Main Microflow: {mf_name} ---", "Microflows")

        # Resolve dependencies
        order_ent = self.builder.get_qualified_entity("Order")
        sub_mf = self.model.ToQualifiedName[IMicroflow](
            f"{self.MODULE}.SUB_CheckInventory"
        ).Resolve()

        # Create Shell
        mf = microflowService.CreateMicroflow(
            self.model,
            self.builder.module,
            mf_name,
            MicroflowReturnValue(
                DataType.Boolean, microflowExpressionService.CreateFromString("true")
            ),
            ValueTuple.Create[String, DataType](
                "PendingOrder", DataType.Object(order_ent.QualifiedName)
            ),
        )

        # Retrieve Association Names
        all_assocs = domainModelService.GetAllAssociations(
            self.model, [self.builder.module]
        )
        assoc_cust_order = next(
            a for a in all_assocs if a.Association.Name == "Customer_Order"
        )
        assoc_order_prod = next(
            a for a in all_assocs if a.Association.Name == "Order_Product"
        )

        # Build Activity List
        acts = []

        # 1. Retrieve Customer
        acts.append(
            microflowActivitiesService.CreateAssociationRetrieveSourceActivity(
                self.model,
                assoc_cust_order.Association,
                "RetrievedCustomer",
                "PendingOrder",
            )
        )

        # 2. Retrieve Products
        acts.append(
            microflowActivitiesService.CreateAssociationRetrieveSourceActivity(
                self.model,
                assoc_order_prod.Association,
                "RetrievedProductList",
                "PendingOrder",
            )
        )

        # 3. List Operation (Head) (Uses model.Create)
        acts.append(
            microflowActivitiesService.CreateListOperationActivity(
                self.model,
                "RetrievedProductList",
                "FirstProduct",
                self.model.Create[IHead](),
            )
        )

        # 4. Call Sub-Microflow
        call_act = self.model.Create[IActionActivity]()
        call_action = self.model.Create[IMicroflowCallAction]()
        call_act.Action = call_action
        call_action.OutputVariableName = "InventoryCheckResult"

        mf_call = self.model.Create[IMicroflowCall]()
        mf_call.Microflow = sub_mf.QualifiedName
        call_action.MicroflowCall = mf_call

        # Parameter Mapping
        mappings = {
            "StringParam": "'Sample Text'",
            "IntegerParam": "42",
            "ProductParam": "$FirstProduct",
            "StatusParam": f"{self.MODULE}.OrderStatus.Pending",
            "ProductListParam": "$RetrievedProductList",
        }
        target_params = {p.Name: p for p in microflowService.GetParameters(sub_mf)}

        for p_name, expr in mappings.items():
            mapping = self.model.Create[IMicroflowCallParameterMapping]()
            mapping.Parameter = target_params[p_name].QualifiedName
            mapping.Argument = microflowExpressionService.CreateFromString(expr)
            mf_call.AddParameterMapping(mapping)

        acts.append(call_act)

        # 5. Aggregate List
        acts.append(
            microflowActivitiesService.CreateAggregateListActivity(
                self.model,
                "RetrievedProductList",
                "ProductCount",
                AggregateFunctionEnum.Count,
            )
        )

        # 6. Change Order
        desc_attr = next(
            a for a in order_ent.GetAttributes() if a.Name == "Description"
        )
        status_attr = next(a for a in order_ent.GetAttributes() if a.Name == "Status")

        acts.append(
            microflowActivitiesService.CreateChangeAttributeActivity(
                self.model,
                desc_attr,
                ChangeActionItemType.Set,
                microflowExpressionService.CreateFromString(
                    "'Processed ' + toString($ProductCount) + ' items.'"
                ),
                "PendingOrder",
                CommitEnum.No,
            )
        )

        acts.append(
            microflowActivitiesService.CreateChangeAttributeActivity(
                self.model,
                status_attr,
                ChangeActionItemType.Set,
                microflowExpressionService.CreateFromString(
                    f"{self.MODULE}.OrderStatus.Confirmed"
                ),
                "PendingOrder",
                CommitEnum.No,
            )
        )

        # 7. Commit
        acts.append(
            microflowActivitiesService.CreateCommitObjectActivity(
                self.model, "PendingOrder", True, False
            )
        )

        # Insert all at once
        if microflowService.TryInsertAfterStart(mf, Array[IActionActivity](acts[::-1])):
            self.report(f"Successfully added {len(acts)} activities.")
        else:
            raise RuntimeError("Failed to generate microflow logic.")


# endregion

# region IOC & APP INITIALIZATION
# ===================================================================
# ==============     IOC & APP INITIALIZATION     ===================
# ===================================================================

from dependency_injector import containers, providers


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    message_hub = providers.Singleton(MendixMessageHub, post_message_func=config.post_message_func)
    
    # 新增 Telemetry 注入
    telemetry = providers.Singleton(PythonTelemetryService, hub=message_hub)

    rpc_handlers = providers.List()
    job_handlers = providers.List(providers.Singleton(GenerateMicroflowJob))
    session_handlers = providers.List()

    app_controller = providers.Singleton(
        AppController,
        rpc_handlers=rpc_handlers,
        job_handlers=job_handlers,
        session_handlers=session_handlers,
        message_hub=message_hub,
        telemetry=telemetry # 注入
    )

def onMessage(e: Any):
    controller = container.app_controller()
    try:
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)
        
        # 拦截追踪导出请求
        if request_object.get('type') == 'telemetry':
            forward_telemetry_to_jaeger(request_object.get('params', {}).get('endpoint'), 
                                       request_object.get('params', {}).get('spans'))
            return
        controller.dispatch(request_object)
    except Exception as ex:
        traceback.print_exc()

def initialize_app():
    container = Container()
    container.config.from_dict({"post_message_func": PostMessage})
    return container


# --- Application Start ---
PostMessage("backend:clear", "")
container = initialize_app()
PostMessage(
    "backend:info", "Backend Python script (Refactored) initialized successfully."
)

# endregion
