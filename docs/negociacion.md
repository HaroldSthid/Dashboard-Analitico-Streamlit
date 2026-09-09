# Negociación — El único punto de desacuerdo del equipo simulado

Este documento registra, tal como lo exige `spec.md` (capability `role-scoped-specs`,
requirement "One explicit disagreement point"), el **único** desacuerdo explícito entre roles
adyacentes de este ejercicio: entre el ingeniero de datos (`roles/01-data-engineer.md`) y el
científico de datos (`roles/03-data-scientist.md`). El analista de datos
(`roles/02-data-analyst.md`) es testigo del desacuerdo pero no parte directa — su lógica de
segmentación funciona igual con el estado actual de entrega.

## La pregunta abierta (levantada por el ingeniero de datos)

`roles/01-data-engineer.md` entrega `dim_hobby` y `dim_comentario` con las etiquetas
deduplicadas, tipadas y anonimizadas — considera esa transformación **terminada** en ese punto.
No todas las tablas de lookup entregadas tienen, sin embargo, una clave de unión estable hacia
`tbl_leads`: `dim_hobby` sí la tiene (`Hobbies_Estandar`, join verificado con 0 filas huérfanas);
`dim_comentario` no la tiene (confirmado por inspección de valores, no solo de nombre de
columna — ver `docs/contratos-datos.md` sección 5).

La pregunta que el ingeniero deja explícitamente abierta: **¿es aceptable, como estado final de
este ejercicio, que `dim_comentario` no tenga clave de unión? ¿O es una brecha que el analista o
el científico de datos deben resolver por otra vía (matching de texto libre, etiquetado manual)
si quieren usar comentarios como feature?**

## La posición del analista de datos

El analista (`roles/02-data-analyst.md`) opera sin problema con el estado actual: su uso
previsto de `dim_comentario` es como catálogo de referencia para definir segmentos manualmente,
no como columna unida fila a fila. Para su caso de uso, la falta de join no es un bloqueante —
pero reconoce que otro rol (el científico de datos) puede tener un requisito distinto y no
resuelve la pregunta por su cuenta.

## La posición del científico de datos (resuelve el desacuerdo)

El científico de datos (`roles/03-data-scientist.md`) sí requiere, como regla general, que toda
tabla de lookup usable como feature categórica de un futuro modelo tenga una clave de unión
estable y verificada. `dim_hobby` cumple ese requisito; `dim_comentario` no.

## Decisión final

Para esta iteración del ejercicio: `dim_comentario` **ships as vocabulary-only** — se usa
exclusivamente a nivel de presentación/catálogo (referencia textual, segmentación manual
definida por el analista), **nunca** como feature categórica directa de un modelo. Esto no es un
defecto no resuelto: es una decisión de alcance explícita, documentada aquí y en
`docs/contratos-datos.md` sección 5.

Si en el futuro reaparece una necesidad de negocio concreta que justifique una clave de unión
para `dim_comentario` (por ejemplo, vía matching de texto libre entre comentarios de
`tbl_leads` y las categorías del diccionario, o etiquetado manual adicional), esa construcción
queda **fuera de alcance** de este repositorio y del ejercicio actual — sería trabajo de una
futura iteración con su propio spec.

## Referencias cruzadas

- `roles/01-data-engineer.md` — sección "Handoff Contract" (levanta la pregunta).
- `roles/02-data-analyst.md` — sección "Business Rules & Invariants" (posición del analista).
- `roles/03-data-scientist.md` — sección "Business Rules & Invariants" (cierra el desacuerdo).
- `docs/contratos-datos.md` — sección 5, "Decisión de Diseño: `dim_comentario` es una tabla de
  vocabulario independiente" (evidencia técnica de por qué no existe join).
