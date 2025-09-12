# https://gist.github.com/engalar/b84b71693c4d1a8addd458e4eec53da3
# gh gist edit b84b71693c4d1a8addd458e4eec53da3 .\main.py -f main.py
# pip install pythonnet dependency-injector
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import AssociationDirection, IDomainModel, IEntity, IAttribute, IAttributeType, IStoredValue, IAssociation, IIntegerAttributeType
from Mendix.StudioPro.ExtensionsAPI.Model.Pages import IPage
from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow
from Mendix.StudioPro.ExtensionsAPI.Model.Projects import IProject, IModule, IFolder
import clr
import json
from typing import Any, Dict, List, Protocol

clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# pythonnet库嵌入C#代码

# 运行时环境提供的工具
PostMessage("backend:clear", '')  # 清理IDE控制台日志
ShowDevTools()  # 打开前端开发者工具
# 运行时环境提供的上下文变量
# currentApp：mendix model
# root：untyped model
# dockingWindowService

# region define
# fix c# json与python json转换问题
def serialize_json_object(json_object: Any) -> str:
    # 将.NET对象序列化为JSON字符串
    import System.Text.Json
    return System.Text.Json.JsonSerializer.Serialize(json_object)
def deserialize_json_string(json_string: str) -> Any:
    # 将JSON字符串反序列化为Python对象
    return json.loads(json_string)
# mendix model事务工具
class TransactionManager:
    """with TransactionManager(currentApp, f"your transaction name"):"""

    def __init__(self, app, transaction_name):
        self.app = app  # currentApp
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
# endregion


# 获取所有模块
ms = currentApp.Root.GetModules()
# 获取名为Administration的模块
m = next((m for m in ms if m.Name == 'Administration'), None)

# 获取名为Administration.Account的实体
entity = next((e for e in m.DomainModel.GetEntities()
              if e.Name == 'Account'), None)

# 编辑器打开模块Administration的DomainModel单元并选中Account实体
ret = dockingWindowService.TryOpenEditor(m.DomainModel, entity)
PostMessage("backend:info", f"{ret}")

# 接收来自C#的消息
def onMessage(e: Any):
    if e.Message == "frontend:message":# 接收来自C#转发的前端消息，前端用window.parent.sendMessage("frontend:message", jsonMessageObj)发送消息
        try:
            message_data = deserialize_json_string(serialize_json_object(e))
            request_object = message_data.get("Data")
            if request_object:
                # 处理逻辑
                response = request_object#简单的echo消息来模拟处理逻辑
                # 发关消息给前端，前端可以用如下代码来接收
                #window.addEventListener('message', (event) => {
                #    if (event.data && event.data.type === 'backendResponse') {
                #        const payload = event.data.data;// payload就是echo的response
                #        // your logic here
                #    }
                #})
                PostMessage("backend:response", json.dumps(response))
        except Exception as ex:
            PostMessage(
                "backend:info", f"Fatal error in onMessage: {ex}\n{traceback.format_exc()}")