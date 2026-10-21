# irpf-uy

Skill de Claude Code para calcular el **anticipo de IRPF en Uruguay** (DGI, código 119, boleto 2908) sobre lo que ganás en brokers del exterior: ventas de acciones y ETFs, dividendos, intereses y cupones. Rige desde la reforma vigente desde el 1/1/2026.

Brokers soportados: **Interactive Brokers**, **Charles Schwab** y **eToro**.

## Qué hace

1. Te dice qué extractos bajar de cada broker y cómo, paso a paso.
2. Claude lee los extractos y arma un `events.csv` con cada venta, dividendo, interés y retención.
3. Antes de calcular, concilia los totales con el resumen de cada broker y espera tu OK.
4. Un script en Python convierte cada evento a pesos con la cotización BCU de su fecha y calcula el impuesto por **ficto** y por **real**.
5. Genera un informe HTML con:
   - el monto a pagar y el método recomendado
   - el crédito por retenciones del exterior
   - sugerencias para optimizar tus inversiones
   - las 10 mejores y las 10 peores ventas
   - el detalle de cada evento
   - las preguntas abiertas para confirmar con un contador

Claude solo lee y ordena los datos. Todas las cuentas las hace `scripts/irpf_calc.py`.

## Instalación

```
git clone https://github.com/cnavas1986/irpf-uy.git ~/.claude/skills/irpf-uy
```

Requisitos:
- Claude Code
- `python3`: el script solo usa la biblioteca estándar
- `pandas` u `openpyxl`, para que Claude lea los XLS de eToro

## Uso

1. Creá una carpeta para tus datos (por ejemplo `~/irpf-uy/`) y abrí Claude Code ahí.
2. Preguntá: *"¿cuánto IRPF tengo que anticipar?"* o *"¿cómo bajo el extracto de Schwab?"*.

El skill crea `inputs/` en esa carpeta y te guía desde ahí. Tus extractos, el `events.csv` y los informes quedan **solo en tu carpeta de datos**: nunca los subas a este repositorio ni a ningún otro.

Para verificar el script:

```
python3 -I ~/.claude/skills/irpf-uy/scripts/irpf_calc.py --selftest
```

## Criterios por defecto

El script aplica estos criterios. Confirmalos con un contador antes de pagar.

- **Lotes comprados antes de 2026:** el costo fiscal es su valor de mercado al 31/12/2025.
- **Retenciones del exterior:** se descuentan como crédito, hasta el 12% de cada dividendo. Con `--no-wht-credit` el cálculo no las descuenta.
- **ETFs de cripto** (IBIT, ETHA): están alcanzados. La cripto que tenés directamente, no.
- **Método:** ficto o real, el mismo para todo el año.

## Aviso

Es una ayuda para hacer el cálculo, **no es asesoramiento tributario ni financiero**. Las reglas resumen la normativa vigente según cómo se explicaba públicamente en octubre de 2026 y pueden cambiar.
