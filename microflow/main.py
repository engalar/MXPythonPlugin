# region FRAMEWORK CODE
import json
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
    def __init__(self, percent: float, message: str, stage: Optional[str] = None, metadata: Optional[Dict] = None):
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

class AppController:
    """Routes incoming messages to registered handlers. Obeys OCP."""
    def __init__(self, rpc_handlers: Iterable[IRpcHandler], job_handlers: Iterable[IJobHandler],
                 session_handlers: Iterable[ISessionHandler], message_hub: IMessageHub):
        self._rpc = {h.command_type: h for h in rpc_handlers}
        self._jobs = {h.command_type: h for h in job_handlers}
        self._sessions = {h.command_type: h for h in session_handlers}
        self._hub = message_hub
        print(f"Controller initialized. RPCs: {list(self._rpc.keys())}, Jobs: {list(self._jobs.keys())}, Sessions: {list(self._sessions.keys())}")

    def dispatch(self, request: Dict):
        msg_type = request.get("type")
        try:
            if msg_type == "RPC": self._handle_rpc(request)
            elif msg_type == "JOB_START": self._handle_job_start(request)
            elif msg_type == "SESSION_CONNECT": self._handle_session_connect(request)
            elif msg_type == "SESSION_DISCONNECT": self._handle_session_disconnect(request)
            else: raise ValueError(f"Unknown message type: {msg_type}")
        except Exception as e:
            req_id = request.get("reqId")
            if req_id:
                # MODIFIED: Capture and send the full traceback string
                tb_string = traceback.format_exc()
                self._hub.send({"type": "RPC_ERROR", "reqId": req_id, "message": str(e), "traceback": tb_string})
            traceback.print_exc()

    def _handle_rpc(self, request):
        handler = self._rpc.get(request["method"])
        if not handler: raise ValueError(f"No RPC handler for '{request['method']}'")
        result = handler.execute(request.get("params"))
        self._hub.send({"type": "RPC_SUCCESS", "reqId": request["reqId"], "data": result})

    def _handle_job_start(self, request):
        handler = self._jobs.get(request["method"])
        if not handler: raise ValueError(f"No Job handler for '{request['method']}'")
        
        job_id = f"job-{uuid.uuid4()}"
        
        class JobContext(IJobContext):
            def __init__(self, job_id: str, hub: IMessageHub):
                self.job_id = job_id
                self._hub = hub
            def report_progress(self, progress: ProgressUpdate):
                self._hub.send({"type": "JOB_PROGRESS", "jobId": self.job_id, "progress": progress.to_dict()})

        context = JobContext(job_id, self._hub)
        
        def job_runner():
            try:
                # To test job error, uncomment the next line
                # raise ValueError("This is a deliberate job error")
                result = handler.run(request.get("params"), context)
                self._hub.send({"type": "JOB_SUCCESS", "jobId": job_id, "data": result})
            except Exception as e:
                # MODIFIED: Capture and send the full traceback string for jobs
                tb_string = traceback.format_exc()
                self._hub.send({"type": "JOB_ERROR", "jobId": job_id, "message": str(e), "traceback": tb_string})
                traceback.print_exc()

        thread = threading.Thread(target=job_runner, daemon=True)
        thread.start()
        self._hub.send({"type": "JOB_STARTED", "reqId": request["reqId"], "jobId": job_id})

    def _handle_session_connect(self, request):
        handler = self._sessions.get(request["channel"])
        if handler: handler.on_connect(request["sessionId"], request.get("payload"))

    def _handle_session_disconnect(self, request):
        handler = self._sessions.get(request["channel"])
        if handler: handler.on_disconnect(request["sessionId"])

# endregion

# region BUSINESS LOGIC CODE
# ===================================================================
# ===============     BUSINESS LOGIC CODE     =======================
# ===================================================================
# This section contains your feature-specific command handlers.
# To add a new feature, create a new class implementing ICommandHandler
# or IAsyncCommandHandler, and register it in the Container below.
# -------------------------------------------------------------------

# region Mendix SDK Imports & Helpers for Microflow Generation
import time
from System import ValueTuple, String, Array
from Mendix.StudioPro.ExtensionsAPI.Model import Location
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow, IMicroflowParameterObject, IActionActivity, IMicroflowCallAction, IMicroflowCall, MicroflowReturnValue, IHead, IMicroflowCallParameterMapping
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import CommitEnum, ChangeActionItemType, AggregateFunctionEnum
from Mendix.StudioPro.ExtensionsAPI.Model.DataTypes import DataType
from Mendix.StudioPro.ExtensionsAPI.Model.Texts import IText
from Mendix.StudioPro.ExtensionsAPI.Model.Enumerations import IEnumeration, IEnumerationValue
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import (
    IEntity, IAttribute, IStoredValue, IAssociation, IDomainModel, AssociationType,
    IStringAttributeType, IBooleanAttributeType, IDateTimeAttributeType, IDecimalAttributeType,

    IEnumerationAttributeType, EntityAssociation
)
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IProject, IModule
# These services are assumed to be globally available in the Mendix script environment
# microflowService, domainModelService, microflowExpressionService, microflowActivitiesService
# endregion

class GenerateMicroflowJob(IJobHandler):
    """
    A long-running job that programmatically generates a complete Mendix
    module with a domain model and a complex microflow, based on test_mf.py.
    """
    command_type = "microflow:generate"

    def __init__(self):
        # Access the global 'currentApp' provided by the Mendix environment
        self._app = currentApp

    def run(self, payload: Dict, context: IJobContext):
        # --- 1. Setup dynamic reporting within the job context ---
        progress_state = {'percent': 0, 'stage': 'Initializing', 'logs': []}

        def report(message, stage_override=None, percent_increment=2):
            new_percent = min(progress_state['percent'] + percent_increment, 99)
            progress_state['percent'] = new_percent

            if stage_override:
                progress_state['stage'] = stage_override
            
            progress_state['logs'].append(message)
            
            context.report_progress(ProgressUpdate(
                percent=new_percent,
                message=message.replace("---", "").strip(),
                stage=progress_state['stage'],
                metadata={'logs': list(progress_state['logs'])}
            ))
            time.sleep(0.05) # Slow down for UI to keep up

        # --- 2. Adapt logic from test_mf.py to be executed within this job ---
        try:
            run_generation_logic(self._app, self._app.Root, report)

            # --- 3. Report final success ---
            final_message = "Solution generated successfully!"
            progress_state['logs'].append(f"--- {final_message} ---")
            context.report_progress(ProgressUpdate(
                percent=100, message=final_message, stage="Completed",
                metadata={'logs': list(progress_state['logs'])}
            ))
            return {"status": "Completed", "module": "MyOrderModule"}
        except Exception as e:
            tb_string = traceback.format_exc()
            report(f"FATAL ERROR: A problem occurred during generation.\n{tb_string}", "Error", 0)
            raise # Re-raise to let the framework send a JOB_ERROR

def run_generation_logic(model, project, report):
    """
    Contains the main, refactored logic from test_mf.py.
    Uses the provided 'report' function for all logging and progress updates.
    """
    # --- Helper: TransactionManager with integrated reporting ---
    class TransactionManager:
        def __init__(self, app, transaction_name):
            self.app, self.name, self.transaction = app, transaction_name, None
        def __enter__(self):
            self.transaction = self.app.StartTransaction(self.name)
            report(f"Transaction '{self.name}' started.", percent_increment=5)
            return self.transaction
        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.transaction:
                if exc_type is None:
                    self.transaction.Commit()
                    report(f"Transaction '{self.name}' committed successfully.")
                else:
                    self.transaction.Rollback()
                    report(f"Transaction '{self.name}' rolled back due to error: {exc_val}")
                self.transaction.Dispose()
            return False

    # --- Start of adapted logic ---
    MODULE_NAME = 'MyOrderModule'
    
    with TransactionManager(model, "Generate Order Management Solution"):
        # STEP 1: Setup Environment
        report("--- Task: Setup Order Management Environment ---", "Setup")
        
        # Ensure Module
        module = next((m for m in project.GetModules() if m.Name == MODULE_NAME), None)
        if not module:
            module = model.Create[IModule]()
            module.Name = MODULE_NAME
            project.AddModule(module)
            report(f"Created module: '{MODULE_NAME}'", percent_increment=10)
        else:
            report(f"Module '{MODULE_NAME}' already exists.")
            
        domain_model = module.DomainModel

        # Create Enum 'OrderStatus'
        enum_qn = f"{MODULE_NAME}.OrderStatus"
        if not model.ToQualifiedName[IEnumeration](enum_qn).Resolve():
            enum = model.Create[IEnumeration]()
            enum.Name = "OrderStatus"
            for val_name in ["Pending", "Confirmed", "Shipped", "Cancelled"]:
                val = model.Create[IEnumerationValue](); val.Name = val_name
                txt = model.Create[IText](); txt.AddOrUpdateTranslation('en_US', val_name)
                val.Caption = txt; enum.AddValue(val)
            module.AddDocument(enum)
            report("Created enumeration: OrderStatus")
            
        # --- MODIFICATION START: Using correct Location API ---
        # Helper to create entities with positioning
        def _ensure_entity(name, attrs, location_coords: tuple[int, int]):
            qn = f"{MODULE_NAME}.{name}"
            entity = model.ToQualifiedName[IEntity](qn).Resolve()
            loc = Location(location_coords[0], location_coords[1])
            
            if entity:
                # If entity exists, just update its location for a consistent layout
                entity.Location = loc
                report(f"Found entity '{name}', repositioned to {location_coords}.")
                return

            entity = model.Create[IEntity]()
            entity.Name = name
            entity.Location = loc # Set visual location using the correct API
            for attr_name, attr_type_creator in attrs.items():
                attr = model.Create[IAttribute](); attr.Name = attr_name
                attr.Type = attr_type_creator(); attr.Value = model.Create[IStoredValue]()
                entity.AddAttribute(attr)
            domain_model.AddEntity(entity)
            report(f"Created entity: {name} at position {location_coords}")
        
        # Define layout constants for the domain model
        START_X, START_Y = 100, 200
        ENTITY_SPACING_X = 300

        # Create Entities with defined positions for a clean layout
        _ensure_entity("Customer", {"Name": model.Create[IStringAttributeType]}, (START_X, START_Y))
        def _create_enum_type():
            et = model.Create[IEnumerationAttributeType]()
            et.Enumeration = model.ToQualifiedName[IEnumeration](enum_qn)
            return et
        _ensure_entity("Order", {"Description": model.Create[IStringAttributeType], "Status": _create_enum_type}, (START_X + ENTITY_SPACING_X, START_Y))
        _ensure_entity("Product", {"Price": model.Create[IDecimalAttributeType]}, (START_X + 2 * ENTITY_SPACING_X, START_Y))
        # --- MODIFICATION END ---

        customer_entity = model.ToQualifiedName[IEntity](f"{MODULE_NAME}.Customer").Resolve()
        order_entity = model.ToQualifiedName[IEntity](f"{MODULE_NAME}.Order").Resolve()
        product_entity = model.ToQualifiedName[IEntity](f"{MODULE_NAME}.Product").Resolve()

        # Create Associations
        all_assocs = domainModelService.GetAllAssociations(model, [module])
        if not any(a for a in all_assocs if a.Association.Name == "Customer_Order"):
            customer_entity.AddAssociation(order_entity).Name = "Customer_Order"
            report("Created association: Customer_Order")
        if not any(a for a in all_assocs if a.Association.Name == "Order_Product"):
            assoc = order_entity.AddAssociation(product_entity)
            assoc.Name = "Order_Product"; assoc.Type = AssociationType.ReferenceSet
            report("Created association: Order_Product")
        
        # Create Sub-Microflow with diverse parameters
        sub_mf_name = "SUB_CheckInventory"
        sub_mf_qn = f"{MODULE_NAME}.{sub_mf_name}"
        if not model.ToQualifiedName[IMicroflow](sub_mf_qn).Resolve():
            params = [
                ValueTuple.Create[String, DataType]("StringParam", DataType.String),
                ValueTuple.Create[String, DataType]("IntegerParam", DataType.Integer),
                ValueTuple.Create[String, DataType]("ProductParam", DataType.Object(product_entity.QualifiedName)),
                ValueTuple.Create[String, DataType]("StatusParam", DataType.Enumeration(model.ToQualifiedName[IEnumeration](enum_qn))),
                ValueTuple.Create[String, DataType]("ProductListParam", DataType.List(product_entity.QualifiedName)),
            ]
            microflowService.CreateMicroflow(
                model, module, sub_mf_name, 
                MicroflowReturnValue(DataType.Boolean, microflowExpressionService.CreateFromString("true")), 
                Array[ValueTuple[String, DataType]](params)
            )
            report(f"Created sub-microflow: {sub_mf_name}")

        report("--- Environment Setup Complete ---", "Building Microflow", percent_increment=15)
        
        # STEP 2: Create Main Microflow
        mf_name = "ACT_ProcessPendingOrder"
        if not model.ToQualifiedName[IMicroflow](f"{MODULE_NAME}.{mf_name}").Resolve():
            report(f"--- Task: Create Microflow '{mf_name}' ---", "Building Microflow")
            all_assocs = domainModelService.GetAllAssociations(model, [module]) # Re-fetch
            customer_order_assoc = next(a for a in all_assocs if a.Association.Name == 'Customer_Order')
            order_product_assoc = next(a for a in all_assocs if a.Association.Name == 'Order_Product')
            sub_mf = model.ToQualifiedName[IMicroflow](sub_mf_qn).Resolve()
            desc_attr = next(a for a in order_entity.GetAttributes() if a.Name == "Description")
            status_attr = next(a for a in order_entity.GetAttributes() if a.Name == "Status")

            mf = microflowService.CreateMicroflow(
                model, module, mf_name, MicroflowReturnValue(DataType.Boolean, microflowExpressionService.CreateFromString("true")), 
                ValueTuple.Create[String, DataType]('PendingOrder', DataType.Object(order_entity.QualifiedName))
            )
            report(f"Created microflow shell: {mf_name}")
            
            # Helper to create Microflow Call Activity
            def createMicroflowCallActivity(sub_mf, mappings, out_var):
                act = model.Create[IActionActivity]()
                call_action = model.Create[IMicroflowCallAction](); act.Action = call_action
                call_action.OutputVariableName = out_var
                mf_call = model.Create[IMicroflowCall](); mf_call.Microflow = sub_mf.QualifiedName
                call_action.MicroflowCall = mf_call
                
                target_params = {p.Name: p for p in microflowService.GetParameters(sub_mf)}
                for m in mappings:
                    param_name, arg_expr = m.Item1, m.Item2
                    mapping = model.Create[IMicroflowCallParameterMapping]()
                    mapping.Parameter = target_params[param_name].QualifiedName
                    mapping.Argument = microflowExpressionService.CreateFromString(arg_expr)
                    mf_call.AddParameterMapping(mapping)
                return act

            # Define activities
            activities = [
                microflowActivitiesService.CreateAssociationRetrieveSourceActivity(model, customer_order_assoc.Association, "RetrievedCustomer", "PendingOrder"),
                microflowActivitiesService.CreateAssociationRetrieveSourceActivity(model, order_product_assoc.Association, "RetrievedProductList", "PendingOrder"),
                microflowActivitiesService.CreateListOperationActivity(model, "RetrievedProductList", "FirstProduct", model.Create[IHead]()),
                createMicroflowCallActivity(sub_mf, [
                    ValueTuple.Create("StringParam", "'Sample Text'"),
                    ValueTuple.Create("IntegerParam", "42"),
                    ValueTuple.Create("ProductParam", "$FirstProduct"),
                    ValueTuple.Create("StatusParam", f"{MODULE_NAME}.OrderStatus.Pending"),
                    ValueTuple.Create("ProductListParam", "$RetrievedProductList"),
                ], "InventoryCheckResult"),
                microflowActivitiesService.CreateAggregateListActivity(model, "RetrievedProductList", "ProductCount", AggregateFunctionEnum.Count),
                microflowActivitiesService.CreateChangeAttributeActivity(model, desc_attr, ChangeActionItemType.Set, microflowExpressionService.CreateFromString("'Processed with ' + toString($ProductCount) + ' items.'"), "PendingOrder", CommitEnum.No),
                microflowActivitiesService.CreateChangeAttributeActivity(model, status_attr, ChangeActionItemType.Set, microflowExpressionService.CreateFromString(f"{MODULE_NAME}.OrderStatus.Confirmed"), "PendingOrder", CommitEnum.No),
                microflowActivitiesService.CreateCommitObjectActivity(model, "PendingOrder", True, False)
            ]
            report(f"Defined {len(activities)} activities for the microflow.")

            if microflowService.TryInsertAfterStart(mf, Array[IActionActivity](activities[::-1])):
                report("Successfully inserted all activities into microflow.")
            else:
                raise RuntimeError("Failed to insert activities into microflow.")
            
            report(f"--- Success: Microflow '{mf_name}' Created ---", "Finalizing")

            
# endregion 

# region IOC & APP INITIALIZATION
# ===================================================================
# ==============     IOC & APP INITIALIZATION     ===================
# ===================================================================

from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    """The application's Inversion of Control (IoC) container."""
    config = providers.Configuration()

    # --- Framework Services (DIP) ---
    message_hub: providers.Provider[IMessageHub] = providers.Singleton(
        MendixMessageHub,
        post_message_func=config.post_message_func
    )

    # --- Business Logic Handlers (OCP) ---
    rpc_handlers = providers.List(
    )
    job_handlers = providers.List(
        providers.Singleton(GenerateMicroflowJob)
    )
    session_handlers = providers.List(
    )

    # --- Core Controller ---
    app_controller = providers.Singleton(
        AppController,
        rpc_handlers=rpc_handlers,
        job_handlers=job_handlers,
        session_handlers=session_handlers,
        message_hub=message_hub,
    )

def onMessage(e: Any):
    """Entry point called by Mendix Studio Pro for messages from the UI."""
    if e.Message != "frontend:message": return
    controller = container.app_controller()
    try:
        request_string = JsonSerializer.Serialize(e.Data)
        request_object = json.loads(request_string)
        controller.dispatch(request_object)
    except Exception as ex:
        traceback.print_exc()

def initialize_app():
    container = Container()
    container.config.from_dict({"post_message_func": PostMessage})
    return container

# --- Application Start ---
PostMessage("backend:clear", '')
container = initialize_app()
PostMessage("backend:info", "Backend Python script (Refactored) initialized successfully.")

# endregion