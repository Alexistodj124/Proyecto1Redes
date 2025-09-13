from typing import List, Dict, Any
from mcp.server.fastmcp import FastMCP
from inventario import Inventario
import os


# Instancia de inventario basada en CSV
CSV_PATH = os.getenv("INVENTARIO_CSV", "/Users/alexismesias/Library/CloudStorage/OneDrive-Personal/UVG8VO/REDES/Proyecto1Redes/prueba.csv")
inv = Inventario(CSV_PATH)

# Crea el servidor MCP
mcp = FastMCP("inventario_csv")

@mcp.tool()
def find_stores_by_zone(zone: str) -> List[Dict[str, Any]]:
    """
    Devuelve tiendas/stock por zona.
    Args:
        zone: Número de zona (e.g., "10")
    Returns:
        Lista de dicts: [{Nombre,Calle,Ciudad,Zona,Producto,Stock}, ...]
    """
    return inv.buscar_tiendas_en_zona(zone)

@mcp.tool()
def recommend_complements(product_name: str, zone: str | None = None) -> Dict[str, Any]:
    """
    Disponibilidad del producto y sugerencias complementarias.
    Args:
        product_name: Nombre del producto a buscar (e.g., "Bionic")
        zone: Número de zona (opcional, e.g., "15")
    Returns:
        {
          "disponibilidad": [ ... coincidencias ... ],
          "sugeridos": ["Producto A", "Producto B", "Producto C"]
        }
    """
    return inv.recomendar_complementos(product_name, zone)

if __name__ == "__main__":
    mcp.run(transport="stdio")
