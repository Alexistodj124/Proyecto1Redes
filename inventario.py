# inventario.py
import pandas as pd
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional
import os

def normalize_text(s: str) -> str:
    """
    Normaliza para comparar: minúsculas, sin acentos, sin guiones/puntuación,
    colapsa espacios, quita palabras de relleno típicas.
    """
    if not s:
        return ""
    # a minúsculas
    s = s.lower()
    # quita acentos
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    # reemplaza guiones y barras por espacio
    s = re.sub(r"[-_/]", " ", s)
    # quita signos
    s = re.sub(r"[^a-z0-9\s\.]", " ", s)
    # plural simple
    s = re.sub(r"\b(juguetes)\b", "juguete", s)
    # colapsa espacios
    s = re.sub(r"\s+", " ", s).strip()
    return s

def tokenize(s: str) -> list:
    s = normalize_text(s)
    return [t for t in s.split() if t]

ALIAS_MAP = {
    "knino": "k nino",
    "k nino": "k nino",
    "k-nino": "k nino",
    "k  nino": "k nino",
    "bionic": "bionic",
    "mish": "mish",
    "l favourite": "l favourite",
    "lfavourite": "l favourite",
    "bio stones": "bio stones",
    "biostones": "bio stones",
}

class Inventario:
    def __init__(self, csv_path: str, complementos_csv: Optional[str] = None):
        self.csv_path = Path(csv_path)
        self.complementos_path = Path(
            complementos_csv or os.getenv("COMPLEMENTOS_CSV", "complementos_catalogo.csv")
        )

        self._df = None
        self._mtime = None

        self._df_compl = None
        self._mtime_compl = None

        self._load()
        self._load_complementos()

        # reglas fallback
        self._rules = [
            (r"\barena\b|\blitter\b", [
                "Pala para arenero",
                "Bandeja sanitaria con borde alto",
                "Desodorante para arenero",
                "Tapete atrapar-arena",
            ]),
            (r"\b(agglomerante|aglomerante|clumping)\b", [
                "Bolsas biodegradables",
                "Desodorante con carbón activado",
            ]),
            (r"\bbionic\b|\bjuguete\b", [
                "Premios de entrenamiento",
                "Collar reforzado",
                "Pelota interactiva",
            ]),
            (r"\b(antipulgas|pipeta|collar antipulgas)\b", [
                "Shampoo hipoalergénico",
                "Peine quitapulgas",
            ]),
        ]

    # -------------------------
    # Carga de datos principales
    # -------------------------
    def _load(self):
        df = pd.read_csv(
            self.csv_path,
            quotechar='"',
            encoding='utf-8',
            on_bad_lines='skip',
            dtype=str
        )
        df.columns = df.columns.str.replace('"', '').str.strip()
        for col in ['Nombre','Calle','Ciudad','Zona','Producto','Stock','Codigo']:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()

        if 'Producto' in df.columns:
            df['Producto_norm'] = df['Producto'].map(normalize_text)
        if 'Codigo' in df.columns:
            df['Codigo_norm'] = df['Codigo'].str.lower().str.strip()

        self._df = df
        self._mtime = self.csv_path.stat().st_mtime

    def _hot_reload(self):
        m = self.csv_path.stat().st_mtime
        if self._mtime != m:
            self._load()

    # ----------------------------------
    # Carga de catálogo de complementos
    # ----------------------------------
    def _load_complementos(self):
        if not self.complementos_path.exists():
            self._df_compl = None
            self._mtime_compl = None
            return

        dfc = pd.read_csv(
            self.complementos_path,
            quotechar='"',
            encoding='utf-8',
            on_bad_lines='skip',
            dtype=str
        )
        dfc.columns = dfc.columns.str.replace('"', '').str.strip()
        for col in [
            'base_nombre','base_codigo',
            'complemento_nombre','complemento_codigo',
            'tipo','razon'
        ]:
            if col in dfc.columns:
                dfc[col] = dfc[col].fillna("").astype(str).str.strip()

        # índices normalizados para match
        dfc['base_nombre_norm'] = dfc['base_nombre'].map(normalize_text)
        dfc['complemento_nombre_norm'] = dfc['complemento_nombre'].map(normalize_text)
        dfc['base_codigo_norm'] = dfc['base_codigo'].str.lower().str.strip()
        dfc['complemento_codigo_norm'] = dfc['complemento_codigo'].str.lower().str.strip()

        self._df_compl = dfc
        self._mtime_compl = self.complementos_path.stat().st_mtime

    def _hot_reload_complementos(self):
        if self._df_compl is None:
            return
        m = self.complementos_path.stat().st_mtime
        if self._mtime_compl != m:
            self._load_complementos()

    # -------------------------
    # Utilidades varias
    # -------------------------
    @staticmethod
    def normalizar_ubicacion(texto: str) -> str:
        m = re.search(r"zona\s*(\d+)", texto.lower())
        return m.group(1) if m else ""

    def _suggest_by_rules(self, texto_producto: str) -> List[str]:
        txt = (texto_producto or "").lower()
        sugerencias = []
        for pattern, sugs in self._rules:
            if re.search(pattern, txt):
                for s in sugs:
                    if s not in sugerencias:
                        sugerencias.append(s)
        if not sugerencias:
            sugerencias = [
                "Pala para arenero",
                "Bolsas biodegradables",
                "Desodorante para arenero",
            ]
        return sugerencias[:5]

    def _canon_from_alias(self, s: str) -> str:
        n = normalize_text(s)
        return ALIAS_MAP.get(n, n)

    def _match_complementos(self, producto: str, codigos_disponibles: set[str]) -> List[Dict[str, str]]:
        """
        Busca en el catálogo por código (si hay) y por nombre normalizado/tokenizado.
        """
        if self._df_compl is None or self._df_compl.empty:
            return []

        dfc = self._df_compl
        q_raw = (producto or "").strip()
        q_canon = self._canon_from_alias(q_raw)
        q_norm = normalize_text(q_canon)
        q_tokens = set(tokenize(q_canon))

        cands = []

        if codigos_disponibles:
            cand_by_code = dfc[dfc['base_codigo_norm'].isin({c.lower() for c in codigos_disponibles})]
            if not cand_by_code.empty:
                cands.append(cand_by_code)

        if q_tokens:
            mask = dfc['base_nombre_norm'].apply(lambda s: all(t in s for t in q_tokens))
            cand_by_name = dfc[mask]
            if cand_by_name.empty:
                mask_any = dfc['base_nombre_norm'].apply(lambda s: any(t in s for t in q_tokens))
                cand_by_name = dfc[mask_any]
            if not cand_by_name.empty:
                cands.append(cand_by_name)

        if not cands:
            return []

        mdf = pd.concat(cands, ignore_index=True).drop_duplicates()

        out = []
        seen = set()
        for _, r in mdf.iterrows():
            key = (r.get("complemento_nombre","").lower(), r.get("complemento_codigo","").lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "complemento_nombre": r.get("complemento_nombre",""),
                "complemento_codigo": r.get("complemento_codigo",""),
                "tipo": r.get("tipo",""),
                "razon": r.get("razon",""),
            })
        return out[:5]

    # ---------------------------------------
    # API: búsqueda de tiendas por 'Zona'
    # ---------------------------------------
    def buscar_tiendas_en_zona(self, zona: str) -> List[Dict[str, Any]]:
        self._hot_reload()
        z = str(zona).strip()
        df = self._df.copy()
        if 'Zona' in df.columns:
            df['Zona'] = df['Zona'].astype(str).str.extract(r'(\d+)')[0]
            res = df[df['Zona'] == z]
        else:
            res = df.iloc[0:0]

        cols = [c for c in ['Nombre','Calle','Ciudad','Zona','Producto','Stock','Codigo'] if c in res.columns]
        if not cols:
            return []
        return res[cols].to_dict(orient='records')

    # ----------------------------------------------------
    # API: recomendaciones de complementos
    # ----------------------------------------------------
    def recomendar_complementos(self, producto: str, zona: str | None = None) -> Dict[str, Any]:
        self._hot_reload()
        self._hot_reload_complementos()

        # ---------- disponibilidad ----------
        df = self._df.copy()
        if zona and 'Zona' in df.columns:
            df['Zona'] = df['Zona'].astype(str).str.extract(r'(\d+)')[0]
            df = df[df['Zona'] == str(zona)]

        has_producto = 'Producto' in df.columns

        if has_producto:
            q_norm = normalize_text(producto)
            base = df[df['Producto_norm'].str.contains(q_norm, na=False)]
            cols = [c for c in ['Nombre','Calle','Ciudad','Zona','Producto','Stock','Codigo'] if c in base.columns]
            disponibilidad = base[cols].to_dict(orient='records') if cols else base.to_dict(orient='records')
        else:
            disponibilidad = []

        codigos = {str(r.get("Codigo","")).strip().lower() for r in disponibilidad if r.get("Codigo")}
        codigos = {c for c in codigos if c}

        # ---------- complementos del catálogo ----------
        sugeridos = self._match_complementos(producto, codigos)

        # ---------- fallback si no hubo match ----------
        if not sugeridos:
            for s in self._suggest_by_rules(producto):
                sugeridos.append({
                    "complemento_nombre": s,
                    "complemento_codigo": "",
                    "tipo": "cross-sell",
                    "razon": "Sugerencia por tipo de producto"
                })

        return {"disponibilidad": disponibilidad, "sugeridos": sugeridos}
