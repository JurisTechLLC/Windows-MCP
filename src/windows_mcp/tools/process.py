"""Process tool — list and kill running processes."""

from typing import Literal

from mcp.types import ToolAnnotations
from windows_mcp.infrastructure import with_analytics
from fastmcp import Context


def register(mcp, *, get_desktop, get_analytics):
    @mcp.tool(
        name="Process",
        description='List and kill running processes. Keywords: task manager, running tasks, kill, terminate, stop process, PID, CPU, memory usage. Use mode="list" to list running processes with filtering, sorting, and optional pagination via limit/offset. Name filtering accepts name, filter, or name_filter. Use mode="kill" to terminate processes by PID or name.',
        annotations=ToolAnnotations(
            title="Process",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    @with_analytics(get_analytics(), "Process-Tool")
    def process_tool(
        mode: Literal["list", "kill"],
        name: str | None = None,
        filter: str | None = None,
        name_filter: str | None = None,
        pid: int | None = None,
        sort_by: Literal["memory", "cpu", "name"] = "memory",
        limit: int | None = None,
        offset: int = 0,
        force: bool | str = False,
        ctx: Context = None,
    ) -> str:
        desktop = get_desktop()
        process_name = name if name is not None else (filter if filter is not None else name_filter)
        try:
            if mode == "list":
                return desktop.list_processes(
                    name=process_name, sort_by=sort_by, limit=limit, offset=offset
                )
            elif mode == "kill":
                force = force is True or (isinstance(force, str) and force.lower() == "true")
                return desktop.kill_process(name=process_name, pid=pid, force=force)
            else:
                return 'Error: mode must be either "list" or "kill".'
        except Exception as e:
            return f"Error managing processes: {str(e)}"
