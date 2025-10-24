from Mendix.StudioPro.ExtensionsAPI.Services import (
    IMicroflowService,
    IMicroflowActivitiesService,
    IMicroflowExpressionService,
    INameValidationService
)
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows.Actions import CommitEnum, ChangeActionItemType
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import IEntity
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IModule, IFolderBase
from Mendix.StudioPro.ExtensionsAPI.Model import IModel
from typing import Optional
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
# 导入必要的 Mendix API 命名空间
# pythonnet 会自动将 .NET 命名空间映射为 Python 模块


def find_module_by_name(model: IModel, module_name: str) -> Optional[IModule]:
    """
    根据名称查找 Mendix 模块。

    :param model: 当前应用模型对象。
    :param module_name: 要查找的模块的名称。
    :return: 如果找到，返回 IModule 对象；否则返回 None。
    """
    modules = model.Root.GetModules()
    target_module = next((m for m in modules if m.Name == module_name), None)
    return target_module


def find_deep_folder(start_container: IFolderBase, folder_path: str) -> Optional[IFolderBase]:
    """
    从一个起始容器（模块或文件夹）开始，根据路径查找深层文件夹。

    :param start_container: 查找的起始点 (IModule 或 IFolder)。
    :param folder_path: 相对文件夹路径，例如 "Microflows/Utilities/Validation"。
    :return: 如果找到，返回目标 IFolderBase 对象；否则返回 None。
    """
    if not folder_path:
        return start_container

    # 分割路径并过滤掉空字符串（例如，如果路径以 '/' 结尾）
    path_segments = [segment for segment in folder_path.replace(
        '\\', '/').split('/') if segment]

    current_container = start_container
    for segment in path_segments:
        subfolders = current_container.GetFolders()
        next_container = next(
            (f for f in subfolders if f.Name == segment), None)

        if next_container is None:
            # 在路径的任何一点没找到文件夹，则返回 None
            return None

        current_container = next_container

    return current_container


def get_module_or_folder(model: IModel, full_path: str) -> Optional[IFolderBase]:
    """
    一个便捷函数，用于通过完整路径获取模块或其内部的文件夹。

    :param model: 当前应用模型对象。
    :param full_path: 完整路径，例如 "MyFirstModule" 或 "MyFirstModule/Microflows/Core"。
    :return: 如果找到，返回目标 IFolderBase 对象；否则返回 None。
    """
    path_parts = [part for part in full_path.replace(
        '\\', '/').split('/') if part]
    if not path_parts:
        return None

    module_name = path_parts[0]
    module = find_module_by_name(model, module_name)

    if module is None:
        return None

    # 如果路径只有模块名，则返回模块本身
    if len(path_parts) == 1:
        return module

    # 否则，在模块内查找剩余的文件夹路径
    remaining_path = "/".join(path_parts[1:])
    return find_deep_folder(module, remaining_path)
# 这个函数将从 C# 中被调用


def create_customer_microflow(
    model: IModel,
    microflow_service: IMicroflowService,
    activity_service: IMicroflowActivitiesService,
    expression_service: IMicroflowExpressionService,
    name_service: INameValidationService
):
    """
    在指定的容器（模块或文件夹）中创建一个新的微流。
    这个微流将创建、更改并提交一个 Customer 对象。
    """
    print("Python script: Starting microflow creation...")

    # 使用我们的新函数来找到目标容器
    # 目标：MyFirstModule 模块下的一个深层文件夹 "Generated/Customers"
    target_path = "MyFirstModule/Generated/Customers"
    container = get_module_or_folder(model, target_path)

    if container is None:
        print(
            f"Error: Container at path '{target_path}' not found. Make sure the module and folders exist.")
        # 在实际应用中，你可能想在这里创建文件夹
        return

    print(
        f"Python script: Found container '{container.Name}' for creating the microflow.")

    transaction = None
    try:
        # 1. 开启事务
        transaction = model.StartTransaction(
            "Create Customer Microflow via Python")
        print("Python script: Transaction started.")

        # 2. 查找我们需要的实体 (假设它存在)
        customer_qn = model.ToQualifiedName[IEntity]("MyFirstModule.Customer")
        customer_entity = customer_qn.Resolve()

        if customer_entity is None:
            print("Error: Entity 'MyFirstModule.Customer' not found.")
            transaction.Rollback()
            return

        print(
            f"Python script: Found entity '{customer_entity.QualifiedName.FullName}'.")

        # 3. 创建一个新的微流
        microflow_name = name_service.GetValidName(
            "ACT_CreateAndChangeCustomer")
        new_mf = microflow_service.CreateMicroflow(
            model, container, microflow_name, None, None)
        print(f"Python script: Created microflow '{microflow_name}'.")

        # 4. 创建活动
        # 活动 1: 创建 Customer 对象
        output_var_name = "NewCustomer"
        create_activity = activity_service.CreateCreateObjectActivity(
            model,
            customer_entity,
            output_var_name,
            CommitEnum.No,  # 我们将在后面手动提交
            False,
            None
        )
        print("Python script: Created 'Create Object' activity.")

        # 活动 2: 修改 Customer 对象的 Name 属性
        # 首先，找到 'Name' 属性
        name_attribute = next(
            (attr for attr in customer_entity.GetAttributes() if attr.Name == "Name"), None)
        if name_attribute is None:
            print("Error: Attribute 'Name' not found on Customer entity.")
            transaction.Rollback()
            return

        # 创建一个表达式来设置新值
        new_value_expr = expression_service.CreateFromString(
            "'Automated Customer Name'")

        change_activity = activity_service.CreateChangeAttributeActivity(
            model,
            name_attribute,
            ChangeActionItemType.Set,
            new_value_expr,
            output_var_name,  # 我们要修改的变量
            CommitEnum.No
        )
        print("Python script: Created 'Change Object' activity.")

        # 活动 3: 提交 Customer 对象
        commit_activity = activity_service.CreateCommitObjectActivity(
            model,
            output_var_name,  # 我们要提交的变量
            True,  # WithEvents
            False  # RefreshInClient
        )
        print("Python script: Created 'Commit' activity.")

        # 5. 将活动插入微流中
        activities_to_insert = [create_activity,
                                change_activity, commit_activity]
        # 注意：C# 数组需要特殊处理
        from System import Array
        activity_array = Array[type(create_activity)](activities_to_insert)

        success = microflow_service.TryInsertAfterStart(new_mf, activity_array)

        if success:
            print("Python script: Successfully inserted activities into the microflow.")
        else:
            print("Python script: Failed to insert activities.")
            transaction.Rollback()
            return

        # 6. 提交事务
        transaction.Commit()
        print("Python script: Transaction committed successfully!")

    except Exception as e:
        print(f"An error occurred: {e}")
        if transaction is not None:
            transaction.Rollback()
            print("Python script: Transaction rolled back due to an error.")


create_customer_microflow(currentApp, microflowService, microflowActivitiesService,
                          microflowExpressionService, nameValidationService)
# endregion
