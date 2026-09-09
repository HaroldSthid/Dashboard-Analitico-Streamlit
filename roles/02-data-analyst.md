# Rol 02 — Analista de Datos

## Convenciones

Este archivo asume las convenciones descritas en `EXERCISE.md`: este repositorio es
spec-first / código-diferido. Léelo antes de ejecutar este spec.

## Business Problem

El comercial que consume el dashboard final no quiere ver 622 leads sin orden: quiere saber, en
una sola mirada, a quién llamar hoy. El analista de datos traduce el dataset entregado por el
ingeniero (cluster, probabilidad de compra, hobby estandarizado) en una **lógica de
priorización comercial** explícita: qué combinación de señales define "lead prioritario",
cómo se rompen los empates, y qué segmentos por interés (hobby) tienen sentido de negocio para
el comercial. El resultado de este rol no es código — es la definición de negocio que el
científico de datos (rol 03) y, después, el agente de código que construya el dashboard,
deben respetar sin reinterpretar.

## Owned Inputs/Outputs

**Owned Inputs** (deben coincidir por nombre exacto con el Handoff Contract de
`roles/01-data-engineer.md`):

- `tbl_leads` — copia de solo lectura de `tbl_Kmean_Iteracion_3vmi` (622 filas × 22 columnas,
  incluye `Cluster:int`, `Probabilidad_Compra:float [0,1]`, `Hobbies_Estandar:str`).
- `dim_hobby` — `hobby_id:int` PK, `hobby_estandar:str`; join:
  `tbl_leads.Hobbies_Estandar = dim_hobby.hobby_estandar` (0 huérfanos).
- `dim_comentario` — `comentario_id:int` PK, `categoria_comentario:str`; sin join hacia
  `tbl_leads` (vocabulario independiente).

Sin inputs adicionales no documentados — el analista no vuelve a tocar los archivos privados
`sourcesbusinesscase/*.xlsx`; su universo de trabajo es exactamente lo que el ingeniero publicó
en `data/db_dashboard_course.db`.

**Owned Outputs** (reglas de negocio, no código — la implementación en Python/SQL queda para
quien construya el dashboard):

- **Criterio de priorización**: cada lead recibe un **tier de prioridad** (Alto / Medio / Bajo)
  derivado de `Cluster` y `Probabilidad_Compra`: los leads cuyo `Cluster` corresponde al
  segmento de mayor conversión histórica (según el propio análisis de Módulo 4) **y** cuya
  `Probabilidad_Compra` supera un umbral de negocio (ej. ≥ 0.70, ejemplo ilustrativo — el valor
  final lo fija el analista al construir el dashboard con el dataset real) se clasifican como
  Alto. El resto se distribuye entre Medio y Bajo según la misma probabilidad, sin importar el
  cluster.
- **Criterio de desempate**: dentro del mismo tier, el orden de contacto lo define
  `Probabilidad_Compra` descendente; si dos leads empatan en probabilidad (con una tolerancia de
  negocio, ej. diferencia < 0.01), el segmento de `hobby_estandar` (vía `dim_hobby`) se usa como
  criterio secundario de agrupación visual (no de ranking numérico) para que el comercial pueda
  ofrecer un discurso comercial más afín al interés del lead.
- **Segmentación por interés**: `dim_hobby` alimenta un filtro/segmento visual del dashboard
  (ej. "leads interesados en X" ordenados por su tier de prioridad). `dim_comentario`, al no
  tener join, se ofrece como catálogo de referencia para que el analista (o quien construya el
  dashboard) pueda, si lo desea, definir manualmente segmentos por categoría de comentario —
  sin garantía de cobertura fila a fila, ya que no hay clave de unión.

## Business Rules & Invariants

1. Todo lead con `Probabilidad_Compra` no nula debe recibir un tier de prioridad definido — no
   se permite un lead "sin clasificar" en el dashboard final.
2. El tier de prioridad se calcula únicamente a partir de columnas ya existentes en `tbl_leads`
   (`Cluster`, `Probabilidad_Compra`); el analista no recomputa ni reentrena el modelo — solo
   define umbrales de negocio sobre la salida ya existente (mismo principio de "reutilización,
   no recomputación" de `docs/contratos-datos.md`).
3. Los segmentos por `hobby_estandar` se construyen exclusivamente vía el join documentado
   `tbl_leads.Hobbies_Estandar = dim_hobby.hobby_estandar` — nunca por coincidencia de texto
   libre o normalización ad hoc fuera de ese contrato.
4. `dim_comentario` no puede usarse como si tuviera join row-level: cualquier uso de esta tabla
   en el dashboard debe presentarse como catálogo de referencia, no como columna adicional por
   lead — esto es intencional, no un bug.

**Punto de desacuerdo (se levanta explícitamente aquí):** el rol 01 (ingeniero de datos) entrega
`dim_hobby` y `dim_comentario` con las etiquetas deduplicadas y tipadas — y considera eso
"terminado". Este analista, para la lógica de segmentación arriba descrita, puede operar
perfectamente con ese nivel de entrega: no necesita una clave de unión adicional para
`dim_comentario`, porque su uso previsto es de catálogo de referencia, no de feature por fila.
Sin embargo, el rol 03 (científico de datos) puede requerir más — ver `docs/negociacion.md`
para el registro completo de este desacuerdo entre 01 y 03, del cual este analista es testigo
pero no parte directa.

## Handoff Contract

El analista de datos entrega al científico de datos (rol 03) exactamente estos criterios de
priorización, como reglas de negocio documentadas (no como código):

- **`tier_prioridad`** (Alto/Medio/Bajo) — derivado de `Cluster` + `Probabilidad_Compra` según
  las reglas de la sección "Owned Inputs/Outputs" arriba.
- **`orden_contacto`** — criterio de desempate: `Probabilidad_Compra` descendente, con
  `hobby_estandar` (vía `dim_hobby`) como agrupador secundario visual.
- **`catalogo_categoria_comentario`** — uso previsto de `dim_comentario` como catálogo de
  referencia sin join row-level, no como feature de modelo.
- Todas las tablas fuente (`tbl_leads`, `dim_hobby`, `dim_comentario`) se reenvían sin cambios
  de esquema — el analista no crea nuevas tablas físicas, solo define lógica de negocio sobre
  las existentes.

## Scope Boundaries / Non-Goals

Este repositorio es spec-first / código-diferido: la disciplina estricta de TDD y tests de
contrato de Módulo 4 (`DataScienceAplicado-Fundamentals`) no aplica aquí, salvo que la propia
sesión del agente de código del alumno decida adoptarla al construir el dashboard. El analista
de datos de este rol **no construye el dashboard Streamlit ni escribe el código de scoring** —
define únicamente la lógica de negocio de priorización; la implementación queda para el agente
de código que ejecute estos specs.

## Acceptance Evidence

- Las seis secciones requeridas (Business Problem, Owned Inputs/Outputs, Business Rules &
  Invariants, Handoff Contract, Scope Boundaries / Non-Goals, Acceptance Evidence) están
  presentes, no vacías y en el orden exigido por `spec.md` (capability `role-scoped-specs`).
- Owned Inputs coincide exactamente por nombre con el Handoff Contract de
  `roles/01-data-engineer.md` (`tbl_leads`, `dim_hobby`, `dim_comentario`), sin inputs
  adicionales no documentados.
- El punto de desacuerdo se levanta explícitamente (no se resuelve aquí) y queda cross-linkeado
  a `docs/negociacion.md`.
- **Escaneo PII ejecutado el 9 de septiembre de 2026**: `rg -i -f pii-patterns.txt roles/01-data-engineer.md
  roles/02-data-analyst.md roles/03-data-scientist.md` → **0 coincidencias** en los tres
  archivos de rol (ver `pii-patterns.txt`).
