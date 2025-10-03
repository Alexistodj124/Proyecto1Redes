# client.py — Cliente de consola (Groq + MCP WS) con respuestas ancladas a MCP
import os, sys, re, json, asyncio, requests
import websockets

# --- Consola Windows UTF-8 + event loop compatible
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# === CONFIG ===
GROQ_API_KEY = "APIKEY"
MODEL = "llama-3.1-8b-instant"
MCP_URL = "ws://127.0.0.1:8000/mcp"
# MCP_URL = "ws://3.140.209.59:8000/mcp"

# === LLM (Groq) helpers ===
def chat_groq(messages, temperature=0.3, max_tokens=400, timeout=30):
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=timeout,
    )
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return f"[LLM error] {data}"

def groq_grounded_summary(user_msg: str, tool_name: str, tool_json: dict|list, zona: str|None = None) -> str:
    """
    Pide al LLM que redacte una respuesta usando SOLO los datos del MCP.
    """
    data_block = json.dumps(tool_json, ensure_ascii=False, indent=2)
    sys_inst = (
        "Eres un asistente para una distribuidora de arena para gato en Guatemala. "
        "DEBES responder únicamente con los datos provistos en DATA. Para los productos. A otras preguntas, puedes responderlas de tipo general. "
        "Prohibido inventar tiendas, direcciones o cantidades no presentes en DATA. "
        # "Si DATA está vacío, di que no hay resultados y pide otra zona o referencia. "
        "Sé claro y conciso. Si hay zona, menciónala."
    )
    user_prompt = f"""Usuario: {user_msg}

TOOL: {tool_name}
DATA:
{data_block}

Instrucciones:
- Resume y presenta los resultados de DATA en viñetas.
- Si DATA es una lista de tiendas, muestra Nombre, Calle, Ciudad y Zona.
- Si DATA es un objeto con 'disponibilidad' y 'sugeridos', resume disponibilidad y luego lista sugeridos.
- No agregues información que no esté en DATA.
- Si no hay datos, explica que no se encontró y sugiere dar otra zona o punto de referencia."""
    msgs = [{"role":"system","content":sys_inst},
            {"role":"user","content":user_prompt}]
    return chat_groq(msgs, temperature=0.2, max_tokens=500)

# === MCP (WebSocket JSON-RPC) helpers ===
async def mcp_init(ws):
    await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}))
    _ = json.loads(await ws.recv())
    # opcional: tools/list
    await ws.send(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}))
    _ = json.loads(await ws.recv())

async def mcp_call(ws, name: str, arguments: dict):
    req = {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":name,"arguments":arguments}}
    await ws.send(json.dumps(req))
    data = json.loads(await ws.recv())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]

async def call_mcp_tool(name: str, arguments: dict):
    async with websockets.connect(MCP_URL, subprotocols=["jsonrpc"]) as ws:
        await mcp_init(ws)
        return await mcp_call(ws, name, arguments)

# === Utilidades ===
def extract_zona(text: str) -> str|None:
    m = re.search(r"\bzona\s*(\d{1,2})\b", text.lower())
    return m.group(1) if m else None

# === LOOP ===
async def main():
    print("\n🟢 Cliente MCP + Groq (Ctrl+C para salir)\n")
    historial = [
        {"role":"system","content":(
            "Eres un asistente para una distribuidora de arena para gato en Guatemala. "
            "Cuando NO se te proporciona DATA de herramientas, responde brevemente "
            "pidiendo zona o referencia. No inventes datos concretos. "
            "Cuando se te proporcione DATA, se usará otro prompt para anclarte."
        )}
    ]

    while True:
        try:
            user = input("Cliente: ").strip()
            if not user:
                continue

            # 1) Detecta intención/slot localmente
            zona_num = extract_zona(user)
            pedir_complementos = any(k in user.lower() for k in ["complemento", "complementarios", "recomienda", "recomendar"])

            if zona_num:
                # 2) TOOL-FIRST -> MCP primero
                try:
                    tiendas = await call_mcp_tool("find_stores_by_zone", {"zone": zona_num})
                except Exception as e:
                    print(f"❌ Error MCP (find_stores_by_zone): {e}")
                    # fallback minimalista
                    base = [{"Nombre":"(sin datos)","Calle":"-","Ciudad":"-","Zona":zona_num}]
                    print("📦 MCP tiendas (fallback):", base)
                    tiendas = base

                # 3) Redacta con LLM pero ANCLADO a DATA
                respuesta = groq_grounded_summary(
                    user_msg=user,
                    tool_name="find_stores_by_zone",
                    tool_json=tiendas,
                    zona=zona_num
                )
                print(f"Asistente: {respuesta}")
                continue

            if pedir_complementos:
                # 2) TOOL-FIRST -> recomendar complementos (sin zona o con zona si la detectas)
                zona_opt = extract_zona(user)
                product_name = user  # si quieres, parsea mejor el nombre del producto
                args = {"product_name": product_name}
                if zona_opt:
                    args["zone"] = zona_opt

                try:
                    comp = await call_mcp_tool("recommend_complements", args)
                except Exception as e:
                    print(f"❌ Error MCP (recommend_complements): {e}")
                    comp = {"disponibilidad":[],"sugeridos":[]}

                respuesta = groq_grounded_summary(
                    user_msg=user,
                    tool_name="recommend_complements",
                    tool_json=comp,
                    zona=zona_opt
                )
                print(f"Asistente: {respuesta}")
                continue

            # 4) Si no hay zona ni intención de complementos -> usa LLM para pedirla (sin inventar)
            historial.append({"role":"user","content":user})
            base = chat_groq(historial, temperature=0.4, max_tokens=200)
            print(f"Asistente: {base}")
            historial.append({"role":"assistant","content":base})

        except KeyboardInterrupt:
            print("\n👋 Conversación finalizada.")
            break

if __name__ == "__main__":
    asyncio.run(main())
