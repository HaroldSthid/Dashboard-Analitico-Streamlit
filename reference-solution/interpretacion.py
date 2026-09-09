"""
Rol 03 — Científico de Datos: guía de interpretación para la superficie de decisión.

Implementa las bandas de interpretación de `Cluster` y `Probabilidad_Compra` descritas en
`roles/03-data-scientist.md`, consistentes con los umbrales ya fijados por el analista en
`logic_priorizacion.py` (regla explícita del rol 03: "no se introduce un segundo criterio
de corte que contradiga al del analista sin justificarlo").

DECISIONES DE NEGOCIO TOMADAS POR EL "CIENTÍFICO DE DATOS" (no dictadas por el spec):

1. Etiquetas de Cluster: el spec da un ejemplo ilustrativo ("Cluster 2 -> Alto interés, alta
   capacidad de compra") pero aclara que "la etiqueta real depende del análisis de perfil de
   cada cluster ya hecho en Módulo 4" -- ese análisis de perfil NO está en este repositorio
   (Módulo 4 vive en otro repo, `DataScienceAplicado-Fundamentals`, y no se leyó acá porque el
   RUNBOOK solo pide leer los archivos de este repo). Ante esa laguna, se perfiló cada Cluster
   directamente contra `tbl_leads` (promedios de Probabilidad_Compra, Edad, Salario_MarcaClase,
   InteresMetraje_MarcaClase):

       Cluster | n   | avg_prob | avg_edad | avg_salario_clase | avg_metraje_clase
       0       | 29  | 0.185    | 49.3     | 3,008,621          | 51.4
       1       | 250 | 0.156    | 63.4     | 2,412,000          | 56.4
       2       | 343 | 0.581    | 47.7     | 2,317,055          | 39.2

   A partir de ese perfil (NO de un análisis de negocio validado por Módulo 4, que este repo no
   tiene) se asignaron las siguientes etiquetas -- deben ser revisadas por quien sí tenga el
   análisis de perfil real de Módulo 4:

     - Cluster 0 -> "Salario alto, conversión baja" (mejor salario declarado del dataset pero
       probabilidad de compra baja; volumen chico, 29 filas).
     - Cluster 1 -> "Maduro, baja urgencia de compra" (edad promedio más alta, mayor interés en
       metraje declarado, pero la probabilidad de compra más baja de los tres clusters).
     - Cluster 2 -> "Alto interés, alta probabilidad de compra" (perfil más joven, la mayoría del
       dataset -- 343/622 filas -- y la única cluster con probabilidad promedio > 0.5; coincide
       con `CLUSTER_ALTA_CONVERSION` usado en `logic_priorizacion.py`).

2. Bandas de Probabilidad_Compra: se reutilizan EXACTAMENTE los mismos cortes que
   `logic_priorizacion.py` (UMBRAL_ALTO=0.70, UMBRAL_MEDIO=0.30) para que la etiqueta que ve el
   comercial nunca contradiga el tier_prioridad ya calculado -- ver Business Rule 3 del rol 03.
   No se inventa un tercer corte.

3. Resolución del desacuerdo dim_comentario (ya cerrada en `docs/negociacion.md` y
   `roles/03-data-scientist.md`): se usa acá y en app.py exclusivamente como catálogo de
   referencia (sin join a tbl_leads), nunca como columna unida a cada lead. Ver
   `catalogo_categoria_comentario()` más abajo.
"""

from __future__ import annotations

import sqlite3

from logic_priorizacion import DB_PATH, UMBRAL_ALTO, UMBRAL_MEDIO

# Etiquetas de negocio por Cluster (decisión del "científico de datos", ver docstring arriba).
CLUSTER_LABELS: dict[int, str] = {
    0: "Salario alto, conversión baja",
    1: "Maduro, baja urgencia de compra",
    2: "Alto interés, alta probabilidad de compra",
}

CLUSTER_DESCRIPTIONS: dict[int, str] = {
    0: (
        "Segmento pequeño (29 leads) con el salario declarado más alto del dataset, pero "
        "probabilidad de compra baja (~18% promedio). No priorizar por volumen."
    ),
    1: (
        "Segmento más grande en número (250 leads) pero con la probabilidad de compra más "
        "baja de los tres (~16% promedio) y la edad promedio más alta (~63 años)."
    ),
    2: (
        "Segmento mayoritario (343 leads) y el único con probabilidad de compra promedio "
        "superior a 0.5 (~58%). Corresponde al Cluster de mayor conversión histórica usado "
        "por el analista para el tier 'Alto'."
    ),
}


def interpretar_cluster(cluster: int) -> str:
    """Etiqueta de negocio legible para un Cluster. Nunca inventa clusters fuera de {0,1,2}."""
    return CLUSTER_LABELS.get(cluster, f"Cluster {cluster} (sin perfil documentado)")


def banda_probabilidad(probabilidad_compra: float) -> str:
    """Banda de confianza para Probabilidad_Compra, MISMOS umbrales que tier_prioridad."""
    if probabilidad_compra >= UMBRAL_ALTO:
        return f"Alta (>= {UMBRAL_ALTO:.2f})"
    if probabilidad_compra >= UMBRAL_MEDIO:
        return f"Media ({UMBRAL_MEDIO:.2f}-{UMBRAL_ALTO:.2f})"
    return f"Baja (< {UMBRAL_MEDIO:.2f})"


def catalogo_categoria_comentario(db_path: str = DB_PATH) -> list[dict]:
    """dim_comentario como catálogo de referencia -- SIN join a tbl_leads (decisión cerrada
    en docs/negociacion.md: dim_comentario ships as vocabulary-only)."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT comentario_id, categoria_comentario FROM dim_comentario ORDER BY comentario_id;")
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def _demo():
    print("Etiquetas de Cluster (Checkpoint 3):")
    for c in (0, 1, 2):
        print(f"  Cluster {c} -> {interpretar_cluster(c)}")
        print(f"    {CLUSTER_DESCRIPTIONS[c]}")

    print("\nBandas de Probabilidad_Compra (mismos umbrales que tier_prioridad):")
    for p in (0.95, 0.5, 0.1):
        print(f"  Probabilidad_Compra={p} -> {banda_probabilidad(p)}")

    print(f"\ncatalogo_categoria_comentario(): {len(catalogo_categoria_comentario())} categorías")


if __name__ == "__main__":
    _demo()
