"""
Dashboard Analítico — Streamlit (Paso 4 del RUNBOOK).

Lee `data/db_dashboard_course.db` directamente (no recalcula Cluster ni
Probabilidad_Compra -- ambos ya vienen del pipeline de Módulo 4, ver
`docs/contratos-datos.md`). Aplica sobre esa lectura la lógica de negocio de
`logic_priorizacion.py` (Rol 02) e `interpretacion.py` (Rol 03).

Requisitos del Paso 4 cubiertos:
- Lee la base directamente.                          -> cargar_leads() / cargar_dim_hobby()
- Lista ordenada por tier_prioridad + orden_contacto. -> orden_contacto()
- Etiquetas de Cluster + bandas de probabilidad.      -> interpretar_cluster() / banda_probabilidad()
- Filtro por segmento de hobby (dim_hobby).            -> selectbox de hobby_estandar
- dim_comentario como catálogo de referencia, sin join.-> tabla aparte, nunca merged a los leads
- Al menos un gráfico Plotly.                          -> distribución de tier por Cluster (barras)
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from interpretacion import banda_probabilidad, catalogo_categoria_comentario, interpretar_cluster
from logic_priorizacion import DB_PATH, cargar_leads, orden_contacto

st.set_page_config(page_title="Priorización de Leads", layout="wide")


@st.cache_data
def cargar_dim_hobby(db_path: str = DB_PATH) -> pd.DataFrame:
    import sqlite3

    con = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT hobby_id, hobby_estandar FROM dim_hobby ORDER BY hobby_estandar;", con)
    con.close()
    return df


@st.cache_data
def construir_tabla_priorizada() -> pd.DataFrame:
    leads = cargar_leads()
    ranked = orden_contacto(leads)
    df = pd.DataFrame(
        [
            {
                "IDPROSPECTO": r.idprospecto,
                "Cluster": r.cluster,
                "Interpretación de Cluster": interpretar_cluster(r.cluster),
                "Probabilidad_Compra": r.probabilidad_compra,
                "Banda de confianza": banda_probabilidad(r.probabilidad_compra),
                "Hobbies_Estandar": r.hobby_estandar,
                "tier_prioridad": r.tier_prioridad,
                "orden_contacto": r.orden_contacto,
            }
            for r in ranked
        ]
    )
    tier_order = pd.CategoricalDtype(categories=["Alto", "Medio", "Bajo"], ordered=True)
    df["tier_prioridad"] = df["tier_prioridad"].astype(tier_order)
    return df.sort_values(["tier_prioridad", "orden_contacto"]).reset_index(drop=True)


df_leads = construir_tabla_priorizada()

st.title("Dashboard de Priorización de Leads")
st.caption(
    "Cluster y Probabilidad_Compra provienen del pipeline de Módulo 4 (K-Means + Random Forest) "
    "ya calculado en data/db_dashboard_course.db -- este dashboard no reentrena ni recalcula "
    "nada, solo aplica la lógica de priorización del Rol 02 y la interpretación del Rol 03."
)

# --- Filtro por hobby (dim_hobby) ---
dim_hobby = cargar_dim_hobby()
hobbies_disponibles = ["(todos)"] + sorted(df_leads["Hobbies_Estandar"].dropna().unique().tolist())
hobby_sel = st.sidebar.selectbox("Filtrar por hobby (dim_hobby)", hobbies_disponibles)

st.sidebar.markdown(f"**Umbral Alto:** tier_prioridad usa Cluster 2 + Probabilidad_Compra ≥ 0.70")
st.sidebar.markdown(f"**Umbral Medio/Bajo:** Probabilidad_Compra ≥ 0.30")

df_filtrado = df_leads if hobby_sel == "(todos)" else df_leads[df_leads["Hobbies_Estandar"] == hobby_sel]

col1, col2, col3 = st.columns(3)
col1.metric("Leads totales", len(df_filtrado))
col2.metric("Tier Alto", int((df_filtrado["tier_prioridad"] == "Alto").sum()))
col3.metric("Tier Medio", int((df_filtrado["tier_prioridad"] == "Medio").sum()))

st.subheader("Leads priorizados (orden de contacto)")
st.dataframe(
    df_filtrado[
        [
            "orden_contacto",
            "tier_prioridad",
            "IDPROSPECTO",
            "Cluster",
            "Interpretación de Cluster",
            "Probabilidad_Compra",
            "Banda de confianza",
            "Hobbies_Estandar",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

# --- Gráfico Plotly: distribución de tier por Cluster ---
st.subheader("Distribución de prioridad por Cluster")
dist = (
    df_filtrado.groupby(["Cluster", "tier_prioridad"], observed=True)
    .size()
    .reset_index(name="cantidad")
)
dist["Cluster"] = dist["Cluster"].map(lambda c: f"Cluster {c} — {interpretar_cluster(c)}")
fig = px.bar(
    dist,
    x="Cluster",
    y="cantidad",
    color="tier_prioridad",
    category_orders={"tier_prioridad": ["Alto", "Medio", "Bajo"]},
    barmode="group",
    title="Cantidad de leads por Cluster y tier de prioridad",
)
st.plotly_chart(fig, use_container_width=True)

# --- dim_comentario: catálogo de referencia, SIN join a tbl_leads ---
st.subheader("Catálogo de categorías de comentario (dim_comentario)")
st.caption(
    "Tabla de vocabulario independiente -- NO tiene clave de unión hacia tbl_leads "
    "(ver docs/negociacion.md). Se muestra como catálogo de referencia, nunca como "
    "columna unida a cada lead."
)
st.dataframe(pd.DataFrame(catalogo_categoria_comentario()), use_container_width=True, hide_index=True)
