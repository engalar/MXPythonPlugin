基于提供的 `main.py` 代码，我们可以反向推导出 **Mendix Untyped Model (Mendix 模型 SDK/API)** 的内部数据结构。

这段代码充当了一个“适配器”，将 .NET 环境下的 Mendix 对象图（Object Graph）转换为前端可理解的 JSON 格式。以下是其核心数据结构的归纳：

### 1. 核心对象层级 (Hierarchy)

Mendix 的模型数据结构呈现为一个**树状结构（Tree Structure）**，主要由三种层级构成：

1.  **Project (Root)**: 项目根节点，是所有数据的入口。
2.  **Unit (单元/文件)**: 独立存储的模型文件，拥有唯一的持久化 `ID`。
    *   例如：`Projects$Module` (模块), `Pages$Page` (页面), `DomainModels$DomainModel` (领域模型)。
    *   特征：代码中通过 `root.GetUnitsOfType()` 或 `parent.GetUnits()` 获取。
3.  **Element (元素)**: 隶属于 Unit 内部的细粒度组件，通常没有全局唯一的持久化 ID（或者 ID 是临时的）。
    *   例如：`DomainModels$Entity` (实体), `Pages$ListView` (列表视图), `Microflows$Action` (微流动作)。
    *   特征：代码中通过 `element.GetElements()` 获取。

### 2. 通用对象接口 (Object Interface)

无论是 Unit 还是 Element，在 Untyped API 中似乎都遵循一个通用的接口模式。根据 `get_details` 函数，任何节点对象主要包含以下成员：

| 属性/方法 | 描述 | 代码佐证 |
| :--- | :--- | :--- |
| **Type** | 字符串，格式通常为 `ModuleName$TypeName` (如 `Projects$Module`)。 | `str(element.Type)` |
| **Name** | (可选) 对象的名称。 | `getattr(element, "Name", ...)` |
| **ID** | (仅 Unit) 全局唯一标识符 (GUID)。 | `hasattr(element, "ID")` |
| **Container** | 指向父节点的引用，用于向上遍历路径。 | `curr.Container` (用于计算 `path`) |
| **GetUnits()** | 获取子级 Unit（通常用于 Folder 或 Module）。 | `target.GetUnits()` |
| **GetElements()** | 获取子级 Element（通常用于实体、页面组件等）。 | `target.GetElements()` |
| **GetProperties()** | 获取该对象的属性列表。 | `target.GetProperties()` |

### 3. 属性系统 (Property System)

通过 `GetProperties()` 获取的每个属性对象 (`p`) 具有以下结构：

*   **p.Name**: 属性名。
*   **p.Type**: 属性的数据类型。
*   **p.Value**: 属性的值，根据类型不同，结构差异很大：
    *   **Primitive**: 基础类型（字符串、布尔值、数字），直接返回值。
    *   **Reference (Ref)**: 引用另一个 Mendix 对象（如 Entity 引用 Module），此时 Value 是一个对象。
    *   **List**: 列表类型。
*   **p.IsList**: 布尔值，指示该属性是否包含列表。如果是列表，其 `Value` 是可迭代对象 (`Count`, `__iter__`)。

### 4. 数据遍历逻辑 (Traversal Logic)

代码揭示了两种不同的遍历模式：

**A. 树状导航 (Tree View - `get_children`)**
*   这部分主要用于宏观导航。
*   它**只**钻取 `GetUnits()`。这意味着在左侧树形菜单中，只能看到 文件夹 -> 模块 -> 页面/微流文件，而看不到页面里面的按钮。

**B. 详情钻取 (Detail View - `get_details`)**
*   这部分用于展示某个节点的内部结构。
*   **混合遍历**: 它优先尝试 `GetUnits()`，如果没有则尝试 `GetElements()`。
*   **分组**: 代码逻辑 `response["elements"]` 将子元素按 `Type` 进行了分组（例如将所有 `Attribute` 分为一组，`Association` 分为一组）。

### 5. 总结：数据结构图示

```text
Project (Root)
 ├── Unit (e.g., Projects$Module) [Has ID]
 │    ├── Property: Name = "MyModule"
 │    ├── Unit (e.g., DomainModels$DomainModel) [Has ID]
 │    │    ├── Element (e.g., DomainModels$Entity) [No Persistent ID in logic]
 │    │    │    ├── Property: Name = "Customer"
 │    │    │    ├── Element (e.g., DomainModels$Attribute)
 │    │    │    │    └── Property: Type = String
 │    │    │    └── Element (e.g., DomainModels$ValidationRule)
 │    │    └── Element (e.g., DomainModels$Association)
 │    └── Unit (e.g., Pages$Page)
 │         └── ...
 └── Unit (e.g., Projects$Folder)
      └── ...
```

### 关键发现 (基于 Python 代码的特殊处理)

1.  **ID 缓存机制**: 由于 Element 可能没有方便传输的 ID，代码实现了一个 `_element_cache`。
    *   如果是 Unit，使用真实的 `ID`。
    *   如果是 Element，使用 Python 内存地址 `id(element)` 生成临时 `tmp_` ID。
2.  **双向链表**: 能够通过 `.Container` 属性从任意子节点反推回 Root，这被用于生成面包屑路径 (`path` 字段)。
3.  **列表作为属性**: 在 Mendix 模型中，子项列表（如实体的一组属性）既可以通过 `GetElements()` 访问，有时也通过 `GetProperties()` 中的列表属性访问（如 `p.IsList`）。代码在 `get_details` 中分别处理了这两种情况。