## 架构知识库：Mendix 前后端 RPC 控制面板

### 1. 总体架构概述 (High-Level Architecture)

本系统是一个基于Mendix Studio Pro扩展API构建的Web应用，包含一个前端UI（`index.html`）和一个后端脚本（`main.py`）。

*   **核心模式**: 客户端-服务器 (Client-Server)
*   **通信协议**: 基于 `window.postMessage` 的**异步RPC（远程过程调用）**。
*   **核心设计原则**:
    1.  **关注点分离 (SoC)**: 前后端、UI、业务逻辑、通信等模块各自独立，职责单一。
    2.  **依赖倒置 (DIP)**: 组件依赖于稳定的抽象（接口/契约），而非不稳定的具体实现。
    3.  **控制反转 (IoC)**: 通过依赖注入（前端`redi`）和调度器（后端`AppController`）来管理和解耦组件。

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

---

### 3. 前端知识库 (Frontend Knowledge Base)

#### 关注点 1: RPC 通信 (RPC Communication)

*   **契约/接口 (DIP): `IMessageService`**
    *   **职责**: 定义一个标准的、与实现无关的后端通信接口。系统中任何需要与后端交互的组件都**必须**依赖此接口。
    *   **API**:
        *   `call(type: string, payload: object): Promise<any>`: 发起一个RPC调用，返回一个Promise，该Promise会用后端的`data`来解决，或在后端返回错误时被拒绝。

*   **实现: `BrowserMessageService`**
    *   **职责**: `IMessageService`接口的具体实现。它封装了所有`window.postMessage`的复杂性。
    *   **内部机制**:
        1.  生成唯一的`correlationId`。
        2.  维护一个`pendingRequests`的Map，用于存储`correlationId`和其对应的Promise `resolve`/`reject`函数。
        3.  监听`message`事件，当收到响应时，使用`correlationId`查找并处理对应的Promise。
        4.  管理请求超时。

#### 关注点 2: 视图组合与布局 (View Composition & Layout)

*   **契约/接口 (DIP): `IView`**
    *   **职责**: 这是一个“标记接口”或“标识符”。任何希望被主应用动态渲染为独立UI块的React组件，都应注册为`IView`的提供者。

*   **管理器: `ViewManagementService`**
    *   **职责**: 通过依赖注入收集所有注册为`IView`的组件。
    *   **协作**: `App`根组件依赖此服务来获取所有视图，并按注册顺序将它们渲染出来。这使得添加或移除UI模块无需修改`App`组件本身。

#### 关注点 3: 用户界面视图 (UI Views)

每个视图都是一个独立的React组件，具有单一职责。

*   **`InputView`**:
    *   **职责**: 提供一个输入框和一个按钮，用于发送`ECHO`命令。
    *   **依赖**: `IMessageService`。

*   **`EditorControlView`**:
    *   **职责**: 提供一个按钮，用于发送`OPEN_EDITOR`命令。
    *   **依赖**: `IMessageService`。

*   **`MessageLogView`**:
    *   **职责**: 显示所有RPC请求和响应的日志，用于调试和监控。
    *   **依赖**: `MessageStore`。

#### 关注点 4: 状态管理 (State Management)

*   **管理器: `MessageStore`**
    *   **职责**: 作为RPC日志的唯一真实来源。它存储所有请求、响应和错误的记录。
    *   **模式**: 发布/订阅（Observer）。`MessageLogView`订阅其变化以重新渲染。

#### 关注点 5: 依赖注入配置 (Dependency Injection Setup)

*   **配置器: `AppWithDependencies`**
    *   **职责**: 这是IoC容器的配置中心。它负责将抽象（如`IMessageService`）绑定到具体的实现（如`BrowserMessageService`），并注册所有的服务和视图。

---

### 4. 后端知识库 (Backend Knowledge Base)

#### 关注点 1: 请求入口与调度 (Request Entry & Dispatching)

*   **入口点: `onMessage(e)` 函数**
    *   **职责**: 作为Mendix环境消息的唯一入口。它的职责**仅限于**:
        1.  验证消息来源 (`e.Message == "frontend:message"`)。
        2.  反序列化消息数据。
        3.  将解析后的请求对象传递给`AppController`进行处理。
        4.  将`AppController`返回的响应序列化并发回前端。

*   **调度器: `AppController` 类**
    *   **职责**: 系统的核心路由器，实现了控制反转（IoC）。
    *   **内部机制**:
        1.  维护一个命令`type`到具体处理函数（handler）的映射。
        2.  `dispatch`方法根据请求的`type`字段，调用相应的handler。
        3.  它不包含任何具体的业务逻辑，只负责委托。
        4.  统一封装成功和失败的响应结构，并确保`correlationId`被回传。

#### 关注点 2: 业务逻辑 (Business Logic)

这是具体命令的实现，每个handler都是一个独立的逻辑单元。

*   **`handle_echo(payload)`**:
    *   **职责**: 实现`ECHO`命令的逻辑。

*   **`handle_open_editor(payload)`**:
    *   **职责**: 实现`OPEN_EDITOR`命令的逻辑。
    *   **外部依赖**: `currentApp` (用于访问Mendix模型) 和 `dockingWindowService` (用于执行打开编辑器的操作)。

#### 关注点 3: Mendix环境交互 (Mendix Environment Interaction)

*   **全局变量**: 后端脚本在一个特殊的Mendix环境中运行，并可以访问以下全局变量：
    *   `currentApp`: 代表当前Mendix项目的模型API入口。
    *   `dockingWindowService`: Mendix Studio Pro提供的服务，用于控制UI面板和编辑器。
    *   `PostMessage(type, data)`: 向前端发送消息的全局函数。
    *   **职责**: 这些是后端与宿主环境（Mendix Studio Pro）交互的唯一手段。任何与Mendix模型或UI相关的操作都必须通过它们进行。