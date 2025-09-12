import json
import clr

# 确保已引用 Mendix.StudioPro.ExtensionsAPI
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# 导入必要的模型元素接口
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IProject, IModule, IFolder
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import AssociationDirection,IDomainModel, IEntity, IAttribute, IAttributeType, IStoredValue, IAssociation,IIntegerAttributeType
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow
from Mendix.StudioPro.ExtensionsAPI.Model.Pages import IPage

PostMessage("backend:clear", '')

#region define
class TransactionManager:
    """with TransactionManager(current_app, f"your transaction name"):"""

    def __init__(self, app, transaction_name):
        self.app = app
        self.name = transaction_name
        self.transaction = None

    def __enter__(self):
        self.transaction = self.app.StartTransaction(self.name)
        return self.transaction

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.transaction.Commit()
        else:
            self.transaction.Rollback()
        self.transaction.Dispose()
        return False  # 允许异常继续传播
#endregion

#获取实体HelloModule.P 和HelloModule.C
ms=currentApp.Root.GetModules()
m = next((m for m in ms if m.Name == 'Administration'), None)

entity = next((e for e in m.DomainModel.GetEntities() if e.Name=='Account'), None)

#添加关联由P指向C
with TransactionManager(currentApp, f'transaction name'):
    other_entity = None
    entity_associations = entity.GetAssociations(AssociationDirection.Parent, other_entity)
    PostMessage("backend:info", f"{entity_associations.Count}")

ret = dockingWindowService.TryOpenEditor(m.DomainModel, entity)
PostMessage("backend:info", f"{ret}")