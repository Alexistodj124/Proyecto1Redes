# inventario.py
import pandas as pd
import re
from pathlib import Path
from typing import List, Dict, Any

class Inventario:
    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        self._df = None
        self._mtime = None
        self._load()

    def _load(self):
        df = pd.read_csv(self.csv_path, quotechar='"', encoding='utf-8', on_bad_lines='skip', dtype=str)
        df.columns = df.columns.str.replace('"', '').str.strip()
        for col in ['Nombre','Calle','Ciudad','Zona','Producto','Stock']:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()
        self._df = df
        self._mtime = self.csv_path.stat().st_mtime

    def _hot_reload(self):
        m = self.csv_path.stat().st_mtime
        if self._mtime != m:
            self._load()

    @staticmethod
    def normalizar_ubicacion(texto: str) -> str:
        m = re.search(r"zona\s*(\d+)", texto.lower())
        return m.group(1) if m else ""

    def buscar_tiendas_en_zona(self, zona: str) -> List[Dict[str, Any]]:
        self._hot_reload()
        z = str(zona).strip()
        df = self._df.copy()
        df['Zona'] = df['Zona'].astype(str).str.extract(r'(\d+)')[0]
        res = df[df['Zona'] == z]
        cols = [c for c in ['Nombre','Calle','Ciudad','Zona','Producto','Stock'] if c in res.columns]
        return res[cols].to_dict(orient='records')

    def recomendar_complementos(self, producto: str, zona: str | None = None) -> Dict[str, Any]:
        self._hot_reload()
        df = self._df.copy()
        if zona:
            df['Zona'] = df['Zona'].astype(str).str.extract(r'(\d+)')[0]
            df = df[df['Zona'] == str(zona)]
        # Heurística sencilla: devolver otros productos frecuentes distintos del consultado
        base = df[df['Producto'].str.contains(producto, case=False, na=False)]
        disponibilidad = base.to_dict(orient='records')
        complementos = (
            df[~df['Producto'].str.contains(producto, case=False, na=False)]
              .groupby('Producto', dropna=True)
              .size()
              .sort_values(ascending=False)
              .head(3)
              .index.tolist()
        )
        return {"disponibilidad": disponibilidad, "sugeridos": complementos}
