# Cómo bajar los archivos de cada broker

Carpeta de destino: `inputs/` dentro de tu carpeta de datos (por ejemplo `~/irpf-uy/inputs/`).

**Rango de fechas: siempre del 1 de enero del año fiscal hasta hoy**, para los dos anticipos. El método (ficto o real) se elige una vez para todo el año, así que para decidirlo hay que ver también las ventas hechas después del 30/6. El cálculo separa solo cada semestre.

| Anticipo | Período que paga | Vencimiento | Qué bajás |
|---|---|---|---|
| 1º de 2026 | ene–jun 2026 | 26/10/2026 | 01/01/2026 → hoy |
| 2º de 2026 | jul–dic 2026 | febrero 2027 | 01/01/2026 → 31/12/2026 |

En los nombres de archivo, `2026` es el año fiscal. Si volvés a bajar un archivo más adelante, reemplazá el anterior: siempre arranca el 1/1.

**Foto al 31/12/2025 (precio de cada posición a esa fecha).** Si vendés algo que compraste antes de 2026, su costo fiscal es lo que valía el 31/12/2025, no lo que pagaste (pregunta A). Ese precio sale **de tus propios extractos**, no de internet. Cada broker tiene su paso "Foto al 31/12/2025" abajo. Se baja **una sola vez** y sirve para todo el año y los siguientes. Solo podés saltearlo en un broker donde abriste la cuenta en 2026 o donde no tenías nada al 31/12/2025.

Los menús de los brokers cambian seguido. Si un paso no coincide, usá la sección "Si no lo encontrás" de ese broker.

---

## Interactive Brokers (Client Portal, web)

**Archivo principal: Activity Statement en CSV**
1. Entrá a <https://www.interactivebrokers.com> → Log In → Client Portal.
2. En el menú, abrí **Performance & Reports → Statements**. En español es *Rendimiento e informes → Extractos*.
3. En *Default Statements*, hacé clic en la flecha (Run) junto a **Activity**.
4. En **Period**, elegí **Custom Date Range**: From `2026-01-01`, To **la fecha de hoy** (o el último día hábil disponible).
5. En **Format**, elegí **CSV**. En **Language**, elegí **English**, porque así los nombres de las secciones son estables.
6. Hacé clic en **Download** o **Run** y guardá el archivo como `inputs/ibkr_2026_activity.csv`.
7. Recomendado: repetí con Format = **PDF** y guardá `inputs/ibkr_2026_activity.pdf`. Sirve de respaldo si después hay que hacer la declaración jurada.

**Foto al 31/12/2025:** como el Activity Statement **empieza el 1/1/2026**, ya la trae. Está en la sección *Mark-to-Market Performance Summary*: "Prior Quantity" y "Prior Price" son la cantidad y el precio de cada posición al 31/12/2025. No hace falta bajar nada más.
- Si no aparece: corré el Activity con Period = **Daily** y fecha `2025-12-31`, en CSV, y guardalo como `inputs/ibkr_2025-12-31.csv`. Sirve la sección *Open Positions* ("Close Price").

**Si tenés más de una cuenta** (por ejemplo, individual y IRA): elegí cada cuenta en el selector de arriba y repetí los pasos. Agregá el número de cuenta al nombre del archivo.

**Qué usa Claude del CSV**
- `Trades`: solo las filas `Order` de Stocks, ETFs, Bonds y Treasury Bills. De ahí toma Date/Time, Symbol, Quantity, Proceeds, Basis (costo), Realized P/L y Comm/Fee. Las ventas son las filas con Quantity negativa.
- `Dividends` y `Payment In Lieu Of Dividends`: se toman como dividendos.
- `Withholding Tax`: se toma como retención (wht).
- `Interest`: se toma como interés. Si está en negativo (margin interest), es un gasto: se marca y no se resta.
- `Bond Interest Received`: se toma como cupón.
- `Mark-to-Market Performance Summary`: la foto al 31/12/2025.
- Se ignoran: `Deposits & Withdrawals`, `Forex`/conversiones de moneda y `Fees` de suscripción de market data (se marcan).
- La fecha de compra de cada lote sale de `Trades` (filas `ClosedLot`). Si no están, Claude la deduce: si al 31/12/2025 tenías al menos la cantidad vendida, IBKR vende primero lo más viejo (FIFO), así que es un lote anterior a 2026. Si no, son las compras de 2026 previas a la venta. Claude te lo muestra en la conciliación.

**Si no lo encontrás:** **Performance & Reports → Flex Queries → Activity Flex Query → +**. Marcá las secciones **Trades** (con *Closed Lots*), **Cash Transactions** y **Open Positions**. Format = CSV, Period = Custom. Guardala, corrélá con el rango del período y descargá el archivo.

---

## Charles Schwab (schwab.com)

**Archivo 1: Transacciones (CSV)**
1. Entrá a <https://client.schwab.com> → **Accounts → History**.
2. Elegí la cuenta de brokerage arriba. Si tenés varias, repetí todo por cada una.
3. En la pestaña **Transactions**, abrí **Edit Filter** y elegí **All Transactions**.
4. En Date Range, elegí **Custom** desde `01/01/2026` hasta **hoy** (formato de EE.UU., MM/DD/YYYY) y hacé clic en **Search**.
5. Hacé clic en **Export** (ícono arriba a la derecha), confirmá y guardá el archivo como `inputs/schwab_2026_transactions.csv`.
   - Si el CSV sale **vacío**, Schwab tiene un tope de unas 1.500 filas. Exportá por trimestre (`..._Q1.csv`, `..._Q2.csv`).

**Archivo 2: Realized Gain/Loss (CSV)**
6. En la misma pantalla de History, abrí la pestaña **Realized Gain/Loss**.
7. Poné el mismo rango (01/01/2026 a hoy), hacé clic en **Export** y guardá el archivo como `inputs/schwab_2026_realized.csv`. Este archivo trae el costo y la fecha de compra (Opened Date) de cada lote vendido.

**Archivo 3: Foto al 31/12/2025 (estado de cuenta de diciembre 2025, PDF)**
8. Abrí **Accounts → Statements & Tax Forms** y elegí Document type = **Statements**.
9. Buscá el estado de cuenta de **diciembre 2025** (período que termina el 31/12/2025), descargá el PDF y guardalo como `inputs/schwab_2025-12_statement.pdf`.
   - Claude lee la sección *Positions*: cantidad, precio y valor de mercado de cada acción o ETF al 31/12/2025.
   - Si tenés varias cuentas, bajá uno por cuenta.

**Qué usa Claude**
- Ventas: las filas de Realized Gain/Loss (un lote por fila, con Proceeds, Cost Basis y Opened Date), verificadas contra las filas `Sell` del archivo de transacciones.
- Dividendos: `Qualified Dividend`, `Non-Qualified Div`, `Cash Dividend`, `Qual Div Reinvest`, `Pr Yr Div Reinv`, `Reinvest Dividend` y `Special Dividend`. El dividendo reinvertido igual cuenta como percibido.
- Intereses: `Credit Interest`, `Bank Interest` y `Bond Interest`.
- Retenciones: `NRA Tax Adj` y `NRA Withholding` → wht. Los ajustes positivos son devoluciones y se restan de wht.
- Se ignoran: `Buy`, `Reinvest Shares` (es la compra del reinvertido), `MoneyLink Transfer`, `Wire Funds`, `Journal` y `Service Fee` (se marca).

**Si no lo encontrás:** en el **Form 1099-B** de 2026 (llega en febrero 2027) está todo, pero tarde para los anticipos. Otra opción: **Accounts → Statements**, bajar los PDF mensuales de 2026 hasta el último disponible y ponerlos en `inputs/`. Claude puede leerlos.

---

## eToro (web)

**Archivo principal: Account Statement en XLS**
1. Entrá a <https://www.etoro.com>, hacé clic en tu foto o nombre (menú izquierdo) y después en **Settings → Account**.
2. Junto a **Account Statement**, hacé clic en **View**.
   - Otra ruta: **Portfolio → History** → ícono de engranaje (arriba a la derecha) → **Account Statement**.
3. Elegí **Select Dates → Custom**, poné desde `01/01/2026` hasta **hoy** (formato DD/MM/YYYY) y hacé clic en **Create**.
4. Arriba a la derecha, hacé clic en **XLS** (no PDF) y guardá el archivo como `inputs/etoro_2026.xlsx`.
5. Recomendado: descargá también el **PDF** del mismo rango como respaldo (`inputs/etoro_2026.pdf`).

**Foto al 31/12/2025 (solo si tenías posiciones abiertas en eToro ese día)**
6. Repetí los pasos 1 a 3 con fecha final **31/12/2025** (la inicial puede ser cualquiera anterior, por ejemplo `01/01/2025`).
7. Bajá el **XLS** y guardalo como `inputs/etoro_2025-12-31.xlsx`. La hoja *Holdings* trae Units y Current Rate de cada posición en la fecha final del estado de cuenta (columna *Snapshot Date*). Claude verifica que esa fecha sea el 31/12/2025.
   - Si abriste la cuenta en 2026, salteá este paso: el *Account Summary* del archivo principal muestra "Beginning Realized Equity" = 0.

**Qué usa Claude del XLS**
- `Closed Positions`: Position ID, Action, Open Date, Close Date, Amount (costo invertido), Units, Profit(USD), Leverage, Type e ISIN.
  - Precio de venta = Amount + Profit − spread de cierre. Costo = Amount + spread de apertura. Los spreads salen de `Account Activity` ("Opening and Closing Spread", por Position ID).
  - Type = **Crypto**: se **excluye** (no está alcanzado por esta normativa).
  - Type = **CFD**: se marca. Es un derivado, no un activo comprado, así que hay que consultarlo con el contador. Se incluye en el resultado real y en el ficto se usa el precio de venta nocional.
  - Operaciones apalancadas (Leverage > 1): se marcan.
- `Dividends`: Date of Payment, Instrument Name, Net Dividend Received (USD) y Withholding Tax Amount (USD).
  - Dividendo bruto = Net + Withholding. La retención va como wht.
- `Account Activity`: Type = *Interest* se toma como interés. *Overnight fee* / *SDRT* son gastos: se marcan y no se restan. *Deposit*, *Withdraw* y *Conversion fee* se ignoran.

**Si no lo encontrás:** el PDF trae las mismas tablas. Claude puede leerlo, aunque con más riesgo de errores de lectura en tablas largas, por eso se verifica contra los totales de *Financial Summary*.

---

## Si falta algún precio al 31/12/2025

Si un broker no te da la foto, cargá el precio a mano en `precios_2025-12-31.csv`, en tu carpeta de datos (no en `inputs/`):

```
symbol,price,source
GLOB,65.37,Yahoo Finance - cierre 31/12/2025
```

Usá el precio de **cierre** del 31/12/2025 y anotá de dónde lo sacaste. Si tampoco lo tenés, el campo queda vacío y el informe marca el método real como incompleto.

---

## Checklist antes de calcular

- [ ] Un archivo por broker y por cuenta, del 01/01 del año fiscal hasta hoy
- [ ] Formato CSV/XLS como fuente principal y PDF como respaldo
- [ ] Schwab: transacciones **y** Realized Gain/Loss
- [ ] Foto al 31/12/2025 de cada broker donde tenías posiciones ese día (IBKR: viene en el Activity del año, que empieza el 1/1; Schwab: estado de cuenta de diciembre 2025; eToro: XLS al 31/12/2025)
- [ ] Los originales quedan en `inputs/` sin editar, porque son la evidencia para la declaración jurada si se elige ficto
