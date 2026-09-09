# EXERCISE.md — Convenciones de este Capítulo Extra

## Qué ES este repositorio

Un **paquete de especificaciones** para un ejercicio de simulación de roles: tres archivos
markdown en `roles/` (ingeniero de datos → analista de datos → científico de datos), un dataset
público anonimizado y congelado en `data/db_dashboard_course.db`, y sus contratos de datos
(`docs/contratos-datos.md`). El objetivo es que un agente de código, leyendo únicamente esos
specs y ese dataset, pueda construir un dashboard Streamlit + Plotly funcional desde cero.

## Qué NO es este repositorio

**No es un dashboard funcionando.** No hay `src/`, no hay `main.py`, no hay aplicación Streamlit
ejecutable en este repo. Construir el dashboard es responsabilidad de quien ejecute los specs
(el propio agente de código del alumno), no de este repositorio. Este repo termina en "specs +
datos + contratos", no en "app corriendo".

## Convenciones: Módulo 4 vs. este repositorio

`DataScienceAplicado-Fundamentals` (Módulo 4) es un pipeline productivo con disciplina estricta.
Este repositorio es, deliberadamente, un ejercicio de otra naturaleza: spec-first y
código-diferido. La siguiente tabla contrasta ambos conjuntos de convenciones para que no haya
ambigüedad sobre cuál aplica dónde.

| Dimensión | Módulo 4 (`DataScienceAplicado-Fundamentals`) | Este repositorio (`Dashboard-Analitico-Streamlit`) |
|---|---|---|
| **Rigor TDD** | Estricto: TDD rojo-verde-refactor obligatorio en cada iteración del pipeline analítico. | No aplica a nivel de repo: no hay código productivo que testear todavía. La sesión del agente de código del alumno decide su propia disciplina de testing al construir el dashboard. |
| **Tests de contrato** | Sí: suite `pytest` (`test_data_processing_contract`, `test_imputation_contract`, `test_kmeans_contract`, `test_random_forest_contract`) valida cada contrato de `docs/contratos-datos.md` automáticamente. | No: no existe código productivo aún, por lo que no hay tests de contrato ejecutables. `docs/contratos-datos.md` de este repo documenta contratos verificables (ver query SQL de orfandad), pero no está atado a una suite `pytest`. |
| **Layout de código fuente** | `src/` con pipeline modular (`data_processing.py`, `models.py`), `tests/`, `main.py` como punto de entrada. | Sin `src/`, sin `tests/`, sin `main.py`. Solo `roles/`, `data/`, `docs/`, `scripts/` (el script generador del dataset es auditable pero es una utilidad de una sola vez, no parte de un pipeline productivo). |
| **Expectativa de CI/CD** | No hay CI/CD configurado, pero el flujo de trabajo es disciplinado test-first: los tests corren localmente antes de cada commit como smoke test. | No hay CI/CD, y tampoco hay expectativa de smoke test local automatizado en este repo — la única verificación shippeada aquí es documental/manual (query SQL re-ejecutable, escaneo PII basado en `rg`). |

## Qué convención aplica al construir el dashboard

Cuando el agente de código del alumno lea `roles/*.md` y comience a escribir la aplicación
Streamlit, **puede** optar por adoptar la disciplina estricta de Módulo 4 (TDD, tests de
contrato) si lo considera apropiado para ese código nuevo — pero no está obligado a hacerlo por
convención heredada de este repositorio. Cada uno de los tres archivos en `roles/` restablece
esta misma regla en su sección "Scope Boundaries / Non-Goals".
