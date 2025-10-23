from System.Text.Json import JsonSerializer
from dependency_injector import containers, providers
import uuid
import threading
import json
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod

# Mendix and .NET related imports
import clr
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
# ShowDevTools()

PostMessage("backend:clear", '')

c = configurationService.Configuration


PostMessage("backend:info", f'{c.MendixVersion}.{c.BuildTag}')
PostMessage("backend:info", f'{c.EarliestSupportedLegacyMendixVersion}')
PostMessage("backend:info", f'{c.LatestSupportedLegacyMendixVersion }')
