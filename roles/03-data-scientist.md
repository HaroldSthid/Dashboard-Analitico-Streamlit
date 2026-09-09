# Rol 03 — Científico de Datos

## Convenciones

Este archivo asume las convenciones descritas en `EXERCISE.md`: este repositorio es
spec-first / código-diferido. Léelo antes de ejecutar este spec.

## Business Problem

El dashboard final es la superficie de decisión del comercial: ahí es donde `Cluster` y
`Probabilidad_Compra` — ya producidos por el pipeline de Módulo 4 (K-Means + Random Forest,
`DataScienceAplicado-Fundamentals`) — dejan de ser artefactos de modelo y se convierten en una
recomendación accionable. El rol del científico de datos en este ejercicio no es reentrenar
nada: es **interpretar** esas dos columnas para el comercial (qué significa cada cluster en
términos de negocio, qué tan confiable es la probabilidad como criterio de decisión) y cerrar,
con una posición técnica explícita, el desacuerdo que el analista dejó abierto sobre qué
lookup tables son aptas como features de modelo futuras.

## Owned Inputs/Outputs

**Owned Inputs** (deben coincidir por nombre exacto con el Handoff Contract de
`roles/02-data-analyst.md`):

- **`tier_prioridad`** (Alto/Medio/Bajo) — regla de negocio del analista sobre
  `Cluster` + `Probabilidad_Compra`.
- **`orden_contacto`** — criterio de desempate (probabilidad descendente + agrupación por
  `hobby_estandar`).
- **`catalogo_categoria_comentario`** — uso de `dim_comentario` como catálogo de referencia,
  sin join row-level.
- Las tres tablas fuente reenviadas sin cambio de esquema: `tbl_leads`, `dim_hobby`,
  `dim_comentario`.

**Owned Outputs** (guía de interpretación para la superficie de decisión del dashboard — reglas
de negocio/interpretativas, no código; el Streamlit/Plotly real queda fuera de alcance por
`EXERCISE.md`):

- **Interpretación de `Cluster`**: cada valor entero de `Cluster` debe mostrarse en el dashboard
  con una etiqueta de negocio legible (ej. "Cluster 2 → Alto interés, alta capacidad de compra",
  ejemplo ilustrativo — la etiqueta real depende del análisis de perfil de cada cluster ya hecho
  en Módulo 4), nunca como un número desnudo sin contexto para el comercial.
- **Interpretación de `Probabilidad_Compra`**: debe presentarse como una banda de confianza
  (ej. "Alta: ≥0.70, Media: 0.40–0.69, Baja: <0.40" — ejemplo ilustrativo, mismos umbrales que
  el analista puede usar para `tier_prioridad`, no un nuevo criterio paralelo), no como un
  decimal aislado — el comercial debe poder leerla sin conocimiento estadístico previo.
- **Resolución del desacuerdo** (ver Handoff Contract abajo): posición final del científico de
  datos sobre qué lookup tables son aptas como features de modelo.

## Business Rules & Invariants

1. El científico de datos no reentrena ni recalibra `Cluster`/`Probabilidad_Compra` — solo
   define cómo se interpretan y presentan (mismo principio de "reutilización, no recomputación"
   que rige todo el repositorio).
2. Toda etiqueta de interpretación de cluster debe ser trazable a un cluster real de
   `tbl_leads.Cluster` — no se inventan clusters ni rangos de probabilidad fuera de los valores
   observados en el dataset entregado.
3. La interpretación de `Probabilidad_Compra` debe ser consistente con los umbrales que el
   analista (rol 02) ya usó para `tier_prioridad` — no se introduce un segundo criterio de corte
   que contradiga al del analista sin justificarlo explícitamente.

**Punto de desacuerdo (se cierra aquí):** el ingeniero de datos (rol 01) considera su
transformación "terminada" con etiquetas deduplicadas y tipadas — sin exigir una clave de unión
estable en todas las tablas de lookup. Este científico de datos, en cambio, **requiere** que
toda tabla de lookup usable como feature categórica de un futuro modelo tenga una clave de
unión estable y verificada contra la tabla de hechos. `dim_hobby` cumple ese requisito
(`Hobbies_Estandar` es un join real, verificado con 0 filas huérfanas). `dim_comentario`
**no** lo cumple — es, por diseño, una tabla de vocabulario sin join.

**Resolución final** (registrada también en `docs/negociacion.md`): para esta iteración del
ejercicio, esa brecha se acepta como estado final, no como bloqueante. `dim_comentario` se
usa exclusivamente a nivel de presentación/catálogo (ej. como referencia textual o para
segmentación manual definida por el analista), **nunca** como feature categórica directa de un
modelo, hasta que exista una necesidad de negocio concreta que justifique construir una clave
de unión (por ejemplo, vía matching de texto libre o etiquetado manual adicional sobre
`tbl_leads`, ambos fuera de alcance de este ejercicio). Si esa necesidad reaparece, es trabajo
futuro explícitamente fuera del alcance de este repositorio.

## Handoff Contract

El científico de datos no entrega a un cuarto rol (la cadena termina en 03), pero su salida es
la que consume directamente el agente de código que construya el dashboard:

- Las bandas de interpretación de `Cluster` y `Probabilidad_Compra` (sección "Owned
  Inputs/Outputs" arriba) — para renderizar la superficie de decisión del comercial.
- La resolución final del desacuerdo: `dim_hobby` es apta como feature categórica (tiene join
  verificado); `dim_comentario` **no** lo es en esta iteración — se restringe a uso de
  presentación/catálogo. Ver `docs/negociacion.md` para el registro completo.

## Scope Boundaries / Non-Goals

Este repositorio es spec-first / código-diferido: la disciplina estricta de TDD y tests de
contrato de Módulo 4 (`DataScienceAplicado-Fundamentals`) no aplica aquí, salvo que la propia
sesión del agente de código del alumno decida adoptarla al construir el dashboard. El científico
de datos de este rol **no construye el dashboard Streamlit ni reentrena el modelo K-Means /
Random Forest** — su alcance es la guía de interpretación y el cierre del desacuerdo de
lookup-tables; la implementación del dashboard queda para el agente de código que ejecute estos
specs.

## Acceptance Evidence

- Las seis secciones requeridas (Business Problem, Owned Inputs/Outputs, Business Rules &
  Invariants, Handoff Contract, Scope Boundaries / Non-Goals, Acceptance Evidence) están
  presentes, no vacías y en el orden exigido por `spec.md` (capability `role-scoped-specs`).
- Owned Inputs coincide exactamente por nombre con el Handoff Contract de
  `roles/02-data-analyst.md` (`tier_prioridad`, `orden_contacto`,
  `catalogo_categoria_comentario`, más las tres tablas fuente).
- El desacuerdo levantado en `roles/01-data-engineer.md` queda cerrado explícitamente aquí (no
  silenciosamente), con la posición del científico de datos y la resolución final, ambas
  también registradas en `docs/negociacion.md`.
- **Escaneo PII ejecutado el 9 de septiembre de 2026**: `rg -i -f pii-patterns.txt roles/01-data-engineer.md
  roles/02-data-analyst.md roles/03-data-scientist.md` → **0 coincidencias** en los tres
  archivos de rol (ver `pii-patterns.txt`).
