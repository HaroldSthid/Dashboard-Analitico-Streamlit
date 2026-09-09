# RUNBOOK — Cómo correr este ejercicio con tu Agent Code

Esta guía tiene dos partes. La primera es para vos, humano, con poco o ningún background en
Data Science — para que entiendas qué está pasando antes de delegarle nada a un agente. La
segunda es un protocolo que **le pegás directamente a tu Agent Code** (GitHub Copilot Chat,
Claude Code, Cursor, o el que uses) como primer mensaje en este repo, abierto en VS Code.

---

## Parte 1 — Para vos: qué es esto, en criollo

**El problema de negocio, en una frase:** una inmobiliaria tiene miles de personas interesadas
en comprar, y no todas valen lo mismo — hay que saber a quién llamar primero.

**Los conceptos que vas a ver, explicados simple:**

| Término | Qué significa acá |
|---|---|
| `Cluster` | Un número (0, 1 o 2) que agrupa a los prospectos parecidos entre sí — sueldo, edad, interés, etc. Ya está calculado, no lo tocás. |
| `Probabilidad_Compra` | Un número entre 0 y 1 que dice qué tan probable es que ESE prospecto compre. 0.90 = muy probable, 0.10 = poco probable. También ya está calculado. |
| `dim_hobby` / `dim_comentario` | Dos tablas chiquitas con categorías (hobbies, tipos de comentario) que le dan más contexto al dashboard — como un diccionario. |
| `tier_prioridad` | Esto NO existe todavía — es una regla de negocio que definís vos (o tu agente) en el Rol 2: "Alto / Medio / Bajo", combinando Cluster + Probabilidad_Compra. |
| Dashboard | La pantalla final donde un comercial ve la lista de prospectos ordenada por prioridad. Eso es lo que vas a construir. |

**¿Por qué 3 roles en vez de "hacé el dashboard" directo?** Porque así trabaja un equipo de
datos real: alguien prepara los datos (engineer), alguien define las reglas de negocio (analyst),
alguien interpreta los resultados para que un no-técnico los entienda (scientist). Cada uno tiene
su propio archivo en `roles/`. Vos (con tu agente) vas a **encarnar los tres, en orden**, y recién
al final construir la app.

**Lo importante — este repo ya tiene el dataset listo** (`data/db_dashboard_course.db`). El
trabajo del Rol 1 (limpiar y anonimizar los datos) **ya está hecho** — lo vas a leer para
entenderlo, no para repetirlo. El trabajo real que tu agente va a escribir en código empieza en
el Rol 2.

---

## Parte 2 — El protocolo para tu Agent Code

Copiá y pegá el bloque de abajo completo como tu primer mensaje al agente, en este repo abierto
en VS Code. No le pegues un solo prompt suelto tipo "hacé un dashboard" — este protocolo lo hace
avanzar paso a paso, con un checkpoint de validación antes de cada paso siguiente, para que no
se salte partes ni invente reglas de negocio que no están en los specs.

````
Vas a trabajar en este repo simulando, en secuencia, tres roles de un equipo de datos: data
engineer, data analyst, data scientist. No inventes reglas de negocio que no estén en los
archivos de spec — si algo no está definido, decime explícitamente qué falta antes de asumir.

PASO 0 — Contexto
Leé completos: EXERCISE.md, docs/contratos-datos.md, docs/negociacion.md.
Decime en 3-4 líneas qué entendiste del caso de negocio, sin copiar el texto.

PASO 1 — Rol Data Engineer (roles/01-data-engineer.md)
Leelo completo. Su trabajo (el dataset, el script de anonimización) YA ESTÁ HECHO — no lo
repitas. Confirmá inspeccionando data/db_dashboard_course.db directamente (abrí el archivo
con sqlite3 o pandas) que existen tbl_leads, dim_hobby, dim_comentario con las columnas que
el Handoff Contract de este rol describe. Mostrame el resultado real de esa inspección, no
lo que el spec dice que debería haber — quiero ver que lo comprobaste vos.

CHECKPOINT 1: no avances al paso 2 hasta confirmar que las 3 tablas existen con esas columnas.

PASO 2 — Rol Data Analyst (roles/02-data-analyst.md)
Leelo completo. Acá sí empezás a escribir código: implementá en un archivo nuevo
`logic_priorizacion.py` las reglas de negocio de este rol — la función que calcula
`tier_prioridad` (Alto/Medio/Bajo) y `orden_contacto`, exactamente como las describe la
sección "Owned Inputs/Outputs" del spec. Los umbrales de ejemplo del spec (0.70, etc.) son
ilustrativos — ajustalos si hace falta para que tengan sentido contra los datos reales de
tbl_leads, pero documentá qué umbral final usaste y por qué.

Corré esa función contra 3 filas reales de tbl_leads (elegí una con Cluster alto y probabilidad
alta, una media, una baja) y mostrame el resultado.

CHECKPOINT 2: no avances al paso 3 hasta mostrarme esos 3 resultados reales.

PASO 3 — Rol Data Scientist (roles/03-data-scientist.md)
Leelo completo. Implementá en el mismo archivo o en uno nuevo `interpretacion.py` las bandas
de interpretación de Cluster (etiqueta de negocio legible) y Probabilidad_Compra (banda de
confianza), consistentes con los umbrales que ya usaste en el paso 2 — no inventes un segundo
criterio que contradiga al del Rol 2 sin decirlo explícitamente. Anotá también la resolución
del desacuerdo (dim_comentario es catálogo, no feature) para que quede claro en el código o en
un comentario por qué esa tabla no se usa como columna unida.

CHECKPOINT 3: mostrame las etiquetas que le pusiste a cada Cluster (0, 1, 2) antes de seguir.

PASO 4 — Construir el dashboard
Ahora sí: construí app.py, una app Streamlit que:
- Lea data/db_dashboard_course.db directamente (no recalcules Cluster ni Probabilidad_Compra).
- Muestre la lista de leads ordenada por tier_prioridad y orden_contacto (paso 2).
- Muestre las etiquetas de interpretación de Cluster y las bandas de probabilidad (paso 3).
- Tenga un filtro por segmento de hobby (dim_hobby).
- Muestre dim_comentario como catálogo de referencia (no como columna unida a cada lead).
- Use Plotly para al menos un gráfico (ej. distribución de prioridad por cluster).
Agregá streamlit y plotly a requirements.txt si no están.

PASO 5 — Autovalidación
Corré `streamlit run app.py` vos mismo. Confirmame que arranca sin errores. Elegí los mismos 3
IDPROSPECTO que usaste en el Paso 2 y confirmá que en el dashboard aparecen con el tier que
calculaste ahí — si no coinciden, hay un bug, no lo ignores.

Al terminar, hacéme un resumen corto: qué decisiones de negocio tomaste vos (no el spec) —
esas son las que un data scientist real tendría que revisar.
````

---

## Qué NO va a hacer este protocolo por vos

No reemplaza tu criterio. El agente va a proponer umbrales, etiquetas y decisiones de diseño —
tu trabajo, como estudiante, es leer el Paso 2 y el Paso 3 con atención y preguntarte si esas
decisiones tienen sentido de negocio, no solo si el código corre. Ese es exactamente el punto de
todo este capítulo: la IA hace el trabajo pesado rápido, pero el criterio de negocio lo revisás
vos.
