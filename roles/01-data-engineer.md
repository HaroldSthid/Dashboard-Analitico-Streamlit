# Rol 01 — Ingeniero de Datos

## Convenciones

Este archivo asume las convenciones descritas en `EXERCISE.md`: este repositorio es
spec-first / código-diferido. Léelo antes de ejecutar este spec.

## Business Problem

El negocio necesita priorizar leads inmobiliarios comerciales: dado un universo de prospectos
ya scoreado por Módulo 4 (`DataScienceAplicado-Fundamentals`, tabla pública
`tbl_Kmean_Iteracion_3vmi` con `Cluster` y `Probabilidad_Compra`), un comercial necesita un
dashboard que le diga, de forma priorizada, a quién contactar primero. Ese scoring ya existe y
no debe recomputarse aquí (ver `docs/contratos-datos.md`, principio "Reutilización, no
recomputación"). Lo que falta para que el dashboard tenga valor de segmentación adicional son
dos diccionarios de negocio — hobbies/intereses y categorías de comentarios estandarizados —
que hoy viven como archivos Excel privados (`sourcesbusinesscase/*.xlsx`, ignorados por git) y
no como tablas públicas consultables. El rol del ingeniero de datos es exactamente ese: convertir
esos dos diccionarios privados en tablas de lookup públicas, anonimizadas y con un contrato de
esquema documentado, sin tocar el modelo de negocio (Cluster, Probabilidad_Compra) ya resuelto
por Módulo 4.

## Owned Inputs/Outputs

**Owned Inputs** (solo a nivel de esquema/columna — nunca valores de fila):

- `sourcesbusinesscase/Diccionarios_Hobbies.xlsx` — hoja `Hoja1`, 433 filas × 2 columnas:
  `cp13` (str, código de fuente crudo — descartado, ver Business Rules) y `ESTANDAR` (str,
  etiqueta de hobby estandarizada — única columna admitida).
- `sourcesbusinesscase/Diccionario_ComentariosEstandarizado.xlsx` — hoja `Hoja1`, 75 filas × 4
  columnas: `recodificar` (str, baja cobertura), `ComentarioStandarizado` (str, texto libre
  casi-único), `Categoria` (str, etiqueta estandarizada — única columna admitida), `Tono` (str,
  fuera del contrato documentado). Ver `docs/contratos-datos.md` sección 2, tabla "Columnas
  excluidas explícitamente" para el detalle de por qué cada columna descartada fue rechazada.
- `tbl_leads` (pública, ya existente, reutilizada de `tbl_Kmean_Iteracion_3vmi` en
  `db_casoInmobiliaria_DS_course.db`) — solo lectura, para calcular la unión de labels de
  `dim_hobby` y verificar orfandad; el ingeniero no la modifica.

**Owned Outputs**:

- `dim_hobby` (`hobby_id:int` PK surrogate, `hobby_estandar:str` no nulo deduplicado — 60 filas,
  universo = unión diccionario + valores reales de `tbl_leads.Hobbies_Estandar`).
- `dim_comentario` (`comentario_id:int` PK surrogate, `categoria_comentario:str` no nulo
  deduplicado — 14 filas, tabla de vocabulario independiente, sin join hacia `tbl_leads`).
- `data/db_dashboard_course.db` — la base SQLite que contiene ambas tablas de lookup más la
  copia de solo lectura de `tbl_leads`.
- `scripts/build_public_dataset.py` — el script generador, committeado (auditable), que produce
  los tres artefactos anteriores de forma determinista y re-ejecutable.

## Business Rules & Invariants

1. Ninguna columna que contenga nombre, teléfono, email, número de documento o texto libre de
   comentario puede sobrevivir a la proyección pública (regla de negocio, no solo técnica: el
   dato es de terceros y su re-identificación no está autorizada para este ejercicio).
2. Las claves primarias (`hobby_id`, `comentario_id`) deben ser enteros surrogate generados
   sobre el conjunto ordenado de labels distintos — nunca derivados de un índice de fila o ID de
   fuente original (garantiza que la clave no filtra identidad de origen).
3. `dim_hobby` debe garantizar cero filas huérfanas contra `tbl_leads.Hobbies_Estandar`: por eso
   su universo de labels es la unión diccionario + valores reales de la tabla de hechos, no el
   diccionario solo (desviación documentada, ver `docs/contratos-datos.md` sección 4).
4. `dim_comentario` no debe inventar una clave de unión que no existe: se comprobó, por valor,
   que ninguna columna de texto de `tbl_leads` coincide con `Categoria`; por eso se publica como
   tabla de vocabulario/taxonomía independiente, no como dimensión unida.
5. Toda columna rechazada del allow-list debe quedar registrada con su motivo en el log del
   script generador — el rechazo nunca es silencioso.

## Handoff Contract

El ingeniero de datos entrega al siguiente rol (analista de datos) exactamente estas tres
tablas, ya materializadas en `data/db_dashboard_course.db`:

- `tbl_leads` — copia de solo lectura de `tbl_Kmean_Iteracion_3vmi` (622 filas × 22 columnas,
  incluye `Cluster:int`, `Probabilidad_Compra:float [0,1]`, `Hobbies_Estandar:str`).
- `dim_hobby` — `hobby_id:int` PK, `hobby_estandar:str`; join documentado:
  `tbl_leads.Hobbies_Estandar = dim_hobby.hobby_estandar` (0 huérfanos, query re-ejecutable en
  `docs/contratos-datos.md` sección 3).
- `dim_comentario` — `comentario_id:int` PK, `categoria_comentario:str`; **sin join** hacia
  `tbl_leads` (tabla de vocabulario independiente, usable por el analista para definir
  segmentos de interés por categoría de comentario sin unión fila a fila).

**Punto de desacuerdo abierto (no resuelto aquí):** el ingeniero de datos considera esta
transformación "terminada" (`done`) una vez que las etiquetas están deduplicadas y tipadas
correctamente — que es exactamente lo entregado arriba. El científico de datos, sin embargo,
puede requerir que toda tabla de lookup entregada tenga además una clave de unión estable
utilizable como feature categórica de modelo. `dim_hobby` cumple esa condición (tiene
`Hobbies_Estandar` como clave de unión real); `dim_comentario` **no** la tiene — es
intencionalmente vocabulario-only. Este spec deja esa brecha **abierta**, no resuelta: ver
`docs/negociacion.md` para el registro completo del desacuerdo y su resolución final por parte
del científico de datos.

## Scope Boundaries / Non-Goals

Este repositorio es spec-first / código-diferido: la disciplina estricta de TDD y tests de
contrato de Módulo 4 (`DataScienceAplicado-Fundamentals`) no aplica aquí, salvo que la propia
sesión del agente de código del alumno decida adoptarla al construir el dashboard. El ingeniero
de datos de este rol **no construye el dashboard Streamlit** — su alcance termina en la entrega
de `data/db_dashboard_course.db` y su contrato documentado; el dashboard es responsabilidad de
los roles 02/03 y, en última instancia, del agente de código que ejecute estos specs.

## Acceptance Evidence

- Las seis secciones requeridas (Business Problem, Owned Inputs/Outputs, Business Rules &
  Invariants, Handoff Contract, Scope Boundaries / Non-Goals, Acceptance Evidence) están
  presentes, no vacías y en el orden exigido por `spec.md` (capability `role-scoped-specs`).
- El Handoff Contract nombra exactamente `tbl_leads`, `dim_hobby`, `dim_comentario` — mismos
  nombres usados en `docs/contratos-datos.md` y en `roles/02-data-analyst.md` (Owned Inputs).
- El punto de desacuerdo queda explícitamente abierto (no resuelto de forma silenciosa) y
  cross-linkeado a `docs/negociacion.md`.
- **Escaneo PII ejecutado el 9 de septiembre de 2026**: `rg -i -f pii-patterns.txt roles/01-data-engineer.md
  roles/02-data-analyst.md roles/03-data-scientist.md` → **0 coincidencias** en los tres
  archivos de rol (ver `pii-patterns.txt`).
