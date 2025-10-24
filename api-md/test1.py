from System import Array
from Mendix.StudioPro.ExtensionsAPI.Services import (
    IMicroflowService, IMicroflowActivitiesService,
    IMicroflowExpressionService, INameValidationService, IDomainModelService
)
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import CommitEnum, AggregateFunctionEnum
from Mendix.StudioPro.ExtensionsAPI.Model.DataTypes import DataType
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow, IMicroflowParameterObject, MicroflowReturnValue
from Mendix.StudioPro.ExtensionsAPI.Model.Enumerations import IEnumeration, IEnumerationValue
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import (
    IEntity, IAttribute, IAssociation, IDomainModel, AssociationType,
    IStringAttributeType, IBooleanAttributeType, IDateTimeAttributeType, IDecimalAttributeType,
    IEnumerationAttributeType, IStoredValue
)
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule, IFolderBase
from Mendix.StudioPro.ExtensionsAPI.Model import IModel
from Mendix.StudioPro.ExtensionsAPI.Model.Texts import IText
from System.Text.Json import JsonSerializer
from dependency_injector import containers, providers
import uuid
import threading
import json
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod

# Mendix and .NET related imports
import clr
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
# ShowDevTools()

PostMessage("backend:clear", '')


def print(e):
    PostMessage("backend:info", e)


# region your logic here

# --- Globals for services passed from C# ---
# These will be set when the script is executed in the C# host
model: IModel = currentApp
microflow_service: IMicroflowService = microflowService
activity_service: IMicroflowActivitiesService = microflowActivitiesService
expression_service: IMicroflowExpressionService = microflowExpressionService
name_service: INameValidationService = nameValidationService
domainModelService: IDomainModelService


def setup_order_management_environment():
    """
    Creates the necessary Module, Entities (Customer, Order, Product),
    an Enumeration (OrderStatus), and Associations for the business case.
    This function is idempotent; it won't create elements if they already exist.
    """
    print("--- Starting Environment Setup ---")
    transaction = None
    try:
        transaction = model.StartTransaction(
            "Setup Order Management Environment")

        module_name = "MyOrderModule"

        # 1. Create Module if it doesn't exist
        target_module = next(
            (m for m in model.Root.GetModules() if m.Name == module_name), None)
        if not target_module:
            target_module = model.Create[IModule]()
            target_module.Name = module_name
            model.Root.AddModule(target_module)
            print(f"Created module: {module_name}")

        domain_model = target_module.DomainModel

        # 2. Create Enumeration 'OrderStatus'
        enum_name = "OrderStatus"
        enum_qn_str = f"{module_name}.{enum_name}"
        if not model.ToQualifiedName[IEnumeration](enum_qn_str).Resolve():
            order_status_enum = model.Create[IEnumeration]()
            order_status_enum.Name = enum_name

            for val_name in ["Pending", "Confirmed", "Shipped", "Cancelled"]:
                enum_value = model.Create[IEnumerationValue]()
                enum_value.Name = val_name

                c = currentApp.Create[IText]()
                c.AddOrUpdateTranslation('en_US', val_name)
                enum_value.Caption = c
                order_status_enum.AddValue(enum_value)

            target_module.AddDocument(order_status_enum)
            print(f"Created enumeration: {enum_name}")

        # 3. Helper to create an entity with attributes
        def create_entity_if_not_exists(name: str, attributes: dict) -> IEntity:
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
                v = model.Create[IStoredValue]()
                # TODO: 根据类型分配默认值
                v.DefaultValue = 'true'  # or 'false'
                attr.Value = v
                entity.AddAttribute(attr)

            domain_model.AddEntity(entity)
            print(f"Created entity: {name}")
            return entity

        def setup_enum_type(enum_qn_str):
            # 1. 创建类型对象 (假设 model.Create[T]() 已经通过某种方式修复或可以工作)
            enum_type = model.Create[IEnumerationAttributeType]()

            # 2. 获取 QualifiedName
            enum_qn = model.ToQualifiedName[IEnumeration](enum_qn_str)

            # 3. 标准属性赋值 (最安全的方式)
            enum_type.Enumeration = enum_qn

            # 4. 返回设置好的类型对象
            return enum_type
        # 4. Define and create entities
        customer_entity = create_entity_if_not_exists("Customer", {
            "Name": lambda: model.Create[IStringAttributeType](),
            "IsVIP": lambda: model.Create[IBooleanAttributeType]()
        })

        product_entity = create_entity_if_not_exists("Product", {
            "Name": lambda: model.Create[IStringAttributeType](),
            "Price": lambda: model.Create[IDecimalAttributeType]()
        })

        order_entity = create_entity_if_not_exists("Order", {
            "OrderDate": lambda: model.Create[IDateTimeAttributeType](),
            "Description": lambda: model.Create[IStringAttributeType](),
            "Status": lambda: setup_enum_type(enum_qn_str)
        })

        # 5. Create Associations if they don't exist
        if not any(a for a in domainModelService.GetAllAssociations(model, [target_module]) if a.Association.Name == "Customer_Order"):
            assoc = customer_entity.AddAssociation(order_entity)
            assoc.Name = "Customer_Order"
            print("Created association: Customer_Order")

        if not any(a for a in domainModelService.GetAllAssociations(model, [target_module]) if a.Association.Name == "Order_Product"):
            assoc = order_entity.AddAssociation(product_entity)
            assoc.Name = "Order_Product"
            assoc.Type = AssociationType.ReferenceSet
            print("Created association: Order_Product")

        # 6. Create a placeholder sub-microflow for the main example to call
        sub_mf_name = "SUB_CheckInventory"
        if not model.ToQualifiedName[IMicroflow](f"{module_name}.{sub_mf_name}").Resolve():
            ret_exp = microflowExpressionService.CreateFromString('13')
            microflow_service.CreateMicroflow(
                model, target_module, sub_mf_name, MicroflowReturnValue(DataType.Integer, ret_exp), [])
            print(f"Created placeholder microflow: {sub_mf_name}")

        transaction.Commit()
        print("--- Environment Setup Complete ---")

    except Exception as e:
        print(f"An error occurred during setup: {e} {traceback.format_exc()}")
        if transaction:
            transaction.Rollback()


def create_order_processing_microflow():
    """
    Creates a microflow 'ACT_ProcessPendingOrder' with a meaningful business process,
    demonstrating various common activity types in a linear flow.
    """
    print("\n--- Starting Microflow Creation ---")
    transaction = None
    try:
        module_name = "MyOrderModule"

        # 0. Find the target module/container
        container = next((m for m in model.Root.GetModules()
                         if m.Name == module_name), None)
        if not container:
            raise ValueError(
                f"Module '{module_name}' not found. Please run the setup function first.")

        # 1. Find all necessary model elements
        order_entity = model.ToQualifiedName[IEntity](
            f"{module_name}.Order").Resolve()
        customer_order_assoc = model.ToQualifiedName[IAssociation](
            f"{module_name}.Customer_Order").Resolve()
        order_product_assoc = model.ToQualifiedName[IAssociation](
            f"{module_name}.Order_Product").Resolve()
        sub_mf_to_call = model.ToQualifiedName[IMicroflow](
            f"{module_name}.SUB_CheckInventory").Resolve()
        description_attr = next(
            a for a in order_entity.GetAttributes() if a.Name == "Description")
        status_attr = next(
            a for a in order_entity.GetAttributes() if a.Name == "Status")

        if not all([order_entity, customer_order_assoc, order_product_assoc, sub_mf_to_call, description_attr, status_attr]):
            raise ValueError(
                "One or more required model elements were not found.")

        # 2. Define Microflow Parameters and Return Value
        param = model.Create[IMicroflowParameterObject]()
        param.Name = "PendingOrder"
        param.Type = DataType.Object(order_entity.QualifiedName)
        params_array = Array[IMicroflowParameterObject]([param])

        # 3. Create the Microflow shell
        mf_name = name_service.GetValidName("ACT_ProcessPendingOrder")
        microflow = microflow_service.CreateMicroflow(
            model, container, mf_name, None, params_array)
        print(f"Created microflow shell: {mf_name}")

        # 4. Create a list of activities to be inserted
        activities = []

        # Activity 1: Retrieve Customer via association
        activities.append(activity_service.CreateAssociationRetrieveSourceActivity(
            model, customer_order_assoc, "RetrievedCustomer", "PendingOrder"
        ))

        # Activity 2: Retrieve Product list via association
        activities.append(activity_service.CreateAssociationRetrieveSourceActivity(
            model, order_product_assoc, "RetrievedProductList", "PendingOrder"
        ))

        # Activity 3: Log Message
        log_activity = model.Create()  # IActionActivity
        log_action = model.Create()  # ILogMessageAction
        log_action.Level = 0  # Info
        log_action.MessageTemplate.AddOrUpdateTranslation(
            "en_US", "Processing order for customer: {1}")
        # Add parameter to the template
        log_param = model.Create()  # ILogParameter
        log_param.Expression = expression_service.CreateFromString(
            "$RetrievedCustomer/Name")
        log_action.AddParameter(log_param)
        log_activity.Action = log_action
        activities.append(log_activity)

        # Activity 4: Call Sub-Microflow
        call_sub_mf_activity = model.Create()  # IActionActivity
        call_sub_mf_action = model.Create()  # IMicroflowCallAction
        call_sub_mf_action.UseReturnVariable = False
        mf_call = model.Create()  # IMicroflowCall
        mf_call.Microflow = sub_mf_to_call.QualifiedName
        call_sub_mf_action.MicroflowCall = mf_call
        call_sub_mf_activity.Action = call_sub_mf_action
        activities.append(call_sub_mf_activity)

        # Activity 5: Aggregate List (Count products)
        activities.append(activity_service.CreateAggregateListActivity(
            model, "RetrievedProductList", "ProductCount", AggregateFunctionEnum.Count
        ))

        # Activity 6: Change Object (Update Description)
        desc_expr = expression_service.CreateFromString(
            f"'Order processed with ' + toString($ProductCount) + ' items.'")
        activities.append(activity_service.CreateChangeAttributeActivity(
            model, description_attr, 0, desc_expr, "PendingOrder", CommitEnum.No  # 0 is 'Set'
        ))

        # Activity 7: Change Object (Update Status)
        status_expr = expression_service.CreateFromString(
            f"MyOrderModule.OrderStatus.Confirmed")
        activities.append(activity_service.CreateChangeAttributeActivity(
            model, status_attr, 0, status_expr, "PendingOrder", CommitEnum.No  # 0 is 'Set'
        ))

        # Activity 8: Commit Object
        activities.append(activity_service.CreateCommitObjectActivity(
            model, "PendingOrder", True, True
        ))

        # 5. Insert all created activities into the microflow
        transaction = model.StartTransaction(
            "Create Order Processing Microflow")

        # Note: The API only supports inserting activities in a linear sequence.
        # Creating branching logic (Decisions, Merges) with connected flows is not supported.
        activities_array = Array[type(activities[0])](activities)
        success = microflow_service.TryInsertAfterStart(
            microflow, activities_array)

        if not success:
            raise RuntimeError(
                "Failed to insert activities into the microflow.")

        transaction.Commit()
        print("--- Microflow Creation Complete ---")

    except Exception as e:
        print(f"An error occurred during microflow creation: {e}")
        if transaction:
            transaction.Rollback()


setup_order_management_environment()
# endregion
