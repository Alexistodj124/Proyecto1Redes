# mcp_server.py
import sys, json
from inventario import Inventario

inv = Inventario("prueba.csv")

def handle_request(request):
    if request["method"] == "find_stores_by_zone":
        zone = request["params"]["zone"]
        result = inv.buscar_tiendas_en_zona(zone)
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": result
        }
    elif request["method"] == "recommend_complements":
        product = request["params"]["product_name"]
        zone = request["params"].get("zone")
        result = inv.recomendar_complementos(product, zone)
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": result
        }
    else:
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "error": {"code": -32601, "message": "Método no encontrado"}
        }

def main():
    print("🟢 Servidor MCP Local iniciado. Esperando requests JSON-RPC...\n")
    for line in sys.stdin:  # Lee línea JSON desde stdin
        try:
            request = json.loads(line.strip())
            response = handle_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err = {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
