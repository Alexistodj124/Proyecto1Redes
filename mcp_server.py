# Servidor MCP vía WebSocket
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from typing import List, Dict, Any
import json, os, re

from inventario import Inventario

CSV_PATH = os.getenv("INVENTARIO_CSV", "prueba.csv")
inv = Inventario(CSV_PATH)

app = FastAPI(title="MCP Inventario (WS)")

# HTTP GET /
@app.get("/", response_class=PlainTextResponse)
def root():
    return "MCP WS server. Connect via WebSocket at /mcp (subprotocol: jsonrpc)."

# Definición de herramientas MCP
TOOLS = [
    {
        "name": "find_stores_by_zone",
        "description": "Devuelve tiendas/stock por zona.",
        "input_schema": {
            "type": "object",
            "properties": {"zone": {"type": "string"}},
            "required": ["zone"],
        },
    },
    {
        "name": "recommend_complements",
        "description": "Disponibilidad del producto y sugerencias complementarias.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "zone": {"type": "string"},
            },
            "required": ["product_name"],
        },
    },
]

PROTOCOL = "MCP/2025-06-18"

async def handle_rpc(req: dict) -> dict:
    """Maneja métodos JSON-RPC propios del MCP."""
    j = {"jsonrpc": "2.0", "id": req.get("id")}
    method = req.get("method")
    params = req.get("params") or {}

    try:
        if method == "initialize":
            j["result"] = {
                "protocol": PROTOCOL,
                "capabilities": {"tools": True},
                "tools": TOOLS,
            }
            return j

        if method == "tools/list":
            j["result"] = {"tools": TOOLS}
            return j

        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "find_stores_by_zone":
                zone = str(args.get("zone", "")).strip()
                result = inv.buscar_tiendas_en_zona(zone)
                j["result"] = result
                return j

            if name == "recommend_complements":
                product_name = str(args.get("product_name", "")).strip()
                zone = args.get("zone")
                if zone is not None:
                    zone = str(zone).strip()
                result = inv.recomendar_complementos(product_name, zone)
                j["result"] = result
                return j

            # método no encontrado
            j["error"] = {"code": -32601, "message": "Method not found"}
            return j

        # método desconocido
        j["error"] = {"code": -32601, "message": "Method not found"}
        return j

    except Exception as e:
        j["error"] = {"code": -32603, "message": f"{type(e).__name__}: {e}"}
        return j

@app.websocket("/mcp")
async def ws_mcp(websocket: WebSocket):
    requested = websocket.headers.get("sec-websocket-protocol", "")
    if "jsonrpc" in [s.strip() for s in requested.split(",") if s]:
        await websocket.accept(subprotocol="jsonrpc")
    else:
        await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
                )
                continue

            resp = await handle_rpc(req)
            await websocket.send_text(json.dumps(resp))

    except WebSocketDisconnect:
        return
