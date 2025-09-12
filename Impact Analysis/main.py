from Mendix.StudioPro.ExtensionsAPI.Model.Microflows import IMicroflow, IMicroflowCall, IShowPageAction
from System import Object
from Mendix.StudioPro.ExtensionsAPI.Model.Pages import IPage
from Mendix.StudioPro.ExtensionsAPI.Model.DomainModels import IAttribute, IEntity
from Mendix.StudioPro.ExtensionsAPI.Model import IStructure
import clr
import json
from abc import ABC, abstractmethod
from typing import List, Type, Optional

# ================================================================================
# PART 0: Mendix API Reference & Imports (Corrected as per Documentation)
# ================================================================================

# 文档参考 https://github.com/mendix/ExtensionAPI-Samples/tree/main/API%20Reference
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")

# IStructure: https://github.com/mendix/ExtensionAPI-Samples/tree/main/API%20Reference/Mendix.StudioPro.ExtensionsAPI.Model/IStructure.md
# IAttribute: https://github.com/mendix/ExtensionAPI-Samples/tree/main/API%20Reference/Mendix.StudioPro.ExtensionsAPI.Model.DomainModels/IAttribute.md
# IEntity: https://github.com/mendix/ExtensionAPI-Samples/tree/main/API%20Reference/Mendix.StudioPro.ExtensionsAPI.Model.DomainModels/IEntity.md
# IMicroflow: https://github.com/mendix/ExtensionAPI-Samples/tree/main/API%20Reference/Mendix.StudioPro.ExtensionsAPI.Model.Microflows/IMicroflow.md
# IMicroflowCall: https://github.com/mendix/ExtensionAPI-Samples/tree/main/API%20Reference/Mendix.StudioPro.ExtensionsAPI.Model.Microflows/IMicroflowCall.md
# IShowPageAction: https://github.com/mendix/ExtensionAPI-Samples/tree/main/API%20Reference/Mendix.StudioPro.ExtensionsAPI.Model.Microflows/IShowPageAction.md
# IPage: https://github.com/mendix/ExtensionAPI-Samples/tree/main/API%20Reference/Mendix.StudioPro.ExtensionsAPI.Model.Pages/IPage.md



# ================================================================================
# PART 1: CORE FRAMEWORK (System Code)
# Defines all abstractions and high-level services.
# This part is generic and should not be modified.
# ================================================================================


class IElementAnalyzer(ABC):
    """
    ABSTRACT STRATEGY: Defines the contract for an analysis "plugin".
    """

    def __init__(self, element: IStructure, app: Object):
        self.element = element
        self.app = app
        self.nodes: List[dict] = []
        self.edges: List[dict] = []
        self.processed_ids: set = set()

    @classmethod
    @abstractmethod
    def can_handle(cls, element: IStructure) -> bool:
        """Determines if this analyzer is suitable for the given element."""
        raise NotImplementedError

    @abstractmethod
    def analyze(self) -> tuple[List[dict], List[dict]]:
        """Performs the analysis and returns nodes and edges."""
        raise NotImplementedError

    # --- Reusable helper methods ---
    def _add_node(self, element: IStructure, group: str = 'default', is_center: bool = False):
        element_id = str(element.Id)
        if element_id in self.processed_ids:
            return

        label = element.Name
        if hasattr(element, 'Module') and element.Module:
            label = f"{element.Module.Name}.{element.Name}"

        self.nodes.append({
            'id': element_id, 'label': label, 'group': 'center' if is_center else group,
            'title': f"Type: {type(element).__name__}<br>ID: {element.Id}"
        })
        self.processed_ids.add(element_id)

    def _add_edge(self, source_elem: IStructure, target_elem: IStructure, label: str = ""):
        self.edges.append({
            'from': str(source_elem.Id), 'to': str(target_elem.Id), 'label': label
        })


class ISelectionProvider(ABC):
    """
    ABSTRACT PROVIDER: Defines the contract for how to get the element to be analyzed.
    This decouples the analysis service from the Studio Pro UI.
    """
    @abstractmethod
    def get_selected_element(self, app: Object) -> Optional[IStructure]:
        """Fetches the currently selected element from the host environment."""
        raise NotImplementedError


class AnalysisService:
    """
    HIGH-LEVEL ORCHESTRATOR: Uses the abstractions to perform the analysis.
    It is injected with strategies (analyzers) and knows nothing about concrete types.
    """

    def __init__(self, analyzers: List[Type[IElementAnalyzer]]):
        self._analyzers = analyzers

    def run_analysis(self, element_to_analyze: Optional[IStructure], app: Object) -> dict:
        """Finds the right analyzer and executes it on the provided element."""
        if not element_to_analyze:
            return {'status': "Please select a single element in the App Explorer."}

        for analyzer_class in self._analyzers:
            if analyzer_class.can_handle(element_to_analyze):
                analyzer_instance = analyzer_class(element_to_analyze, app)
                nodes, edges = analyzer_instance.analyze()

                center_label = f"{element_to_analyze.Module.Name}.{element_to_analyze.Name}"
                return {
                    'graph_data': {'nodes': nodes, 'edges': edges, 'centerNodeLabel': center_label}
                }

        return {'status': f"Analysis for element type '{type(element_to_analyze).__name__}' is not supported."}

# ================================================================================
# PART 2: CONCRETE PROVIDER IMPLEMENTATION (User-defined)
# Developer must provide the concrete logic for getting an element here.
# ================================================================================


class StudioProSelectionProvider(ISelectionProvider):
    """
    A concrete implementation for getting the selected element from the Mendix
    Studio Pro App Explorer.
    """

    def get_selected_element(self, app: Object) -> Optional[IStructure]:
        """
        ============================ DEVELOPER ACTION REQUIRED ============================
        Implement the correct logic to get a single selected element.
        The Mendix Extensions API for selection can be complex. The logic below
        is a robust placeholder that handles common scenarios.

        Please verify this against the official Mendix API documentation for your
        version of Studio Pro.
        =================================================================================
        """
        try:
            selection = app.Selection
            if not selection:
                return None

            if hasattr(selection, 'SelectedElement') and selection.SelectedElement:
                return selection.SelectedElement if isinstance(selection.SelectedElement, IStructure) else None

            if hasattr(selection, 'SelectedElementsInAppExplorer') and selection.SelectedElementsInAppExplorer:
                if len(selection.SelectedElementsInAppExplorer) == 1:
                    element = selection.SelectedElementsInAppExplorer[0]
                    return element if isinstance(element, IStructure) else None

            return None
        except Exception:
            return None

# ================================================================================
# PART 3: CONCRETE ANALYZER IMPLEMENTATIONS (User-defined)
# These are the "plugins" for the analysis service.
# ================================================================================


class MicroflowAnalyzer(IElementAnalyzer):
    @classmethod
    def can_handle(cls, element: IStructure) -> bool:
        return isinstance(element, IMicroflow)

    def analyze(self) -> tuple[List[dict], List[dict]]:
        self._add_node(self.element, group='microflow', is_center=True)
        # Usages
        for usage in self.element.FindUsages():
            self._add_node(usage, group=self._get_group(usage))
            self._add_edge(usage, self.element, label="calls")
        # Dependencies
        for activity in self.element.Activities:
            if isinstance(activity, IMicroflowCall) and activity.Microflow:
                self._add_node(activity.Microflow, group='microflow')
                self._add_edge(self.element, activity.Microflow, label="calls")
            elif isinstance(activity, IShowPageAction) and activity.Page:
                self._add_node(activity.Page, group='page')
                self._add_edge(self.element, activity.Page, label="shows")
        return self.nodes, self.edges

    def _get_group(self, e: IStructure) -> str:
        if isinstance(e, IMicroflow):
            return 'microflow'
        if isinstance(e, IPage):
            return 'page'
        return 'default'


class AttributeAnalyzer(IElementAnalyzer):
    @classmethod
    def can_handle(cls, element: IStructure) -> bool:
        return isinstance(element, IAttribute)

    def analyze(self) -> tuple[List[dict], List[dict]]:
        self._add_node(self.element, group='attribute', is_center=True)
        for usage in self.element.FindUsages():
            group = 'microflow' if isinstance(
                usage, IMicroflow) else 'page' if isinstance(usage, IPage) else 'default'
            self._add_node(usage, group=group)
            self._add_edge(usage, self.element, label="uses")
        return self.nodes, self.edges

# ================================================================================
# PART 4: APPLICATION ENTRYPOINT & WIRING (Configuration)
# ================================================================================


# 1. Register available analyzer "plugins"
REGISTERED_ANALYZERS: List[Type[IElementAnalyzer]] = [
    MicroflowAnalyzer,
    AttributeAnalyzer,
]

# 2. Choose and instantiate the concrete selection provider
selection_provider: ISelectionProvider = StudioProSelectionProvider()

# 3. Instantiate the core service, injecting the registered analyzers
analysis_service: AnalysisService = AnalysisService(REGISTERED_ANALYZERS)

# 4. Define the main message handler, which uses the wired services


def onMessage(e: Object):
    """ Main message handler. Acts as a thin entry point. """
    try:
        if e.Message == "frontend:analyze_selection":
            selected_element = selection_provider.get_selected_element(
                currentApp)
            result = analysis_service.run_analysis(
                selected_element, currentApp)

            if 'graph_data' in result:
                PostMessage("backend:graph_data",
                            json.dumps(result['graph_data']))
            elif 'status' in result:
                PostMessage("backend:status", result['status'])

    except Exception as ex:
        PostMessage("backend:status", f"A critical error occurred: {str(ex)}")


# Initial message when the plugin is loaded
PostMessage("backend:status",
            "Ready. Select a supported element and click 'Analyze'.")
