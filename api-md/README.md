### Mendix Extensions API - A Structured Overview

The Mendix Extensions API provides a powerful way to interact with and extend the Mendix Studio Pro environment. It allows you to read and modify your app's model, add custom UI elements like menus and tool windows, and automate development tasks.

This API can be understood through four main pillars:

1.  **Extension Entry Points**: How your code integrates with the Studio Pro UI (e.g., menus, panes).
2.  **The Typed Model API**: A strongly-typed C# interface to read and write every part of your Mendix app model (domain models, microflows, pages, etc.).
3.  **Services**: A collection of helper services to perform common actions, from creating microflow activities to showing dialog boxes.
4.  **UI & Web View Integration**: The framework for building custom user interfaces for your extension using web technologies (HTML, CSS, JavaScript).

---

### 1. Extension Entry Points (How Your Extension Appears)

These are the abstract base classes you inherit from to create an extension. They define how your extension is loaded and presented within Studio Pro.

-   **`ExtensionBase`**: The root class for all extensions.
-   **`UIExtensionBase`**: The base for any extension that has a user interface component.
    -   **`MenuExtension`**: Adds a new item to the main **Extensions** menu in Studio Pro.
    -   **`ContextMenuExtension<T>`**: Adds a right-click context menu item for a specific model element (e.g., add a menu to `IEntity` or `IMicroflow`).
    -   **`DockablePaneExtension`**: Creates a new dockable tool window (pane) that can be placed on the left, right, or bottom of the screen.
    -   **`ConsistencyCheckExtension<T>`**: Creates custom validation rules that run during a consistency check (F4), showing errors or warnings for a specific model element type.
    -   **`WebServerExtension`**: Allows your extension to host a local web server, useful for integrations or serving resources.

---

### 2. The Typed Model API (Interacting with Your App)

This is the core of the API, allowing you to programmatically access and modify your Mendix application's structure. All model modifications **must** be wrapped in a transaction.

#### Key Concepts & Entry Points

-   **`IModel`**: The root object for an entire Mendix app. It's your starting point for almost everything.
    -   `IModel.Root`: Gets the `IProject` object.
    -   `IModel.StartTransaction(string description)`: **Crucial.** Starts a transaction for modifying the model. The returned `ITransaction` should be in a `using` block to ensure `Commit()` or `Rollback()` is called.
    -   `IModel.Create<T>()`: Creates a new instance of a model element (e.g., `IEntity`, `IAttribute`).
-   **Model Hierarchy**: The model is structured like your App Explorer:
    -   **`IProject`**: Represents the entire project. Contains a list of modules.
    -   **`IModule`**: Represents a single module. Contains folders and documents.
    -   **`IFolder`**: A folder within a module.
    -   **`IDocument`**: Represents a single document, such as a microflow, page, or enumeration.

#### Common Model Elements

-   **Domain Model (`Mendix.StudioPro.ExtensionsAPI.Model.DomainModels`)**
    -   **`IDomainModel`**: The container for all entities and associations in a module.
    -   **`IEntity`**: Represents an entity. You can get/add/remove its `IAttribute`s and `IAssociation`s.
    -   **`IAttribute`**: An attribute of an entity.
    -   **`IAssociation`**: An association between two entities.

-   **Microflows (`Mendix.StudioPro.ExtensionsAPI.Model.Microflows`)**
    -   **`IMicroflow`**: Represents a microflow document.
    -   **`IActivity`**: A generic activity within a microflow.
    -   **`IActionActivity`**: The most common type of activity, which contains an action.
    -   **`IMicroflowAction`**: The specific action to perform, such as `ICreateObjectAction`, `IChangeObjectAction`, `IMicroflowCallAction`, or `IRetrieveAction`.
    -   **`IMicroflowExpression`**: Represents a Mendix expression string.

-   **Data Types (`Mendix.StudioPro.ExtensionsAPI.Model.DataTypes`)**
    -   **`DataType`**: An abstract class used to represent all Mendix data types. Use its static properties (`DataType.String`, `DataType.Integer`) and methods (`DataType.Object(entityQualifiedName)`) to define types.

---

### 3. Services (The Toolbox)

Services are provided for dependency injection and simplify complex or common operations, acting as factories and helpers.

#### Model Creation & Modification Services

-   **`IMicroflowActivitiesService`**: A factory for creating pre-configured microflow activities. This is the **preferred way** to create new activities (e.g., `CreateCreateObjectActivity`, `CreateChangeListActivity`).
-   **`IMicroflowService`**: A helper for working with microflows as a whole. Can create a new microflow (`CreateMicroflow`) or insert activities into an existing one (`TryInsertAfterStart`).
-   **`IPageGenerationService`**: Generates standard overview pages for a set of entities.
-   **`IDomainModelService`**: Provides query methods for finding associations between entities.

#### Studio Pro UI Interaction Services

-   **`IDockingWindowService`**: Manages panes and document tabs. Use it to `OpenPane` or `TryOpenEditor` for a specific document.
-   **`IDialogService`**: Shows custom modal dialogs built with the Web View framework.
-   **`IMessageBoxService`**: Shows standard information, warning, error, or question dialogs.
-   **`ISelectorDialogService`**: Shows standard Mendix dialogs for selecting an element, like an entity or document.
-   **`IMicroflowExpressionEditorService`**: Opens the built-in Mendix expression editor to allow a user to write an expression.
-   **`IFindResultsPaneService`**: Shows the "Find Usages" results for a given element.
-   **`INotificationPopupService`**: Displays a temporary notification pop-up in the bottom-right corner of Studio Pro.

#### Utility Services

-   **`IHttpClientService`**: Creates `IHttpClient` instances for making HTTP requests.
-   **`ILogService`**: Logs messages to the Studio Pro console (`Debug`, `Info`, `Error`).
-   **`IBackgroundJobService`**: Runs long-running operations in the background without freezing the UI.
-   **`INameValidationService`**: Checks if a string is a valid name for a Mendix element (e.g., entity name, attribute name).
-   **`IAppService`**: Manages importing app/module packages (`.mpk` files).

---

### 4. UI & Web View Integration (Building Your Interface)

Most custom UI for extensions is built using web technologies. Your C# code creates a view model, which then hosts a web view pointing to your HTML file.

#### Core Components

-   **`IWebView`**: The central component that renders a web page. It acts as a bridge between your C# backend and JavaScript frontend.
    -   `Address`: The URL to load (typically a local HTML file).
    -   `PostMessage(string message, object data)`: Sends data from C# to your JavaScript code.
    -   `MessageReceived` (Event): Fires when your JavaScript code sends a message to C#.

#### ViewModel Hierarchy

You will create a view model class that inherits from one of these base classes, depending on where you want your UI to appear.

-   **`WebViewDockablePaneViewModel`**: The view model for a `DockablePaneExtension`.
-   **`WebViewTabViewModel`**: The view model for a UI that appears in a new document tab.
-   **`WebViewModalDialogViewModel`**: The view model for a pop-up modal dialog.

**Typical Workflow:**
1.  Create an extension inheriting from `DockablePaneExtension` (or another UI entry point).
2.  In its `Open()` method, return an instance of your custom view model (e.g., `MyDockablePaneViewModel`).
3.  Your view model class inherits from `WebViewDockablePaneViewModel`.
4.  In the constructor or `InitWebView` method of your view model, set the `IWebView.Address` to your `index.html` file.
5.  Use `PostMessage` and the `MessageReceived` event to communicate between your C# logic and the JavaScript running in the web view.