# Cómo bajar los archivos de cada broker

Carpeta de destino: `inputs/` dentro de tu carpeta de datos (por ejemplo `~/irpf-uy/inputs/`).

| Período | Desde | Hasta | Vencimiento anticipo |
|---|---|---|---|
| H1 2026 | 2026-01-01 | 2026-06-30 | 26/10/2026 |
| H2 2026 | 2026-07-01 | 2026-12-31 | primeros días de enero 2027 |

Reemplazá `2026H1` por `2026H2` en los nombres de archivo para el segundo semestre.

**Foto al 31/12/2025:** solo hace falta si se quiere evaluar el método *real con costo = valor al 31/12/2025* (pregunta A). Alcanza con bajarla una sola vez.

Los menús de los brokers cambian seguido. Si un paso no coincide, usá la sección "Si no lo encontrás" de ese broker.

---

## Interactive Brokers (Client Portal, web)

**Archivo principal: Activity Statement en CSV**
1. Entrá a <https://www.interactivebrokers.com> → Log In → Client Portal.
2. En el menú, abrí **Performance & Reports → Statements**. En español es *Rendimiento e informes → Extractos*.
3. En *Default Statements*, hacé clic en la flecha (Run) junto a **Activity**.
4. En **Period**, elegí **Custom Date Range** y poné From `2026-01-01` y To `2026-06-30`.
5. En **Format**, elegí **CSV**. En **Language**, elegí **English**, porque así los nombres de las secciones son estables.
6. Hacé clic en **Download** o **Run** y guardá el archivo como `inputs/ibkr_2026H1_activity.csv`.
7. Opcional pero recomendado: repetí con Format = **PDF** y guardá `inputs/ibkr_2026H1_activity.pdf`. Sirve de respaldo si después hay que hacer la declaración jurada.

**Foto al 31/12/2025 (opcional)**
8. Corré el mismo Activity con Period = **Daily**, fecha `2025-12-31` (o Custom Date Range 2025-12-31 → 2025-12-31), en CSV. Guardalo como `inputs/ibkr_2025-12-31_positions.csv`.

**Si tenés más de una cuenta** (por ejemplo, individual y IRA): elegí cada cuenta en el selector de arriba y repetí los pasos. Agregá el número de cuenta al nombre del archivo.

**Qué usa Claude del CSV**
- `Trades`: solo las filas `Order` de Stocks, ETFs y Bonds. De ahí toma Date/Time, Symbol, Quantity, Proceeds, Basis (costo), Realized P/L y Comm/Fee. Las ventas son las filas con Quantity negativa.
- `Dividends` y `Payment In Lieu Of Dividends`: se toman como dividendos.
- `Withholding Tax`: se toma como retención (wht).
- `Interest`: se toma como interés. Si está en negativo (margin interest), es un gasto: se marca y no se resta.
- `Bond Interest Received`: se toma como cupón.
- Se ignoran: `Deposits & Withdrawals`, `Forex`/conversiones de moneda, `Fees` de suscripción de market data (se marcan) y `Open Positions` (salvo en el snapshot 2025).
- La fecha de compra de cada lote sale de `Trades` (filas `ClosedLot`). Si no está, hay que correr el Flex Query de abajo.

**Si no lo encontrás:** **Performance & Reports → Flex Queries → Activity Flex Query → +**. Marcá las secciones **Trades** (con *Closed Lots*), **Cash Transactions** y **Open Positions**. Format = CSV, Period = Custom. Guardala, corrélá con el rango del período y descargá el archivo.

---

## Charles Schwab (schwab.com)

**Archivo 1: Transacciones (CSV)**
1. Entrá a <https://client.schwab.com> → **Accounts → History**.
2. Elegí la cuenta de brokerage arriba. Si tenés varias, repetí todo por cada una.
3. En la pestaña **Transactions**, abrí **Edit Filter** y elegí **All Transactions**.
4. En Date Range, elegí **Custom** con `01/01/2026` a `06/30/2026` (formato de EE.UU., MM/DD/YYYY) y hacé clic en **Search**.
5. Hacé clic en **Export** (ícono arriba a la derecha), confirmá y guardá el archivo como `inputs/schwab_2026H1_transactions.csv`.
   - Si el CSV sale **vacío**, Schwab tiene un tope de unas 1.500 filas. Exportá por trimestre (`..._Q1.csv`, `..._Q2.csv`).

**Archivo 2: Realized Gain/Loss (CSV)**
6. En la misma pantalla de History, abrí la pestaña **Realized Gain/Loss**.
7. Poné el mismo rango, hacé clic en **Export** y guardá el archivo como `inputs/schwab_2026H1_realized.csv`. Este archivo trae el costo y la fecha de compra (Opened Date) de cada lote vendido.

**Foto al 31/12/2025 (opcional)**
8. Abrí **Accounts → Statements & Tax Forms** con Document type = Statements. Bajá el estado de cuenta de **diciembre 2025** (PDF) y guardalo como `inputs/schwab_2025-12_statement.pdf`. Claude lee la sección *Positions* (cantidad y precio al cierre).

**Qué usa Claude**
- Ventas: las filas `Sell` del archivo de transacciones, cruzadas con Realized Gain/Loss para obtener Cost Basis y Opened Date.
- Dividendos: `Qualified Dividend`, `Non-Qualified Div`, `Cash Dividend`, `Pr Yr Div Reinv`, `Reinvest Dividend` y `Special Dividend`. El dividendo reinvertido igual cuenta como percibido.
- Intereses: `Credit Interest`, `Bank Interest` y `Bond Interest`.
- Retenciones: `NRA Tax Adj` y `NRA Withholding` → wht. Los ajustes positivos son devoluciones y se restan de wht.
- Se ignoran: `Buy`, `Reinvest Shares` (es la compra del reinvertido), `MoneyLink Transfer`, `Wire Funds`, `Journal` y `Service Fee` (se marca).

**Si no lo encontrás:** en el **Form 1099-B** de 2026 (llega en febrero 2027) está todo, pero tarde para el H1. Otra opción: **Accounts → Statements**, bajar los PDF mensuales de enero a junio 2026 y ponerlos en `inputs/`. Claude puede leerlos.

---

## eToro (web)

**Archivo principal: Account Statement en XLS**
1. Entrá a <https://www.etoro.com>, hacé clic en tu foto o nombre (menú izquierdo) y después en **Settings → Account**.
2. Junto a **Account Statement**, hacé clic en **View**.
   - Otra ruta: **Portfolio → History** → ícono de engranaje (arriba a la derecha) → **Account Statement**.
3. Elegí **Select Dates → Custom**, poné `01/01/2026` a `30/06/2026` y hacé clic en **Create**.
4. Arriba a la derecha, hacé clic en **XLS** (no PDF) y guardá el archivo como `inputs/etoro_2026H1.xlsx`.
5. Recomendado: descargá también el **PDF** del mismo rango como respaldo (`inputs/etoro_2026H1.pdf`).
   - Si ya tenés un estado de cuenta que cubre más que el período (por ejemplo, del 1/1 a hoy), sirve si se filtran las fechas, pero el XLS del rango exacto es mejor.

**Foto al 31/12/2025:** el estado de eToro no trae precios de posiciones abiertas. Claude toma de Closed Positions las ventas de lotes con Open Date anterior a 2026. Para cada símbolo busca el precio de cierre del 31/12/2025 (con las herramientas FMP o Financial Datasets) y lo multiplica por las Units. Vos confirmás esos números.

**Qué usa Claude del XLS**
- `Closed Positions`: Position ID, Action, Open Date, Close Date, Amount (costo invertido), Units, Open Rate, Close Rate, Profit(USD), Type e ISIN.
  - Precio de venta = Amount + Profit. Costo = Amount.
  - Type = **Crypto**: se **excluye** (no está alcanzado por esta normativa).
  - Type = **CFD**: se marca. Es un derivado, no un activo comprado, así que hay que consultarlo con el contador. Se incluye en el resultado real y en el ficto se usa el precio de venta nocional.
  - Operaciones apalancadas (Leverage > 1): se marcan.
- `Dividends`: Date of Payment, Instrument Name, Net Dividend Received (USD) y Withholding Tax Amount (USD).
  - Dividendo bruto = Net + Withholding. La retención va como wht.
- `Account Activity`: Type = *Interest* se toma como interés. *Overnight fee* / *SDRT* son gastos: se marcan y no se restan. *Deposit*, *Withdraw* y *Conversion fee* se ignoran.

**Si no lo encontrás:** el PDF trae las mismas tablas. Claude puede leerlo, aunque con más riesgo de errores de lectura en tablas largas, por eso se verifica contra los totales de *Financial Summary*.

---

## Checklist antes de calcular

- [ ] Un archivo por broker y por cuenta, con el rango exacto del período
- [ ] Formato CSV/XLS como fuente principal y PDF como respaldo
- [ ] Schwab: transacciones **y** Realized Gain/Loss
- [ ] Foto al 31/12/2025 de cada broker, solo si se evalúa real con costo 2025
- [ ] Los originales quedan en `inputs/` sin editar, porque son la evidencia para la declaración jurada si se elige ficto
