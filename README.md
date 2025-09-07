# MCP Local Server – Inventario (CSV)

Este proyecto implementa un **servidor MCP local** que expone herramientas para consultar inventario de productos desde un archivo **CSV**.  
Forma parte del **Proyecto 1 – CC3067 Redes** (Uso de un protocolo existente).

---

## Requisitos

- Python 3.11 o superior  
- Virtualenv (recomendado)  

Dependencias:
- `pandas`  

Instálalas con:

```bash
pip install -r requirements.txt
```
---

# Cómo ejecutar el servidor MCP
Clona o descarga el repositorio.
Entra a la carpeta del proyecto:
```bash 
cd proyecto1
```
Crea y activa un entorno virtual:
```bash
python3 -m venv venv
```
```bash
source venv/bin/activate
```
Instala dependencias:
```bash
pip install -r requirements.txt
```
Corre el servidor MCP local:
```bash
python mcp_server.py
```
Verás en consola:
```bash
🟢 Servidor MCP Local iniciado. Esperando requests JSON-RPC...
```
