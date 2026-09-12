"""
Cliente MCP real para la herramienta de tickets.

Este módulo levanta `mcp_server/server.py` como subproceso (stdio
transport) usando el cliente oficial de FastMCP, y expone dos funciones
SÍNCRONAS (para no tener que volver async todo el grafo de LangGraph):
`create_ticket(...)` y `get_ticket_status(...)`. Cada llamada abre una
sesión MCP real, invoca la tool remota vía JSON-RPC sobre stdio, y cierra
la sesión — igual que hablaría con cualquier server MCP externo.
"""
import asyncio
import os
from pathlib import Path
from typing import Any, Dict

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

_PROJECT_ROOT = Path(__file__).parent.parent
_SERVER_SCRIPT = _PROJECT_ROOT / "mcp_server" / "server.py"


def _build_transport() -> PythonStdioTransport:
    return PythonStdioTransport(
        script_path=str(_SERVER_SCRIPT),
        cwd=str(_PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(_PROJECT_ROOT)},
    )


async def _call_tool_async(tool_name: str, arguments: Dict[str, Any]) -> str:
    transport = _build_transport()
    client = Client(transport)
    async with client:
        result = await client.call_tool(tool_name, arguments)
        # FastMCP devuelve `.data` cuando hay contenido estructurado o texto simple
        if hasattr(result, "data") and result.data is not None:
            return str(result.data)
        return str(result)


def _run_sync(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Ejecuta una llamada MCP async desde código síncrono (nodos de LangGraph)."""
    try:
        return asyncio.run(_call_tool_async(tool_name, arguments))
    except RuntimeError:
        # Ya hay un event loop corriendo (poco común en este proyecto, pero
        # se cubre por robustez si el server se llama desde contexto async).
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_call_tool_async(tool_name, arguments))
        finally:
            loop.close()


def create_ticket(employee_email: str, category: str, description: str) -> str:
    return _run_sync("create_ticket", {
        "employee_email": employee_email,
        "category": category,
        "description": description,
    })


def get_ticket_status(ticket_id: str) -> str:
    return _run_sync("get_ticket_status", {"ticket_id": ticket_id})