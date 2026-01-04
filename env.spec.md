以下是根据您提供的 **源代码**、**前端需求分析** 以及 **后端补充逻辑** 合并整理而成的完整项目文档。该文档涵盖了项目概述、功能需求、系统架构、前后端详细技术规格及交互流程。

---

# PythonIDE (Plugin Playground) 项目完整技术文档

**项目名称**: Mendix Python Extension / Plugin Playground
**文档生成时间**: 2026-01-04
**适用版本**: 基于提供的 RxJS 重构版前端与 C# MEF 架构后端

---

## 1. 项目概述 (Project Overview)

**PythonIDE** 是一个集成在 Mendix Studio Pro 中的扩展插件（Dockable Pane）。它提供了一个嵌入式的全栈开发环境（沙箱），允许开发者使用 **Python** 编写后端逻辑，使用 **HTML/JS** 编写前端界面，从而快速扩展 Mendix 的功能。

该项目旨在解决 Mendix 原生扩展开发周期长、调试困难的问题，提供即时编译（JIT）、实时预览和低代码交互能力。

---

## 2. 架构设计 (System Architecture)

系统采用 **三层隔离架构**，实现了逻辑计算、UI 交互与渲染展示的严格分离，确保了宿主环境的稳定性与安全性。

### 2.1 三层模型
1.  **Layer 1: 宿主层 (Host Layer - C# / Python)**
    *   **运行环境**: Mendix Studio Pro (.NET CLR) + CPython Engine。
    *   **职责**: 系统最高权限层。负责文件读写、Python 脚本执行、Mendix 模型 API 调用 (`IMicroflowService` 等) 以及 HTTP 请求。
    *   **核心组件**: `PluginHostClient`, `PythonEnvironment`, `ScopeManager`。

2.  **Layer 2: 交互层 (UI Layer - WebView2 / React)**
    *   **运行环境**: Embedded Edge/WebKit (React + RxJS)。
    *   **职责**: 开发者操作界面。提供代码编辑器 (Monaco)、控制台日志、状态管理及链路追踪。**该层不直接执行用户代码**。
    *   **核心组件**: `EditorStateService`, `ConsoleService`, `TelemetryService`。

3.  **Layer 3: 沙箱层 (Sandbox Layer - Iframe)**
    *   **运行环境**: 纯浏览器沙箱 (Iframe)。
    *   **职责**: 插件运行结果的展示层。渲染用户编写的 HTML/CSS/JS。
    *   **隔离性**: 使用 `sandbox` 属性防止 CSS 污染 IDE 界面或恶意 JS 导致主进程卡死。仅通过 `postMessage` 接收数据。

---

## 3. 功能需求 (Functional Requirements)

### 3.1 核心模式
*   **开发模式 (Development Mode)**:
    *   **双栏编辑**: 集成 Monaco Editor，支持 Python 和 HTML 语法高亮。
    *   **实时调试**: 提供 "Run Python" 按钮执行后端逻辑，"Update Preview" 刷新前端渲染。
    *   **多视图切换**: 支持 Python/HTML/Preview/Split 视图切换。
*   **执行模式 (Execution Mode)**:
    *   **插件运行**: 全屏运行已安装的插件，模拟最终用户体验。
    *   **插件管理**: 支持从 URL (`manifest.json`) 安装插件、切换激活插件、复制副本及设置默认插件。

### 3.2 调试与可观测性
*   **统一控制台**: 聚合显示前端日志、Python 标准输出/错误、Host 宿主日志。
*   **链路追踪 (Telemetry)**:
    *   前端实现 Zipkin 兼容的 Trace 收集。
    *   支持 RPC 请求（前端 -> 后端 -> 前端）的全链路自动关联 (Correlation)。
    *   支持导出到本地 Jaeger 服务 (默认端口 9411)。

### 3.3 Python 环境集成
*   **自动探测**: 能够通过环境变量、注册表、PATH 或 `py.exe` 自动找到系统 Python 环境。
*   **API 注入**: Python 脚本上下文中自动注入 Mendix 服务（如 `microflowService`, `messageBoxService`），允许脚本直接操作 Mendix 模型。

---

## 4. 技术规格：后端 (Backend Specifications)

### 4.1 技术栈
*   **Language**: C# (.NET Framework / .NET Core).
*   **Python Interop**: `Python.Runtime` (pythonnet).
*   **DI Framework**: MEF (Managed Extensibility Framework).
*   **JSON Handling**: `System.Text.Json`.

### 4.2 核心服务实现

#### 4.2.1 引导与消息路由 (`Boot.cs` & `MessageBus`)
*   **入口**: `Boot.cs` 初始化 WebView 并加载 `index.html`。
*   **路由策略**: 使用策略模式，通过 MEF 导入所有实现 `IWebViewMessageHandler` 的类。
*   **分发逻辑**: `WebView_MessageReceived` 根据消息字符串（如 `python:exe`）自动调用对应的 Handler，无需修改核心代码即可扩展新指令。

#### 4.2.2 Python 环境管理 (`PythonEnvironmentService.cs` & `PythonFinder.cs`)
*   **环境发现**: 实现启发式搜索策略：
    1.  `PYTHONNET_PYDLL` 环境变量（人工覆盖）。
    2.  `py.exe` 启动器输出解析。
    3.  Windows 注册表扫描。
    4.  系统 PATH 路径扫描。
*   **线程安全**: 严格管理 GIL (Global Interpreter Lock)，使用 `using (Py.GIL())` 块包裹所有 Python 调用。

#### 4.2.3 作用域与注入 (`ScopeManager.cs`)
*   **持久化作用域**: 维护 `_persistentScope`，保证插件运行期间变量不丢失。
*   **API 注入**: 将 C# 的 Mendix 服务实例转换为 Python 对象注入全局命名空间。
    *   *Ex*: `scope.Set("show_message", new Action<string>(...))`。

#### 4.2.4 异步执行与取消 (`PythonScriptingServiceRefactored.cs`)
*   **后台执行**: 所有脚本执行通过 `Task.Run` 放入线程池，避免阻塞 UI 线程。
*   **取消机制**:
    *   使用 `CancellationTokenSource` 管理任务生命周期。
    *   将 Token 注入 Python 作用域 (`scope.Set("cancellation_token", token)`)，允许脚本内部感知取消请求。

---

## 5. 技术规格：前端 (Frontend Specifications)

### 5.1 技术栈
*   **Framework**: React 18 (Browser ESM, 无需编译构建)。
*   **State Management**: RxJS (Observables, Subjects) + Redi (DI)。
*   **Styles**: TailwindCSS + FontAwesome。
*   **Editor**: Monaco Editor (AMD Loader)。

### 5.2 核心架构设计

#### 5.2.1 依赖注入 (DI)
使用 **Redi** 容器管理服务依赖，实现松耦合：
*   **Layer 0 (Infra)**: `ITelemetryService`, `ILogger`, `IPluginHostClient`。
*   **Layer 1 (Domain)**: `IAppLifecycleService`, `IPluginManagementService`, `IEditorStateService`。
*   **Layer 2 (View)**: `MainViewResolver`。

#### 5.2.2 响应式通信 (RxJS Bridge)
*   **`PluginHostClient`**:
    *   维护 `messages$` 流，广播所有入站消息。
    *   实现 RPC 追踪：`send()` 方法自动生成 `traceId` 并启动 Span；收到响应时根据 `traceId` 闭环 Span 并计算耗时。
*   **数据流向**:
    *   `client.onPluginLoad$` -> `EditorStateService` (更新代码) -> `Telemetry` (记录耗时)。

#### 5.2.3 沙箱隔离 (`ExecutionModeUI`)
*   **Iframe 重置**: 利用 React 的 Key 机制 (`key={iframeVersion}`)。当代码更新或插件切换时，`iframeVersion` 自增，强制 React 销毁并重建 Iframe DOM 节点，确保运行环境（Window 对象）彻底重置，无变量污染。
*   **消息转发**: `FrontendBridgeService` 监听 `backend:response`，并通过 `postMessage` 转发进 Iframe。

#### 5.2.4 可观测性 (`TelemetryService`)
*   **实现**: 手动实现的简易 OpenTelemetry 客户端。
*   **特性**: 支持 Context Propagation (父子 Span)、批量异步上报 (BufferTime)、以及控制台可视化。

---

## 6. 接口协议 (Interface Specifications)

### 6.1 前端 -> 后端 (Commands)

| Message Key | Payload | Description | Handler Class |
| :--- | :--- | :--- | :--- |
| `app:ready` | `{}` | 前端加载完成，请求初始化配置 | `AppReadyMessageHandler` |
| `python:exe` | `{ code: string }` | 请求执行 Python 代码 | `PythonExeMessageHandler` |
| `plugin:save` | `{ pluginName, pythonCode, htmlCode }` | 保存当前插件代码到磁盘 | `PluginSaveMessageHandler` |
| `plugin:run` | `{ pluginName }` | 请求加载并运行指定插件 | `PluginRunMessageHandler` |
| `plugin:install`| `{ url }` | 从远程 URL 安装插件 | `PluginInstallMessageHandler` |
| `config:save` | `{ ...config }` | 保存用户偏好设置 | `ConfigSaveMessageHandler` |
| `frontend:message`| `{ ... }` | 通用消息，转发给 Python 的 `onMessage` | `PythonEnvironmentMessageHandler` |

### 6.2 后端 -> 前端 (Events)

| Message Key | Payload | Description |
| :--- | :--- | :--- |
| `app:initialize` | `{ config, plugins }` | 初始化数据（配置和插件列表） |
| `plugin:load` | `{ pythonCode, htmlCode }` | 返回插件的具体代码内容 |
| `plugins:update` | `[PluginManifest]` | 插件列表更新通知 |
| `backend:response`| `{ traceId, data, ... }` | Python 脚本执行结果或回调数据 |
| `Log*` | `string` | 系统日志 (`log:info`, `log:error`) |

---

## 7. 典型交互流程示例 (Sequence Diagram Description)

**场景：用户在开发模式点击 "Run Python"**

1.  **UI Layer (React)**:
    *   用户点击按钮。
    *   `TelemetryService` 开启 Span `UI:Click:RunPython`。
    *   `PluginHostClient` 发送消息 `python:exe`，携带代码和 `traceId`。
2.  **Host Layer (C#)**:
    *   `WebView` 接收消息，`PythonExeMessageHandler` 被激活。
    *   `PythonScriptingService` 创建新的 `CancellationTokenSource`。
    *   `Task.Run` 启动后台线程。
    *   **Python Engine**:
        *   获取 GIL。
        *   注入 `cancellation_token` 和 Mendix Services。
        *   执行代码 (`scope.Exec(code)`).
    *   代码执行完毕，通过 `MessageBus` 发布 `PythonExecutionCompletedMessage`。
3.  **Host Layer (C#)**:
    *   监听 `PythonExecutionCompletedMessage`。
    *   `WebViewService` 发送 `log:info` ("Python execution completed") 回前端。
4.  **UI Layer (React)**:
    *   `ConsoleService` 收到 `log:info`。
    *   控制台显示执行成功日志。
    *   `TelemetryService` 收到对应的 Trace 响应（若有），结束 Span 并记录耗时。