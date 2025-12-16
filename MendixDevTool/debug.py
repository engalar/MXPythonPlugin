# 这是一个最小化的验证脚本，完全脱离服务器和复杂架构，仅用于调试 Mendix API 的查找逻辑。

import clr
import traceback

# 引入 Mendix 扩展 API
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
from System.Collections import IEnumerable
_dir = dir


def dir(e):
    PostMessage("backend:info", f'{_dir(e)}')


def error(e):
    PostMessage("backend:error", f'{e}')

def print(e):
    PostMessage("backend:info", e)
# ==========================================
# 硬编码调试脚本: Evora_UI.Login.container11
# ==========================================

PostMessage("backend:clear", "")
PostMessage("backend:info", "=== 开始硬编码调试 (兼容版) ===")

try:
    # 目标定义
    TARGET_MODULE = "Evora_UI"
    TARGET_DOC = "Login"
    TARGET_WIDGET = "container11"

    PostMessage("backend:info", "目标: " + TARGET_MODULE + "." + TARGET_DOC + "." + TARGET_WIDGET)

    # -------------------------------------------------
    # 步骤 1: 查找 Module
    # -------------------------------------------------
    PostMessage("backend:info", "步骤 1: 查找 Module...")
    found_module = None
    for m in currentApp.Root.GetModules():
        if m.Name == TARGET_MODULE:
            found_module = m
            break
            
    if not found_module:
        raise Exception("找不到模块: " + TARGET_MODULE)
    
    PostMessage("backend:info", "✅ 成功找到模块: " + found_module.Name)

    # -------------------------------------------------
    # 步骤 2: 查找 Document (Page)
    # -------------------------------------------------
    PostMessage("backend:info", "步骤 2: 查找 Document...")
    
    def find_document_recursive(folder, doc_name):
        for d in folder.GetDocuments():
            if d.Name == doc_name: return d
        for sub in folder.GetFolders():
            res = find_document_recursive(sub, doc_name)
            if res: return res
        return None

    found_doc = find_document_recursive(found_module, TARGET_DOC)
    
    if not found_doc:
        raise Exception("找不到文档: " + TARGET_DOC)
        
    PostMessage("backend:info", "✅ 成功找到文档: " + found_doc.Name)

    # -------------------------------------------------
    # 步骤 3: 查找 Widget (使用字典上下文避免 nonlocal 问题)
    # -------------------------------------------------
    PostMessage("backend:info", "步骤 3: 深度查找 Widget...")
    
    # 上下文容器
    ctx = {
        "found_widget": None,
        "visited_count": 0
    }

    def find_widget_recursive(node, target_name, depth):
        # 如果已经找到，直接返回
        if ctx["found_widget"]: return 

        ctx["visited_count"] += 1
        
        # 获取名称
        current_name = getattr(node, "Name", "")
        # node_type = str(node.GetType().Name) if hasattr(node, "GetType") else "Unknown"

        PostMessage("backend:info", "   [" + str(depth) + "] 扫描: " + current_name)

        if current_name == target_name:
            ctx["found_widget"] = node
            return

        # 遍历属性
        if hasattr(node, "GetProperties"):
            for prop in node.GetProperties():
                val = prop.Value
                if not val: continue

                # 列表类型
                if isinstance(val, IEnumerable) and not isinstance(val, str):
                    for item in val:
                        if hasattr(item, "GetProperties"):
                            find_widget_recursive(item, target_name, depth + 1)
                            if ctx["found_widget"]: return
                
                # 单对象类型
                elif hasattr(val, "GetProperties"):
                    find_widget_recursive(val, target_name, depth + 1)
                    if ctx["found_widget"]: return

    # 开始查找
    find_widget_recursive(found_doc, TARGET_WIDGET, 0)
    
    found_widget = ctx["found_widget"]

    if found_widget:
        PostMessage("backend:info", "✅ 成功找到组件: " + found_widget.Name)
    else:
        PostMessage("backend:info", "⚠️ 未找到组件 '" + TARGET_WIDGET + "' (扫描了 " + str(ctx["visited_count"]) + " 个节点)")

    # -------------------------------------------------
    # 步骤 4: 执行打开
    # -------------------------------------------------
    PostMessage("backend:info", "步骤 4: 调用 Studio Pro 编辑器...")

    if found_widget:
        PostMessage("backend:info", "执行模式: 打开文档并选中组件")
        dockingWindowService.TryOpenEditor(found_doc, found_widget)
    else:
        PostMessage("backend:info", "执行模式: 仅打开文档 (Fallback)")
        dockingWindowService.TryOpenEditor(found_doc)

    PostMessage("backend:info", "🎉 API 调用完成")

except Exception as e:
    PostMessage("backend:info", "❌ 严重错误: " + str(e))
    PostMessage("backend:info", traceback.format_exc())