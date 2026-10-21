# Cómo aportar

Gracias por sumarte. Todo aporte sirve: avisar que algo no funciona, agregar un broker, corregir un criterio o mejorar la guía de descarga.

## ⚠️ Nunca subas datos personales

Este repo es público. **No subas extractos reales, `events.csv`, informes, capturas de tu cuenta, números de cuenta, cédula ni montos reales**, ni en issues, ni en pull requests, ni en comentarios.

Si necesitás mostrar un caso:
- describí las columnas y el formato del archivo, sin los valores;
- o armá un ejemplo con números inventados, como `examples/events-ejemplo.csv`.

Si subiste algo por error, editá o borrá el comentario. Ojo: GitHub puede guardar el historial de ediciones, así que lo más seguro es borrarlo.

## Reportar un problema

Abrí un issue con la plantilla "Algo no funciona". Indicá:
- broker y tipo de archivo (por ejemplo: "Schwab, Realized Gain/Loss en CSV");
- qué esperabas y qué pasó;
- el mensaje de error, si hay. Antes de pegarlo, revisá que no tenga datos tuyos.

## Agregar un broker

1. **Guía de descarga:** una sección en `reference/brokers.md` con el paso a paso, incluida la foto al 31/12/2025.
2. **Qué usa Claude:** qué columnas de cada archivo se toman, en la misma sección.
3. **Reglas de lectura**, si el broker tiene algo particular (spreads, cierres parciales, splits): en `SKILL.md`, paso 3. Respetá el formato de `events.csv`, que está documentado al principio de `scripts/irpf_calc.py`.
4. **Ejemplo:** si podés, agregá filas inventadas de ese broker a `examples/events-ejemplo.csv`.

## Cambiar una regla de cálculo

- Citá la norma: ley, decreto o resolución DGI, con su artículo. Las fuentes actuales están en `reference/normativa.md`.
- Si la norma no lo resuelve, la regla va como **criterio por defecto** y como pregunta abierta en el informe, no como hecho.
- Agregá un caso a `--selftest` en `scripts/irpf_calc.py` y verificá que pase:

```
python3 -I scripts/irpf_calc.py --selftest
```

- El script usa solo la biblioteca estándar de Python. No agregues dependencias.

## Pull requests

- Un cambio por PR, con una descripción breve de qué y por qué.
- Si cambia el resultado del cálculo, mostralo con el ejemplo de `examples/`, nunca con datos reales.
