import json, re, time
from datetime import datetime

MCP_SERVERS = {
    "inventario_local": {"tools": ["find_stores_by_zone", "recommend_complements"]},
}

LOG_PATH = "mcp_logs.jsonl"
def log_mcp(event: dict):
    event["ts"] = datetime.now().isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def call_tool(server: str, tool: str, args: dict):
    from mcp_server import tool_find_stores_by_zone, tool_recommend_complements
    handlers = {
        "find_stores_by_zone": tool_find_stores_by_zone,
        "recommend_complements": tool_recommend_complements
    }
    request = {"server": server, "tool": tool, "args": args}
    log_mcp({"direction": "request", **request})
    result = handlers[tool](args)
    log_mcp({"direction": "response", "result": result})
    return result

def detect_zone(text: str):
    m = re.search(r"zona\s*(\d+)", text.lower())
    return m.group(1) if m else None

print("Host CLI listo. Comandos: :logs para ver interacciones MCP, Ctrl+C para salir.")
while True:
    try:
        q = input("Usuario: ").strip()
        if q == ":logs":
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                print("— LOGS —")
                for line in f:
                    print(line.rstrip())
            continue
        z = detect_zone(q)
        if z:
            data = call_tool("inventario_local", "find_stores_by_zone", {"zone": z})
            if not data:
                print(f"No hay tiendas en zona {z}.")
            else:
                for r in data[:10]:
                    print(f"• {r['Nombre']} — {r['Calle']}, Zona {r['Zona']}, {r['Ciudad']} (Stock {r.get('Stock','?')})")
        else:
            # Aquí tu llamada al LLM (Groq/Anthropic) + políticas antialucinación
            print("(LLM) ¿Podrías indicar tu zona para buscar disponibilidad?")
    except KeyboardInterrupt:
        print("\nAdiós!")
        break
