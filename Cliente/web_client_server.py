import os, sys, re, json, asyncio, uuid
from typing import Dict, Any
import requests
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ========= CONFIG =========
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
MCP_URL = os.getenv("MCP_URL", "ws://3.140.209.59:8000/mcp") 
# MCP_URL = os.getenv("MCP_URL", "ws://127.0.0.1:8000/mcp") 

# ========= LLM (Groq) =========
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
    data_block = json.dumps(tool_json, ensure_ascii=False, indent=2)
    sys_inst = (
        "Eres un asistente para una distribuidora de arena para gato en Guatemala. "
        "DEBES responder únicamente con los datos provistos en DATA. "
        "Prohibido inventar tiendas, direcciones o cantidades no presentes en DATA. "
        "Si DATA está vacío, di que no hay resultados y pide otra zona o referencia. "
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

# ========= MCP (WebSocket JSON-RPC) =========
async def mcp_init(ws):
    await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}))
    _ = json.loads(await ws.recv())
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

# ========= Utilidades =========
def extract_zona(text: str) -> str|None:
    m = re.search(r"\bzona\s*(\d{1,2})\b", text.lower())
    return m.group(1) if m else None

# ========= Estado de conversación por sesión =========
SESSIONS: Dict[str, list] = {}

def get_historial(session_id: str) -> list:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = [{
            "role":"system","content":(
                "Eres un asistente para una distribuidora de arena para gato en Guatemala. "
                "Cuando NO se te proporciona DATA de herramientas, responde brevemente "
                "pidiendo zona o referencia. No inventes datos concretos. "
                "Cuando se te proporcione DATA, se usará otro prompt para anclarte."
            )
        }]
    return SESSIONS[session_id]

# ========= FastAPI app =========
app = FastAPI(title="Cliente Web - MCP + Groq")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Página HTML (embebida)
HTML_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Cliente MCP</title>
<style>
  :root{
    --bg:#0f172a;        /* slate-900 */
    --panel:#111827;     /* gray-900 */
    --mine:#1d4ed8;      /* blue-700 */
    --bot:#374151;       /* gray-700 */
    --text:#e5e7eb;      /* gray-200 */
    --muted:#9ca3af;     /* gray-400 */
  }
  *{box-sizing:border-box}
  body{
    margin:0; background:var(--bg); color:var(--text);
    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
    height:100svh; display:flex; flex-direction:column;
  }
  header{
    padding:14px 16px; border-bottom:1px solid #1f2937; background:#0b1220;
    font-weight:600;
  }
  #chat{
    flex:1; overflow:auto; padding:16px; display:flex; flex-direction:column; gap:12px;
  }
  .bubble{
    max-width:min(720px, 80%); padding:12px 14px; border-radius:14px;
    line-height:1.4; white-space:pre-wrap; word-wrap:break-word;
    box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset, 0 2px 10px rgba(0,0,0,0.25);
  }
  .mine{ align-self:flex-end; background:var(--mine); color:white; border-top-right-radius:4px; }
  .bot{ align-self:flex-start; background:var(--bot); color:var(--text); border-top-left-radius:4px; }
  .meta{ font-size:12px; color:var(--muted); margin-top:4px }
  footer{
    border-top:1px solid #1f2937; padding:12px; background:#0b1220; display:flex; gap:8px;
  }
  #msg{
    flex:1; padding:12px 14px; border-radius:10px; border:1px solid #313a49; background:#0f172a; color:var(--text);
    outline:none;
  }
  button{
    padding:12px 16px; border-radius:10px; border:1px solid #2943a6; background:#1e3a8a; color:white; cursor:pointer;
  }
  button:disabled{ opacity:0.6; cursor:not-allowed }
  .row{ display:flex; gap:8px; align-items:center }
</style>
</head>
<body>
  <header>Cliente MCP</header>
  <div id="chat"></div>
  <footer>
    <input id="msg" type="text" placeholder="Escribe tu mensaje..." autocomplete="off"/>
    <button id="send">Enviar</button>
  </footer>
<script>
  const chat = document.getElementById('chat');
  const input = document.getElementById('msg');
  const btn = document.getElementById('send');

  // Genera un sessionId persistente por pestaña
  let sessionId = localStorage.getItem('mcp_session_id');
  if(!sessionId){
    sessionId = crypto.randomUUID();
    localStorage.setItem('mcp_session_id', sessionId);
  }

  function addBubble(text, who){
    const wrap = document.createElement('div');
    wrap.className = 'bubble ' + (who==='me' ? 'mine' : 'bot');
    wrap.textContent = text;
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
  }

  async function sendMessage(){
    const text = input.value.trim();
    if(!text) return;
    input.value = '';
    addBubble(text, 'me');
    btn.disabled = true;

    try{
      const resp = await fetch('/chat', {
        method:'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ sessionId, message: text })
      });
      const data = await resp.json();
      if(data && data.reply){
        addBubble(data.reply, 'bot');
      }else{
        addBubble('[Error] Respuesta vacía', 'bot');
      }
    }catch(e){
      addBubble('[Error de red] ' + e, 'bot');
    }finally{
      btn.disabled = false;
      input.focus();
    }
  }

  btn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', (e)=>{ if(e.key==='Enter') sendMessage(); });

  // Mensaje inicial opcional
  addBubble('Hola 👋 ¿en qué te ayudo? (por ejemplo: "Estoy en zona 10" o "recomienda complementos Bionic zona 15")','bot');
  input.focus();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE

@app.post("/chat")
async def chat_api(req: Request):
    payload = await req.json()
    session_id = payload.get("sessionId") or str(uuid.uuid4())
    user = (payload.get("message") or "").strip()
    if not user:
        return JSONResponse({"reply":"(mensaje vacío)"})

    historial = get_historial(session_id)

    zona_num = extract_zona(user)
    pedir_complementos = any(k in user.lower() for k in ["complemento", "complementarios", "recomienda", "recomendar"])

    if zona_num:
        try:
            tiendas = await call_mcp_tool("find_stores_by_zone", {"zone": zona_num})
        except Exception as e:
            tiendas = [{"Nombre":"(sin datos)","Calle":"-","Ciudad":"-","Zona":zona_num}]
        respuesta = groq_grounded_summary(
            user_msg=user,
            tool_name="find_stores_by_zone",
            tool_json=tiendas,
            zona=zona_num
        )
        return JSONResponse({"reply": respuesta, "sessionId": session_id})

    if pedir_complementos:
        zona_opt = extract_zona(user)
        product_name = user
        args = {"product_name": product_name}
        if zona_opt:
            args["zone"] = zona_opt
        try:
            comp = await call_mcp_tool("recommend_complements", args)
        except Exception as e:
            comp = {"disponibilidad":[],"sugeridos":[]}
        respuesta = groq_grounded_summary(
            user_msg=user,
            tool_name="recommend_complements",
            tool_json=comp,
            zona=zona_opt
        )
        return JSONResponse({"reply": respuesta, "sessionId": session_id})

    historial.append({"role":"user","content":user})
    base = chat_groq(historial, temperature=0.4, max_tokens=200)
    historial.append({"role":"assistant","content":base})
    return JSONResponse({"reply": base, "sessionId": session_id})


if __name__ == "__main__":
    import uvicorn
    print("MCP_URL =", MCP_URL)
    uvicorn.run("web_client_server:app", host="0.0.0.0", port=8080, reload=False)
