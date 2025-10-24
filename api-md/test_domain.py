#region framework
import json
import clr
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# 导入所有常用接口和系统类型
from System import String, ValueTuple, Func, Boolean
from System.Collections.Generic import IReadOnlyList, KeyValuePair
from Mendix.StudioPro.ExtensionsAPI.Model import Location
from Mendix.StudioPro.ExtensionsAPI.Model.UntypedModel import PropertyType
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IProject, IModule, IFolder, IFolderBase
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import (
    IMicroflow, IActionActivity, IMicroflowCallAction, IMicroflowCall, IMicroflowCallParameterMapping, MicroflowReturnValue
)
from Mendix.StudioPro.ExtensionsAPI.Model.Pages import IPage
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import (
    IDomainModel, IEntity, IAttribute, IStoredValue, IIntegerAttributeType, IAssociation,
    AssociationDirection, IGeneralization, INoGeneralization
)
from Mendix.StudioPro.ExtensionsAPI.Model.Enumerations import IEnumeration, IEnumerationValue
from Mendix.StudioPro.ExtensionsAPI.Model.Constants import IConstant
from Mendix.StudioPro.ExtensionsAPI.Model.Texts import IText
from Mendix.StudioPro.ExtensionsAPI.Model.DataTypes import DataType

# 清除日志（方便每次运行查看结果）
PostMessage("backend:clear",'')
def info(e):
	PostMessage("backend:info", f'{e}')
_dir=dir
def dir(e):
	PostMessage("backend:info", f'{_dir(e)}')	

def error(e):
	PostMessage("backend:error", f'{e}')
# --- 辅助类：事务管理器 ---
class TransactionManager:
    """Provides a context manager for handling Mendix model transactions."""
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
                PostMessage("backend:info", f"Transaction '{self.name}' committed.")
            else:
                self.transaction.Rollback()
                PostMessage("backend:error", f"Transaction '{self.name}' rolled back due to error: {exc_val}")
            self.transaction.Dispose()
        return False # 允许异常继续传播
# --- 辅助函数：查找或创建模块 ---
def ensure_module(app, project: IProject, module_name: str) -> IModule:
    existing_module = next((m for m in project.GetModules() if m.Name == module_name), None)
    if existing_module:
        PostMessage("backend:info", f"Module '{module_name}' already exists.")
        return existing_module
    else:
        with TransactionManager(app, f'Create module {module_name}'):
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
            with TransactionManager(app, f'Create folder {part} in {module.Name}'):
                new_folder = app.Create[IFolder]()
                new_folder.Name = part
                current_container.AddFolder(new_folder)
                current_container = new_folder
                PostMessage("backend:info", f"Created folder: {module.Name}/{path}")
        else:
            current_container = next_container
            
    return current_container
# --- 全局项目访问 ---
project = currentApp.Root

#endregion


#region component


def run_domain_model_demo(app, project):
    # --- 实体名称定义 ---
    PARENT_ENTITY_NAME = 'MyParent'
    CHILD_ENTITY_NAME = 'MyChild'
    MODULE_NAME = 'MyCustomModule' # 假设模块已存在

    PostMessage("backend:info", "--- Running Domain Model Demo ---")

    module = ensure_module(app, project, MODULE_NAME)
    domain_model = module.DomainModel

    # --- 辅助函数：查找或创建实体 ---
    def ensure_entity(app, domain_model: IDomainModel, entity_name: str, x: int, y: int) -> IEntity:
        existing_entity = next((e for e in domain_model.GetEntities() if e.Name == entity_name), None)
        if existing_entity:
            # 如果存在，更新其布局位置 (Layout)
            with TransactionManager(app, f'Update layout for {entity_name}'):
                existing_entity.Location = Location(x, y)
            PostMessage("backend:info", f"Entity '{entity_name}' exists, layout updated.")
            return existing_entity
        else:
            with TransactionManager(app, f'Create entity {entity_name}'):
                entity = app.Create[IEntity]()
                entity.Name = entity_name
                entity.Location = Location(x, y)
                domain_model.AddEntity(entity)
                PostMessage("backend:success", f"Entity '{entity_name}' created at ({x}, {y}).")
                return entity

    # 1. 创建或获取父子实体，并设置布局
    parent_entity = ensure_entity(app, domain_model, PARENT_ENTITY_NAME, 100, 100)
    child_entity = ensure_entity(app, domain_model, CHILD_ENTITY_NAME, 100, 300)

    # 2. 设置继承 (Generalization) - 幂等性检查
    
    # 获取继承属性的值（可能是 IGeneralization 或 INoGeneralization）
    current_generalization = child_entity.Generalization
    
    # 检查是否已经继承自 MyParent
    is_already_parented = False
    if current_generalization.GetType().Name.endswith('GeneralizationProxy'):
        try:
            # 使用 IGeneralization 接口的属性来获取父实体
            parent_qn = current_generalization.Generalization 
            if parent_qn and parent_qn.Resolve().Name == PARENT_ENTITY_NAME:
                is_already_parented = True
        except Exception:
            # 如果访问属性失败，则可能不是有效的泛化，或 API 访问受限
            pass

    if not is_already_parented:
        with TransactionManager(app, f'Set generalization for {CHILD_ENTITY_NAME}'):            
            # 创建 IGeneralization 对象来表示继承关系
            generalization = app.Create[IGeneralization]()
            # 将父实体解析器赋值给 Generalization 属性
            generalization.Generalization = parent_entity.QualifiedName 
            
            # 将 IGeneralization 对象赋值给子实体的 Generalization 属性
            child_entity.Generalization = generalization 
            
            PostMessage("backend:success", f"Set generalization for {CHILD_ENTITY_NAME} to {PARENT_ENTITY_NAME}")
    else:
        PostMessage("backend:info", f"{CHILD_ENTITY_NAME} already inherits from {PARENT_ENTITY_NAME}.")


    # 3. 添加关联 (Association) - 幂等性检查
    ASSOCIATION_NAME = 'Assoc_Parent_Child'
    
    # 检查关联是否已存在 (Parent 到 Child)
    existing_associations = parent_entity.GetAssociations(AssociationDirection.Parent, child_entity)
    
    if existing_associations.Count == 0:
        with TransactionManager(app, f'Add association {ASSOCIATION_NAME}'):
            association = parent_entity.AddAssociation(child_entity)
            association.Name = ASSOCIATION_NAME
            PostMessage("backend:success", f"Association '{ASSOCIATION_NAME}' added.")
    else:
        PostMessage("backend:info", f"Association '{ASSOCIATION_NAME}' already exists.")

# run_domain_model_demo(currentApp, project)


#endregion

#region boot
import traceback
try:
    # your logic here
    run_domain_model_demo(currentApp, project)
except IndexError as e:
    # Get the traceback as a string
    traceback_str = traceback.format_exc()
    PostMessage("backend:info",traceback_str)
#endregion
