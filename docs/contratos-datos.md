# Contratos de Datos — Dashboard Analítico (Alcance Simplificado)

Este repositorio no ejecuta ningún pipeline: consume un dataset ya construido y congelado en
`data/db_dashboard_course.db`. Este documento define, en el mismo estilo que
`DataScienceAplicado-Fundamentals/docs/contratos-datos.md`, el contrato mínimo que cualquier
código o rol (`roles/*.md`) que lea este dataset debe respetar, y documenta cómo fue producido
para que la validación sea re-ejecutable por un auditor externo.

## 1. Principios de Diseño

- **Contratos sobre Esquema:** el código del dashboard (Streamlit) depende de nombres de tabla y
  columna, tipos, y garantías de integridad referencial documentados aquí — no de la forma
  interna de `scripts/build_public_dataset.py`.
- **Reutilización, no reimplementación:** `tbl_leads` copia sin transformación las 22 columnas
  originales de la tabla pública ya validada de Módulo 4 (`tbl_Kmean_Iteracion_3vmi`), y agrega
  `Cluster`/`Probabilidad_Compra` ejecutando de nuevo el pipeline **real** de Módulo 4
  (`segmentar_clientes_kmeans` + `entrenar_evaluar_probabilidad`, importados desde
  `DataScienceAplicado-Fundamentals/src/models.py`, no reescritos aquí). Este repo no reentrena
  con otra lógica ni otros datos — corre el mismo K-Means y el mismo Random Forest ya
  contractados por pytest en Módulo 4, sobre la misma base pública fuente.
- **Anonimización verificable, no declarada:** cada tabla derivada de un diccionario privado pasa
  por un filtro de patrones PII antes de escribirse, y el resultado (0 rechazos) queda impreso en
  el log del script generador.

## 2. Matriz de Trazabilidad

| Objetivo de Negocio | Fuente | Tabla Pública | Contrato de Salida | Validación |
|---|---|---|---|---|
| Priorización de leads (fact table, reutilizada + 2 columnas computadas) | `tbl_Kmean_Iteracion_3vmi` (público, `db_casoInmobiliaria_DS_course.db`, Módulo 4) | `tbl_leads` | 622 filas × 24 columnas: las 22 originales copiadas 1:1 sin transformación, más `Cluster:int` y `Probabilidad_Compra:float [0,1]`, calculadas en tiempo de construcción del dataset re-ejecutando el pipeline real de Módulo 4 (no recomputadas con otra lógica, no reentrenadas con otros datos). Solo lectura — este repo nunca escribe en la tabla fuente. | Conteo de filas/columnas contra el origen para las 22 columnas originales; `Cluster`/`Probabilidad_Compra` generadas por `scripts/build_public_dataset.py::compute_ml_outputs()`, que importa y llama a `cargar_datos`, `ejecutar_limpieza_pipeline`, `imputar_estado_civil` (de `DataScienceAplicado-Fundamentals/src/data_processing.py`) y `segmentar_clientes_kmeans`, `entrenar_evaluar_probabilidad` (de `src/models.py`), en la misma secuencia que `main.py` de ese repo, y las mergea a `tbl_leads` por `IDPROSPECTO` en `copy_tbl_leads()`. Determinista: `random_state=42` fijo en cada paso. Verificado por re-corrida bit-a-bit idéntica (`git status --porcelain` vacío). |
| Catálogo de hobbies/intereses | `Diccionarios_Hobbies.xlsx` (privado, `sourcesbusinesscase/`, columna `ESTANDAR`) | `dim_hobby` | `hobby_id:int` (PK, surrogate, entero denso desde 1 sobre el conjunto ordenado de labels distintos), `hobby_estandar:str` (no nulo, deduplicado). 60 filas. **Universo de labels = unión** del diccionario (58 valores) **y** los valores reales distintos de `tbl_leads.Hobbies_Estandar` (2 valores adicionales: "Areas Sociales", "Otros", no presentes en el diccionario) — ver Decisión de Diseño abajo. | Escaneo de patrones PII sobre `ESTANDAR` (0 rechazos) + query de orfandad de la sección 3 (0 filas huérfanas). |
| Catálogo de categorías de comentarios | `Diccionario_ComentariosEstandarizado.xlsx` (privado, `sourcesbusinesscase/`, columna `Categoria`) | `dim_comentario` | `comentario_id:int` (PK, surrogate), `categoria_comentario:str` (no nulo, deduplicado). 14 filas. **Tabla de vocabulario independiente: no existe columna de unión hacia `tbl_leads`** (confirmado por inspección de valores contra todas las columnas de texto de la tabla de hechos, no solo por nombre de columna) — ver Decisión de Diseño abajo. | Escaneo de patrones PII sobre `Categoria` (0 rechazos). No aplica query de orfandad (no hay join). |

### Columnas excluidas explícitamente (fuente → allow-list)

| Fuente | Columna rechazada | Motivo |
|---|---|---|
| `Diccionarios_Hobbies.xlsx` | `cp13` | Código de fuente crudo, no forma parte del contrato público; falla el escaneo PII por ser casi-único fila a fila. |
| `Diccionario_ComentariosEstandarizado.xlsx` | `ComentarioStandarizado` | Texto libre casi-único (75/75 valores distintos): capturado por el umbral de near-unique del escaneo PII. |
| `Diccionario_ComentariosEstandarizado.xlsx` | `recodificar` | Baja cardinalidad pero solo 22/75 filas pobladas, semántica ambigua, no forma parte del contrato documentado en `spec.md`. |
| `Diccionario_ComentariosEstandarizado.xlsx` | `Tono` | No forma parte del contrato documentado en `spec.md` (columna `grupo` de `design.md` no fue implementada; ver discrepancia registrada en `apply-progress.md` Checkpoint 1). |

## 3. Query de Orfandad de `dim_hobby` (re-ejecutable)

Verifica que todo valor no nulo de `tbl_leads.Hobbies_Estandar` tenga una fila correspondiente en
`dim_hobby`. Debe devolver `0`. Esta es la misma query que corre dentro de
`scripts/build_public_dataset.py::verify_no_orphan_hobbies` al generar la base, y puede
re-ejecutarse en cualquier momento contra `data/db_dashboard_course.db`:

```sql
SELECT COUNT(*)
FROM tbl_leads t
LEFT JOIN dim_hobby h ON t."Hobbies_Estandar" = h.hobby_estandar
WHERE t."Hobbies_Estandar" IS NOT NULL AND h.hobby_id IS NULL;
-- Resultado esperado: 0
```

Vía shell (usando el CLI de `sqlite3`):

```bash
sqlite3 data/db_dashboard_course.db "SELECT COUNT(*) FROM tbl_leads t LEFT JOIN dim_hobby h ON t.\"Hobbies_Estandar\" = h.hobby_estandar WHERE t.\"Hobbies_Estandar\" IS NOT NULL AND h.hobby_id IS NULL;"
```

Resultado verificado en Checkpoint 1: **0 filas huérfanas**, tanto dentro del script (assert
interno) como en una corrida independiente contra la base ya generada.

## 4. Decisión de Diseño: universo de labels de `dim_hobby` (unión, no solo diccionario)

Una lectura literal de `design.md` ("Source: `Diccionarios_Hobbies.xlsx`") sugeriría que el
universo de labels de `dim_hobby` es exactamente el de la columna `ESTANDAR` del diccionario. La
inspección real (tarea 1.2) encontró que 38 de los 40 valores distintos de
`tbl_leads.Hobbies_Estandar` coinciden por valor con el diccionario (95% de solapamiento real, no
solo coincidencia de nombre de columna) — pero **2 valores existen en la tabla de hechos y no en
el diccionario**: `"Areas Sociales"` y `"Otros"` (confirmado por comparación de strings
normalizados, no es un problema de espacios/mayúsculas).

Para garantizar el requisito de "cero filas huérfanas" (`spec.md`, capability `dashboard-dataset`,
escenario "No source row identifier survives" combinado con el requisito de integridad de join;
`design.md`, Testing Strategy), `dim_hobby` se construye tomando la **unión** de los labels del
diccionario y los valores reales distintos de la tabla de hechos, en vez de proyectar el
diccionario solo. Esta es una desviación deliberada y documentada de la lectura literal de
`design.md`, necesaria para que la propia Testing Strategy de `design.md` se cumpla. Registrada en
el docstring/log de `scripts/build_public_dataset.py` y en `apply-progress.md` (Checkpoint 1,
sección "Deviations from Design", ítem 1).

## 5. Decisión de Diseño: `dim_comentario` es una tabla de vocabulario independiente

Se escaneó cada columna de texto de `tbl_Kmean_Iteracion_3vmi` contra cada columna de
`Diccionario_ComentariosEstandarizado.xlsx` buscando solapamiento a nivel de **valor** (no solo de
nombre de columna). No se encontró ninguna coincidencia. Esto confirma la decisión de diseño ya
prevista en `design.md` ("Gate resolved in Checkpoint 1"): `dim_comentario` no tiene clave de
unión hacia `tbl_leads` y se publica como tabla de vocabulario/taxonomía independiente (categorías
que la capa de análisis puede usar para definir segmentos de interés, sin join directo a nivel de
lead).

## 6. Disciplina de Anonimización

- **Claves surrogate, no identificadores de fuente:** `hobby_id` y `comentario_id` son enteros
  densos generados sobre el conjunto ordenado de labels distintos (`enumerate(sorted(labels),
  start=1)`), independientes del orden o contenido de las filas de origen. Ninguna clave es
  derivada de un índice de fila, ID de respondiente, ni timestamp de captura original.
- **Ningún identificador de fila de origen sobrevive:** las columnas `cp13` (código fuente de
  hobbies) y cualquier columna de texto libre casi-única fueron explícitamente excluidas del
  allow-list — ver sección 2.
- **Regla de rechazo por patrón PII** (`scripts/build_public_dataset.py::reject_reasons`),
  aplicada a toda columna candidata antes de escribirla en la tabla pública:
  - **Email:** `[^@\s]+@[^@\s]+\.[^@\s]+`
  - **Teléfono:** `\+?\d[\d\-\s]{6,}\d`
  - **Texto libre:** promedio de tokens por valor > 6 (distingue "oración de texto libre" de una
    etiqueta categórica corta que ocasionalmente tiene valores más largos).
  - **Casi-único fila a fila:** si hay más de 10 valores y la proporción de valores distintos sobre
    el total es > 0.9, se marca como dato crudo por fila, no como etiqueta categórica deduplicada.
  - Cualquier columna que dispare al menos una de estas reglas es excluida del allow-list y la
    razón queda impresa en el log del script (`print(...)` por columna evaluada) — nunca se omite
    silenciosamente.
- **Resultado verificado en Checkpoint 1:** ninguna columna candidata de ninguno de los dos
  diccionarios disparó el filtro PII sobre las columnas finalmente incluidas (`ESTANDAR`,
  `Categoria`); las columnas excluidas lo fueron por no estar en el contrato documentado o por
  fallar el chequeo de near-unique (ver sección 2), no porque el pipeline haya tenido que abortar
  por PII real encontrado.
