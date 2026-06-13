import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

from fastmcp.utilities.types import Image


def _load_snapshot_helpers(monkeypatch):
    fake_service = ModuleType("windows_mcp.desktop.service")

    class Desktop:  # pragma: no cover - placeholder for import
        pass

    @dataclass
    class Size:
        width: int
        height: int

    fake_service.Desktop = Desktop
    fake_service.Size = Size
    monkeypatch.setitem(sys.modules, "windows_mcp.desktop.service", fake_service)

    fake_utils = ModuleType("windows_mcp.desktop.utils")
    fake_utils.remove_private_use_chars = lambda text: text
    monkeypatch.setitem(sys.modules, "windows_mcp.desktop.utils", fake_utils)

    module_name = "test_snapshot_helpers_module"
    sys.modules.pop(module_name, None)
    snapshot_helpers_path = Path(__file__).resolve().parents[1] / "src/windows_mcp/tools/_snapshot_helpers.py"
    spec = importlib.util.spec_from_file_location(module_name, snapshot_helpers_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capture_result(*, screenshot_bytes: bytes | None):
    desktop_state = SimpleNamespace(
        cursor_position=(100, 200),
        screenshot_original_size=None,
        screenshot_region=None,
        screenshot_displays=None,
        screenshot_backend=None,
    )
    return {
        "desktop_state": desktop_state,
        "interactive_elements": "interactive",
        "scrollable_elements": "scrollable",
        "semantic_tree": "tree",
        "windows": "windows",
        "active_window": "active",
        "active_desktop": "desktop-1",
        "all_desktops": "desktop-1,desktop-2",
        "screenshot_bytes": screenshot_bytes,
    }


def test_build_snapshot_response_appends_screenshot_note_when_image_present(monkeypatch):
    helpers = _load_snapshot_helpers(monkeypatch)

    response = helpers.build_snapshot_response(
        _capture_result(screenshot_bytes=b"png-bytes"),
        include_ui_details=False,
    )

    assert isinstance(response, list)
    assert len(response) == 2
    assert isinstance(response[0], str)
    assert response[0].endswith("\n[Screenshot attached above]")
    assert isinstance(response[1], Image)


def test_build_snapshot_response_keeps_single_text_part_without_image(monkeypatch):
    helpers = _load_snapshot_helpers(monkeypatch)

    response = helpers.build_snapshot_response(
        _capture_result(screenshot_bytes=None),
        include_ui_details=False,
    )

    assert isinstance(response, list)
    assert len(response) == 1
    assert isinstance(response[0], str)
    assert "[Screenshot attached above]" not in response[0]
