Of course, here is the updated `README.md` file reflecting the changes in the provided code, including the new MCP server controls.

---

## 架构知识库：Mendix 前后端 RPC 控制面板

### 1. 总体架构概述 (High-Level Architecture)

本系统是一个基于Mendix Studio Pro扩展API构建的Web应用，包含一个前端UI（`index.html`）和一个后端脚本（`main.py`）。它现在集成了Mendix Copilot (MCP) 服务，允许用户通过UI直接控制后端的MCP服务器生命周期。

*   **核心模式**: 客户端-服务器 (Client-Server)
*   **通信协议**: 基于 `window.postMessage` 的**异步RPC（远程过程调用）**。
*   **核心设计原则**:
    1.  **关注点分离 (SoC)**: 前后端、UI、业务逻辑、通信等模块各自独立，职责单一。
    2.  **依赖倒置 (DIP)**: 组件依赖于稳定的抽象（接口/契约），而非不稳定的具体实现。
    3.  **控制反转 (IoC)**: 通过依赖注入（前端`redi`，后端`dependency-injector`）和调度器（后端`AppController`）来管理和解耦组件。

---

### 2. 集成契约：RPC 通信协议 (The Contract)

这是前后端之间必须遵守的“法律”，是整个系统中最稳定的部分。

#### 2.1 请求 (Request)

从前端发送到后端的每个消息都必须是一个包含以下字段的JSON对象：

| 字段名          | 类型   | 描述                                     | 示例                      |
| --------------- | ------ | ---------------------------------------- | ------------------------- |
| `type`          | string | **必须**。命令的类型，用于后端路由。     | `"OPEN_EDITOR"`           |
| `payload`       | object | **必须**。与命令相关的数据。             | `{"moduleName": "Admin"}` |
| `correlationId` | string | **必须**。请求的唯一ID，用于匹配响应。   | `"req-123"`               |
| `timestamp`     | string | 可选。ISO 8601格式的客户端时间戳。       | `"2023-10-27T10:00:00Z"`  |

#### 2.2 响应 (Response)

从后端返回到前端的每个消息都必须是一个包含以下字段的JSON对象：

| 字段名          | 类型         | 描述                                     | 示例                      |
| --------------- | ------------ | ---------------------------------------- | ------------------------- |
| `status`        | `"success"`/`"error"` | **必须**。表示操作是否成功。             | `"success"`               |
| `data`          | any          | 可选。`status`为`success`时返回的数据。    | `{"opened": true}`        |
| `message`       | string       | 可选。`status`为`error`时的错误信息。      | `"Module not found."`     |
| `correlationId` | string       | **必须**。必须与触发此响应的请求ID完全相同。 | `"req-123"`               |

#### 2.3 已定义的命令 (Defined Commands)

| `type`          | `payload` 结构                                | 成功时 `data` 结构                     | 描述                                         |
| --------------- | ----------------------------------------------- | ---------------------------------------- | -------------------------------------------- |
| `ECHO`          | `{ "content": any }`                            | `{ "echo_response": { "content": any } }` | 后端将收到的 `payload` 原样返回，用于测试连通性。 |
| `OPEN_EDITOR`   | `{ "moduleName": string, "entityName": string}` | `{ "opened": boolean, ... }`             | 请求后端在Mendix Studio Pro中打开指定实体的编辑器。 |
| `MCP_CONTROL`   | `{ "action": "start" \| "stop" \| "get_status" \| "list_tools" }` | 依赖于 `action` (见下文)                  | 管理后端的MCP服务器生命周期。 |

**`MCP_CONTROL` 命令的 `data` 结构:**

*   当 `action` 是 `start`, `stop`, 或 `get_status` 时, `data` 返回服务器状态: `{ "status": "running" | "stopped", "port": number }`。
*   当 `action` 是 `list_tools` 时, `data` 返回可用工具列表: `{ "tools": [{ "name": string, "description": string }] }`。

---

### 3. 前端知识库 (Frontend Knowledge Base)

#### 关注点 1: RPC 通信 (RPC Communication)

*   **契约/接口 (DIP): `IMessageService`**
    *   **职责**: 定义一个标准的、与实现无关的后端通信接口。系统中任何需要与后端交互的组件都**必须**依赖此接口。
    *   **API**:
        *   `call(type: string, payload: object): Promise<any>`: 发起一个RPC调用，返回一个Promise，该Promise会用后端的`data`来解决，或在后端返回错误时被拒绝。

*   **实现: `BrowserMessageService`**
    *   **职责**: `IMessageService`接口的具体实现。它封装了所有`window.postMessage`的复杂性。
    *   **内部机制**: 管理唯一的`correlationId`、`pendingRequests`映射、响应监听和请求超时。

*   **辅助工具: `useRpc` Hook**
    *   **职责**: 一个可复用的React Hook，封装了调用 `IMessageService` 的异步流程。它负责管理`isLoading`, `error`, 和 `data`状态，简化了UI组件中的异步代码。

#### 关注点 2: 视图组合与布局 (View Composition & Layout)

*   **契约/接口 (DIP): `IView`**
    *   **职责**: 这是一个“标记接口”。任何希望被主应用动态渲染为独立UI块的React组件，都应注册为`IView`的提供者。

*   **管理器: `ViewManagementService`**
    *   **职责**: 通过依赖注入收集所有注册为`IView`的组件。`App`根组件依赖此服务来获取并渲染所有视图。

#### 关注点 3: 用户界面视图 (UI Views)

每个视图都是一个独立的React组件，具有单一职责。

*   **`McpControlView` (新增)**:
    *   **职责**: 提供一个完整的UI来管理后端MCP服务器。它允许用户启动、停止、刷新服务器状态，并在服务器运行时显示可用工具列表。
    *   **依赖**: `IMessageService` (通过 `useRpc` hook)。

#### 关注点 4: 依赖注入配置 (Dependency Injection Setup)

*   **配置器: `AppWithDependencies`**
    *   **职责**: 这是IoC容器的配置中心。它负责将抽象（如`IMessageService`）绑定到具体的实现（如`BrowserMessageService`），并注册所有的服务和视图（包括新的`McpControlView`）。

---

### 4. 后端知识库 (Backend Knowledge Base)

#### 关注点 1: 请求入口与调度 (Request Entry & Dispatching)

*   **入口点: `onMessage(e)` 函数**
    *   **职责**: 作为Mendix环境消息的唯一入口，负责反序列化消息、将其传递给`AppController`处理，并将返回的响应序列化并发回前端。

*   **调度器: `AppController` 类**
    *   **职责**: 系统的核心路由器。它维护一个命令`type`到具体**命令处理器(Command Handler)**的映射。`dispatch`方法根据请求的`type`字段，调用相应的处理器，实现了控制反转。

#### 关注点 2: 命令处理器与业务逻辑 (Command Handlers & Business Logic)

业务逻辑被封装在实现了`ICommandHandler`接口的类中，每个类负责处理一种命令类型。

*   **接口 (DIP): `ICommandHandler`**
    *   **职责**: 定义所有命令处理器的契约，要求实现`command_type`属性和`execute(payload)`方法。

*   **实现: `EchoCommandHandler` & `EditorCommandHandler`**
    *   **职责**: 分别实现`ECHO`和`OPEN_EDITOR`命令的逻辑。

*   **实现: `MCPCommandHandler` (新增)**
    *   **职责**: 处理`MCP_CONTROL`命令。它本身不包含复杂的逻辑，而是作为一个外观（Facade），将`start`, `stop`, `get_status`等具体操作委托给`MCPService`。

#### 关注点 3: 核心服务 (Core Services)

*   **`MendixEnvironmentService`**
    *   **职责**: 封装与Mendix Studio Pro宿主环境的交互，如访问项目模型(`currentApp`)、打开编辑器(`dockingWindowService`)和发送消息(`PostMessage`)。
    * **其它**
        * extensionFileService
        * logService
        * microflowActivitiesService
        * microflowExpressionService
        * microflowService
        * untypedModelAccessService
        * dockingWindowService
        * domainModelService
        * backgroundJobService
        * configurationService
        * extensionFeaturesService
        * httpClientService
        * nameValidationService
        * navigationManagerService
        * pageGenerationService
        * appService https://github.com/mendix/ExtensionAPI-Samples/      * blob/main/API%20Reference/Mendix.StudioPro.ExtensionsAPI.   * UI.Services/IAppService.md
        * dialogService
        * entityService
        * findResultsPaneService
        * localRunConfigurationsService
        * notificationPopupService
        * runtimeService
        * selectorDialogService
        * versionControlService
        * messageBoxService

*   **`MCPService` (新增)**
    *   **职责**: 管理`FastMCP`服务器的完整生命周期。
    *   **内部机制**:
        1.  **后台执行**: 在一个独立的`threading.Thread`中启动和运行`uvicorn`服务器，避免阻塞Mendix主线程。
        2.  **生命周期管理**: 提供`start()`和`stop()`方法来控制服务器。
        3.  **状态查询**: `is_running()`, `get_status()`, `get_tools()`等方法允许其他部分查询服务器状态和配置。
        4.  **热重载**: 在启动时使用`importlib.reload`来重新加载工具模块，确保每次启动都能获取最新的工具定义。
        5.  **自动关闭**: 启动一个监控线程，在Mendix脚本被取消或重新运行时（通过`cancellation_token`）自动关闭服务器，防止僵尸进程。

#### 关注点 4: 依赖注入配置 (Dependency Injection Setup)

*   **IoC容器: `Container` (基于 `dependency-injector`)**
    *   **职责**: 负责实例化和装配系统中的所有组件。
    *   **配置**:
        1.  所有服务（如`MendixEnvironmentService`, `MCPService`）都被注册为`Singleton`。
        2.  所有`ICommandHandler`的实现（`EchoCommandHandler`, `EditorCommandHandler`, `MCPCommandHandler`）被聚合到一个`providers.List`中。
        3.  `AppController`被注入这个处理器列表，使其能够动态发现所有可用的命令，而无需硬编码依赖。
