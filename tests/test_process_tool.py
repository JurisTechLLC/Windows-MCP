import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


PROCESS_TOOL_PATH = Path(__file__).resolve().parents[1] / "src" / "windows_mcp" / "tools" / "process.py"


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, name, **kwargs):
        def decorator(func):
            self.tools[name] = func
            return func

        return decorator


def _load_process_module():
    infra_module = types.ModuleType("windows_mcp.infrastructure")

    def with_analytics(_analytics, _name):
        def decorator(func):
            return func

        return decorator

    infra_module.with_analytics = with_analytics

    mcp_types_module = types.ModuleType("mcp.types")

    class ToolAnnotations:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    mcp_types_module.ToolAnnotations = ToolAnnotations

    fastmcp_module = types.ModuleType("fastmcp")

    class Context: ...

    fastmcp_module.Context = Context

    sys.modules["windows_mcp.infrastructure"] = infra_module
    sys.modules["mcp.types"] = mcp_types_module
    sys.modules["fastmcp"] = fastmcp_module

    spec = importlib.util.spec_from_file_location("test_process_tool_module", PROCESS_TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_process_list_accepts_filter_aliases_and_pagination():
    process_module = _load_process_module()
    desktop = MagicMock()
    desktop.list_processes.return_value = "ok"

    mcp = FakeMCP()
    process_module.register(mcp, get_desktop=lambda: desktop, get_analytics=lambda: None)

    result = mcp.tools["Process"](mode="list", filter="chrome", sort_by="cpu", limit=50, offset=10)

    assert result == "ok"
    desktop.list_processes.assert_called_once_with(
        name="chrome", sort_by="cpu", limit=50, offset=10
    )


def test_process_kill_uses_name_filter_alias_when_name_missing():
    process_module = _load_process_module()
    desktop = MagicMock()
    desktop.kill_process.return_value = "killed"

    mcp = FakeMCP()
    process_module.register(mcp, get_desktop=lambda: desktop, get_analytics=lambda: None)

    result = mcp.tools["Process"](mode="kill", name_filter="notepad.exe", force="true")

    assert result == "killed"
    desktop.kill_process.assert_called_once_with(name="notepad.exe", pid=None, force=True)
