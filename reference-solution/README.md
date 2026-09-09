# ⚠️ Solución de referencia — spoiler

Este código existe para dos cosas:

1. **Probar que el `RUNBOOK.md` funciona de punta a punta** — se generó corriendo el protocolo
   completo con un Agent Code sin contexto previo del proyecto, simulando exactamente lo que
   haría un alumno. Arrancó Streamlit real, sirvió sin errores, y las tres filas de prueba dieron
   los mismos resultados en el código como en el dashboard.
2. **Destrabar a alguien que se quedó colgado**, o darle a un docente algo contra qué comparar.

**Si sos alumno haciendo el ejercicio por primera vez: no lo abras todavía.** Seguí
`../RUNBOOK.md` con tu propio Agent Code. Las decisiones de negocio que tomes vos (qué cluster
es de mayor conversión, dónde cortar Medio/Bajo, cómo etiquetar cada cluster) son justamente lo
que el ejercicio quiere que ejerciteches — mirar esto antes te las saltea.

## Cómo correrlo

Desde la raíz del repo (no desde acá adentro):

```bash
pip install -r requirements.txt
streamlit run reference-solution/app.py
```

## Qué decisiones de negocio tomó esta solución (documentadas también inline en cada archivo)

- `CLUSTER_ALTA_CONVERSION = 2` — el cluster con mayor `Probabilidad_Compra` promedio (0.581 vs
  0.185 y 0.156 de los otros dos), determinado perfilando los datos reales, no adivinado.
- `UMBRAL_ALTO = 0.70` — el ejemplo ilustrativo del spec, confirmado contra un hueco bimodal real
  en la distribución de `Probabilidad_Compra`.
- `UMBRAL_MEDIO = 0.30` — **inventado**, sin respaldo estadístico tan limpio como el de Alto. El
  spec no da ningún corte acá — esta es la decisión más discutible de toda la solución, y un buen
  ejercicio es que la cuestiones vos.
- Etiquetas de cluster (`interpretacion.py`) — perfiladas directo desde `tbl_leads` (edad, salario,
  interés de metraje), no desde el análisis de perfil real de Módulo 4, que vive en otro repo y
  este ejercicio no pide leer.

Ver el docstring de cada archivo para el detalle completo con los números reales.
