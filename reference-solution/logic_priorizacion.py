"""
Rol 02 — Analista de Datos: lógica de priorización comercial.

Implementa las reglas de negocio descritas en `roles/02-data-analyst.md` (sección
"Owned Inputs/Outputs" y "Handoff Contract") sobre las columnas ya existentes en
`tbl_leads` (`Cluster`, `Probabilidad_Compra`). No recomputa ni reentrena nada del
modelo de Módulo 4 — solo aplica umbrales de negocio sobre su salida.

DECISIONES DE NEGOCIO TOMADAS POR EL ANALISTA (no dictadas por el spec, ver RUNBOOK.md
Paso 2 y el resumen final de decisiones):

1. Cluster de "mayor conversión histórica": el spec (`roles/02-data-analyst.md`) dice
   "el segmento de mayor conversión histórica (según el propio análisis de Módulo 4)"
   pero NO dice qué número de Cluster es ese — hay que inspeccionar los datos reales.
   Se inspeccionó `AVG(Probabilidad_Compra)` por Cluster sobre las 622 filas de
   tbl_leads:
       Cluster 0: avg=0.185 (29 filas)
       Cluster 1: avg=0.156 (250 filas)
       Cluster 2: avg=0.581 (343 filas)
   Cluster 2 es, por lejos, el de mayor probabilidad promedio de compra -> se define
   CLUSTER_ALTA_CONVERSION = 2. (La columna `Compra` NO es un flag binario de compra
   realizada -- son etiquetas de segmento de valor tipo "high value (DP)" -- así que no
   sirve como proxy directo de conversión; se usó Probabilidad_Compra, que es la señal
   de negocio ya validada por Módulo 4).

2. Umbral Alto (UMBRAL_ALTO = 0.70): el spec da 0.70 como "ejemplo ilustrativo" a
   ajustar contra los datos reales. Se graficó el histograma real de
   Probabilidad_Compra (bins de 0.1) y aparece una distribución bimodal clara con un
   hueco natural entre 0.6 y 0.7 (solo 2/622 filas caen en [0.6, 0.7) contra 93+81=174
   filas en [0.9, 1.0]). 0.70 cae justo en ese hueco natural, así que se mantiene el
   valor ilustrativo del spec porque los datos reales lo confirman -- no fue necesario
   ajustarlo.

3. Umbral Medio/Bajo (UMBRAL_MEDIO = 0.30): el spec NO da ningún umbral para separar
   Medio de Bajo dentro del "resto" (leads que no calificaron como Alto). Esta es una
   decisión de negocio inventada por el analista, no derivada de un spec: se eligió
   0.30 porque, dentro del grupo "resto" (438 leads), el 77% tiene Probabilidad_Compra
   < 0.20 y la cola superior (>= 0.30) representa un ~32% con probabilidad no
   despreciable de compra -- un corte razonable para separar "vale la pena una segunda
   pasada" de "prioridad baja", pero es un criterio de negocio, no un hueco estadístico
   tan nítido como el de Alto. DEBE ser revisado por un data scientist/analista real.

4. Empate (orden_contacto): el spec define un empate como diferencia de probabilidad
   < 0.01, y dice que en ese caso `hobby_estandar` se usa como "agrupador visual
   secundario", no como criterio de ranking numérico. Interpretación tomada aquí:
   `orden_contacto` es un entero de ranking (1 = primer contacto) basado
   exclusivamente en Probabilidad_Compra descendente (con IDPROSPECTO como
   desempate estable final, no de negocio, solo para que el orden sea determinista);
   el hobby NO se usa para reordenar numéricamente -- se expone aparte como
   `grupo_visual_hobby` para que la capa de presentación pueda agrupar/mostrar por
   hobby sin tocar el ranking. Esto es una interpretación mía de una instrucción
   ambigua del spec ("agrupador visual, no de ranking") que no especifica cómo
   una función debe materializar esa distinción.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Resuelto relativo a este archivo, no al cwd desde donde se corra streamlit/python
# (esta solución de referencia vive en reference-solution/, un nivel debajo de data/).
DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "db_dashboard_course.db")

# --- Umbrales de negocio (documentados arriba) ---
CLUSTER_ALTA_CONVERSION = 2
UMBRAL_ALTO = 0.70
UMBRAL_MEDIO = 0.30
TOLERANCIA_EMPATE = 0.01


@dataclass
class LeadPriorizado:
    idprospecto: int
    cluster: int
    probabilidad_compra: float
    hobby_estandar: str | None
    tier_prioridad: str
    orden_contacto: int


def tier_prioridad(cluster: int, probabilidad_compra: float) -> str:
    """Alto / Medio / Bajo según Cluster + Probabilidad_Compra.

    Regla del spec (roles/02-data-analyst.md):
    - Alto: cluster de mayor conversión histórica (Cluster == 2) Y
      Probabilidad_Compra >= UMBRAL_ALTO.
    - Resto: se distribuye entre Medio y Bajo únicamente según la probabilidad,
      sin importar el cluster.
    """
    if cluster == CLUSTER_ALTA_CONVERSION and probabilidad_compra >= UMBRAL_ALTO:
        return "Alto"
    if probabilidad_compra >= UMBRAL_MEDIO:
        return "Medio"
    return "Bajo"


def orden_contacto(leads: list[dict]) -> list[LeadPriorizado]:
    """Asigna un ranking de contacto (1 = primero) dentro de cada tier.

    Orden: Probabilidad_Compra descendente. Empates (diff < TOLERANCIA_EMPATE) se
    resuelven de forma estable por IDPROSPECTO ascendente (desempate técnico, no de
    negocio) -- el spec pide que el hobby sea "agrupador visual secundario" en el
    empate, no un criterio de reordenamiento numérico, así que no se usa acá para
    romper el empate del ranking.
    """
    tier_orden = {"Alto": 0, "Medio": 1, "Bajo": 2}
    enriquecidos = []
    for lead in leads:
        t = tier_prioridad(lead["Cluster"], lead["Probabilidad_Compra"])
        enriquecidos.append((t, lead))

    # Orden global: tier, luego probabilidad desc, luego IDPROSPECTO asc (estable)
    enriquecidos.sort(
        key=lambda tl: (
            tier_orden[tl[0]],
            -tl[1]["Probabilidad_Compra"],
            tl[1]["IDPROSPECTO"],
        )
    )

    resultado = []
    contador_por_tier = {"Alto": 0, "Medio": 0, "Bajo": 0}
    for t, lead in enriquecidos:
        contador_por_tier[t] += 1
        resultado.append(
            LeadPriorizado(
                idprospecto=lead["IDPROSPECTO"],
                cluster=lead["Cluster"],
                probabilidad_compra=lead["Probabilidad_Compra"],
                hobby_estandar=lead.get("Hobbies_Estandar"),
                tier_prioridad=t,
                orden_contacto=contador_por_tier[t],
            )
        )
    return resultado


def cargar_leads(db_path: str = DB_PATH) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT IDPROSPECTO, Cluster, Probabilidad_Compra, Hobbies_Estandar FROM tbl_leads;"
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def _demo():
    """Corre la función contra 3 filas reales: Cluster/probabilidad alta, media, baja."""
    leads = cargar_leads()
    by_id = {l["IDPROSPECTO"]: l for l in leads}

    # Elegidas por inspección real de la base (ver README de esta demo / RUNBOOK Paso 2):
    # alta: Cluster 2 con Probabilidad_Compra alta (>=0.70)
    # media: Probabilidad_Compra en [0.30, 0.70) o Cluster != 2 con prob alta
    # baja: Probabilidad_Compra < 0.30
    alto_id = next(
        l["IDPROSPECTO"]
        for l in leads
        if l["Cluster"] == 2 and l["Probabilidad_Compra"] >= 0.9
    )
    medio_id = next(
        l["IDPROSPECTO"]
        for l in leads
        if 0.30 <= l["Probabilidad_Compra"] < 0.70
    )
    bajo_id = next(
        l["IDPROSPECTO"] for l in leads if l["Probabilidad_Compra"] < 0.05
    )

    print("IDPROSPECTO elegidos para la demo:", alto_id, medio_id, bajo_id)

    ranked = orden_contacto(leads)
    ranked_by_id = {r.idprospecto: r for r in ranked}

    for label, idp in [("ALTO", alto_id), ("MEDIO", medio_id), ("BAJO", bajo_id)]:
        row = by_id[idp]
        r = ranked_by_id[idp]
        print(
            f"[{label}] IDPROSPECTO={idp} Cluster={row['Cluster']} "
            f"Probabilidad_Compra={row['Probabilidad_Compra']:.4f} "
            f"Hobbies_Estandar={row['Hobbies_Estandar']!r} "
            f"-> tier_prioridad={r.tier_prioridad} orden_contacto={r.orden_contacto}"
        )
    return alto_id, medio_id, bajo_id


if __name__ == "__main__":
    _demo()
