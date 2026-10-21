# Ejemplo para probar sin datos propios

`events-ejemplo.csv` tiene operaciones **inventadas** en tres brokers:

- posiciones al 31/12/2025;
- una venta con pérdida y otra con ganancia;
- la misma acción en dos brokers, que entra al mismo promedio ponderado;
- un reverse split;
- un dividendo con retención de EE.UU.;
- intereses.

`tc-ejemplo.csv` tiene las cotizaciones **reales** del BCU (dólar billete) de los días anteriores a cada operación. Con ellas el ejemplo funciona sin conexión.

```
cd ~/.claude/skills/irpf-uy
python3 -I scripts/irpf_calc.py examples/events-ejemplo.csv --period 2026-01..2026-06 \
  --fx-file examples/tc-ejemplo.csv --out ~/irpf-ejemplo.html
open ~/irpf-ejemplo.html
```

El informe se guarda fuera del repo. Probá también:
- `--period 2026-07..2026-12`, para ver el 2º anticipo;
- `--cost-method lot`, para comparar con el costo que asigna cada broker.
