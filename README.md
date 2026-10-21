# irpf-uy

Skill de Claude Code para calcular el **anticipo de IRPF en Uruguay** (DGI, código 119, boleto 2908) sobre lo que ganás en brokers del exterior: ventas de acciones y ETFs, dividendos, intereses y cupones. Rige desde la reforma vigente desde el 1/1/2026.

Brokers soportados: **Interactive Brokers**, **Charles Schwab** y **eToro**.

## Qué hace

1. Te dice qué extractos bajar de cada broker y cómo, paso a paso: siempre del 1/1 a hoy, más la foto de tus posiciones al 31/12/2025. Los precios salen de tus propios extractos: la única conexión externa es la cotización del dólar del BCU.
2. Claude lee los extractos y arma un `events.csv` con cada venta, dividendo, interés y retención, más las compras, la foto al 31/12/2025 y los splits que necesita el promedio ponderado.
3. Antes de calcular, concilia los totales con el resumen de cada broker y las posiciones abiertas, y espera tu OK.
4. Un script en Python calcula el costo fiscal por promedio ponderado (con lo que tenías al 31/12/2025 a su valor de ese día), convierte a pesos con la cotización BCU del día anterior a cada operación y calcula el impuesto por **ficto** y por **real**, según el Decreto 148/007 art. 29 ter. Las normas usadas están en `reference/normativa.md`.
5. Genera un informe HTML con:
   - el monto a pagar y el método recomendado, comparando ficto y real sobre todo el año a la fecha (el método no se puede cambiar a mitad de año)
   - el crédito por retenciones del exterior
   - sugerencias para optimizar tus inversiones
   - las 10 mejores y las 10 peores ventas
   - el detalle de cada evento
   - las preguntas abiertas para confirmar con un contador

Claude solo lee y ordena los datos. Todas las cuentas las hace `scripts/irpf_calc.py`.

## Instalación

```
git clone https://github.com/charliegin/irpf-uy.git ~/.claude/skills/irpf-uy
```

Requisitos:
- Claude Code
- `python3`. Los scripts solo usan la biblioteca estándar, incluido el que lee los XLSX de eToro, así que no hace falta instalar nada más.

## Uso

1. Creá una carpeta para tus datos (por ejemplo `~/irpf-uy/`) y abrí Claude Code ahí.
2. Preguntá: *"¿cuánto IRPF tengo que anticipar?"* o *"¿cómo bajo el extracto de Schwab?"*.

El skill crea `inputs/` en esa carpeta y te guía desde ahí. Tus extractos, el `events.csv` y los informes quedan **solo en tu carpeta de datos**: nunca los subas a este repositorio ni a ningún otro.

### Vencimientos

| Pago a cuenta | Qué cubre | Vence |
|---|---|---|
| 1º | enero a junio | agosto. Solo para 2026, el **26/10/2026** (Res. DGI 1783/026) |
| 2º | todo el año, menos el 1º | **febrero** del año siguiente |

Se paga con el boleto 2908, código **119**.

### Decisiones

Cuando resolvés una pregunta abierta, solo o con tu contador, Claude la anota en `decisiones.json`, dentro de tu carpeta de datos:

```json
{"B": {"decision": "El crédito por retenciones se descuenta en el anticipo", "fecha": "2026-10-21", "fuente": "contador"}}
```

El informe la muestra en "Decisiones tomadas" y la saca de las preguntas abiertas. Queda en tu carpeta, no en el skill, porque cada persona puede decidir distinto.

### Verificar y comparar

```
python3 -I ~/.claude/skills/irpf-uy/scripts/irpf_calc.py --selftest
```

- `--cost-method lot`: usa el costo que asignó cada broker, en lugar del promedio ponderado.
- `--fx-mode event` o `--fx-mode period-end`: usa el tipo de cambio del día del evento, o el del cierre del semestre.

Sirven para comparar con lo que muestra cada broker, o con otro criterio que te sugiera un contador.

## Criterios

Según el Decreto 148/007 (art. 29 ter), el script aplica:

- **Costo fiscal:** promedio ponderado de las compras. Lo que tenías al 31/12/2025, si cotiza en bolsa, entra a su valor de ese día.
- **Tipo de cambio:** el BCU dólar billete del día anterior a cada operación.
- **Método:** ficto (20% del precio de venta) o real, el mismo para todo el año.
- **Pagos a cuenta:** sobre lo acumulado desde el 1/1, menos el anticipo anterior.

Donde la norma no dice nada, el script aplica estos criterios por defecto. Confirmalos con un contador antes de pagar:

- **Promedio:** se calcula por contribuyente, sumando todos los brokers.
- **Retenciones del exterior:** se descuentan como crédito ya en el anticipo, hasta el 12% de cada dividendo. Con `--no-wht-credit` no se descuentan.
- **Cripto:** los ETFs de cripto (IBIT, ETHA) están alcanzados; la cripto que tenés directamente, no.
- **Tipo de cambio de dividendos e intereses:** el mismo del día anterior.
- **Arrastre de pérdidas a años siguientes:** sin confirmar.

## Aviso

Es una ayuda para hacer el cálculo, **no es asesoramiento tributario ni financiero**. Las reglas resumen los textos oficiales vigentes en octubre de 2026 (ver `reference/normativa.md`). El régimen se ajustó varias veces durante 2026: antes de cada anticipo, revisá en [IMPO](https://www.impo.com.uy) si hay decretos o resoluciones de la DGI nuevos.

## Licencia

[MIT](LICENSE). Podés usarlo, modificarlo y redistribuirlo libremente; los aportes son bienvenidos.
