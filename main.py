import json
import traceback
from typing import Any, Dict, Callable, Iterable
from abc import ABC, abstractmethod

# Mendix and .NET related imports
import clr
clr.AddReference("System.Text.Json")
clr.AddReference("Mendix.StudioPro.ExtensionsAPI")
import threading
import uuid
from dependency_injector import containers, providers
from System.Text.Json import JsonSerializer
# ShowDevTools()

PostMessage("backend:clear", '')
from Mendix.StudioPro.ExtensionsAPI.BackgroundJobs import BackgroundJob
job = BackgroundJob('test')
jobType = job.GetType()
assembly = jobType.Assembly

all_types = list(assembly.GetTypes())

PostMessage("backend:info", f'{all_types}')
