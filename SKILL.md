---
name: irpf-uy
description: Calculate the Uruguay IRPF anticipo (DGI código 119, boleto 2908) owed on foreign-broker income — sales, dividends, interest, coupons — from eToro, Charles Schwab and Interactive Brokers statements, comparing ficto vs real. Use when the user asks how much IRPF to pay/anticipar, mentions the October, February or semestral anticipo, uploads broker statements for Uruguayan taxes, or asks how to download the statements Claude needs from eToro, Schwab or IBKR.
---

## What this does

Turns broker exports into one exact UYU figure for the DGI anticipo, with an auditable per-event report. **Claude only parses and normalizes.** All FX lookups and tax math run in `scripts/irpf_calc.py`, so never compute the tax by hand.

Paths:
- Skill: the directory this file is in (`<skill>` below).
- **Data directory** (`<data>` below) holds `inputs/`, `events.csv`, `fx_cache.json` and `report-<period>.html`. Use the current working directory if it already has `inputs/` or `events.csv`. Otherwise ask the user where to keep their files, suggesting `~/irpf-uy/`, and create `inputs/` there. Each user has their own; never mix two people's data.
- Official sources: `reference/normativa.md` (articles behind each rule; check for newer decrees before each anticipo).
- Download guide: `reference/brokers.md`. If the user only asks "¿cómo bajo el extracto de X?", show that broker's section and stop.

Reply in Spanish (rioplatense is fine), since the user is filing with DGI Uruguay.

## Tax rules

These rules come from the official texts as of October 2026: Ley 20.446, Decreto 148/007 as amended by Decretos 95/026 and 237/026, and Resoluciones DGI 1517/026, 1783/026 and 2294/026. Article references and links are in `reference/normativa.md`. They are a summary, not legal advice. Rules marked **default** are interpretations where the norm is silent: the report lists them under "Preguntas abiertas". Tell the user about each default once, on the first run, and recommend confirming it with an accountant.

- Since **2026-01-01**, IRPF Cat. I taxes, for foreign brokers that do not withhold:
  - dividends, interest and coupons
  - **sales of financial assets** (incrementos patrimoniales, art. 29 ter)
  - Rate **12%**. The 8% rate is only a withholding by local intermediaries with custody. Income from derivatives is excluded.
- **Crypto:** the decree and resolutions don't mention it.
  - **Default:** crypto held directly (for example eToro rows of type Crypto) is excluded.
  - **Default:** crypto ETFs (IBIT, ETHA and similar) are included as listed financial assets (question F). If the user holds any, ask once whether they agree, then apply it every period, for losses and gains alike.
- A tax event happens only when income is received or a sale is made. Open positions and transfers between brokers (ACAT) are never taxed.
- **Fiscal cost of a sale** (art. 29 ter): the **weighted average** of the purchases of identical goods. Assets that are listed and were held before 2026 enter at their **market value on 31/12/2025**, which is mandatory ("será"). Prices from Bloomberg are accepted (Res. 1517 art. 12), so a broker's 31/12/2025 statement price is fine.
  - **Default** (question G): the average is per taxpayer, pooling the same symbol across all brokers.
  - `--cost-method lot` uses each broker's own lot matching, for comparison only.
- **Exchange rate** (art. 29 ter, question E): the BCU USD billete rate (code 2225) of the **day before the sale**, or the previous business day.
  - **Default:** dividends and interest use the same rule; the norm doesn't say.
  - `--fx-mode event` and `--fx-mode period-end` are only for comparison.
- **Ficto** (art. 29 ter): 20% of the sale price × 12% = 2.4% of the proceeds, plus 12% of dividends and interest. The option is **annual**, is exercised through the declaración jurada, and covers all the year's sales: without a local withholding agent there is one option per year (question C). Without the option, real applies.
- **Real:** (proceeds − fiscal cost) × 12%. Losses net against other incrementos patrimoniales and against foreign capital income such as dividends (art. 30, losses must be proven).
  - Carrying a net loss into later years is **not** in the regulations reviewed (question I). Present it as unconfirmed.
- **Foreign withholding credit** (art. 76 bis, question B): an analogous income tax paid abroad on the same income (US 30% on dividends, since there is no treaty) is credited, capped at the IRPF of that income. The excess is lost.
  - The script caps it per dividend and matches `wht` rows to income by broker + date + symbol. It warns about any it cannot match, so keep those fields identical.
  - **Default:** the credit is taken in the anticipo. The norm doesn't say whether that is allowed or only in the declaración jurada; if the accountant says only there, run with `--no-wht-credit`.
- **Pagos a cuenta** (art. 44 terdecies): semestral, on the income **accumulated since 1 January**, at 12%, minus what was paid for the first semester. The 2nd anticipo is the annual total minus the 1st.
  - The user can make them **definitive**, and then files no declaración jurada for that income.
  - **Due dates** (Res. 1517 arts. 22 and 26, Res. 1783 num. 4): Jan–Jun is due in **August**, but for 2026 only it moved to **26/10/2026**. Jul–Dec is due in **February** of the next year.
- The method chosen for the year **must be kept for the whole year**.
- How to pay: DGI Servicios en línea → Boleto 2908 → RUT = cédula → código **119** → period → amount in pesos → pay online.
  - Period: "hasta mes 06/<year>" for the 1st, "12/<year>" for the 2nd.

## Workflow

1. **Period.** Ask which anticipo: H1 = Jan 1..Jun 30, H2 = Jul 1..Dec 31 of the tax year. Default to the one whose deadline is next.
   - **The data always covers the tax year from Jan 1 to today**, whichever anticipo it is. The method is fixed for the whole year, so choosing it needs the sales made after the period too. The script takes the period from `--period` and uses the rest for the year view.

2. **Collect files.** List `<data>/inputs/` and check it against the checklist in `reference/brokers.md`. Also check `~/Downloads` for recent eToro, Schwab or IBKR statements and offer to copy them in.
   - Ask which of the three brokers the user has accounts at. Don't demand files for a broker they don't use.
   - Ask, per broker, whether they held positions there on 31/12/2025. If yes or unsure, the **31/12/2025 snapshot is required**, not optional. Skip it only for an account opened in 2026.
   - For every broker or file that is missing, print **that broker's full step-by-step section** from `reference/brokers.md`, including its "Foto al 31/12/2025" steps, then wait for the user.
   - On a first run, or when the user starts from scratch, print the full sections for every broker they use. Don't summarize them.

3. **Parse into `<data>/events.csv`.** Use these columns:
   `broker,date,type,symbol,open_date,quantity,proceeds_usd,cost_usd,cost_basis_2025_usd,amount_usd,notes`
   - Taxable types: `sale` | `dividend` | `interest` | `coupon` | `wht`. Use the date the income was received or the trade date of the sale.
   - `sale` rows: one row per sale order, with `quantity`, `proceeds_usd` (net of commissions) and the broker's own lot cost in `cost_usd` (including buy commissions).
     - For lots held before 2026, also fill `open_date` = `pre2026` and `cost_basis_2025_usd`. They are used by `--cost-method lot` and to reconcile with the broker.
   - `dividend`, `interest` and `coupon` rows: the **gross** amount. Foreign withholding goes in its own `wht` row as a positive number.
   - **Position rows for the weighted average.** They are not taxable. Use the same `symbol` for the same security at every broker.
     - `holding`: every position held on 31/12/2025 at each broker, sold or not. Dated 2025-12-31, with `quantity`, `cost_basis_2025_usd` (market value that day) and `cost_usd` (original cost, if the statement has it).
     - `buy`: every purchase of the year, dividend reinvestments included. It has `quantity` and `cost_usd`, including commissions and eToro's opening spread.
     - `split`: a split or reverse split. `quantity` = old shares per new share. A cash-in-lieu payment is a `sale` of the fraction.
     - Transfers between brokers (ACAT) produce no row: the pool is per taxpayer.
   - **Order within a day matters** for the average. Write rows in the order they happened: IBKR and eToro have times; Schwab lists each day newest first. Say when the same symbol traded at two brokers on the same day, because their relative order is a guess.
   - **Include every event of the tax year up to the download date**, not just the period. Drop events from other years.
   - Exclude crypto. Put flags (CFD, leverage, fees not deducted, refunds) in `notes`.
   - Read XLSX files with `<skill>/scripts/xlsx_read.py` (stdlib only; don't assume pandas or openpyxl are installed). Run it as a CLI to see every sheet, or import `read()` into a parser.
   - Use the csv module for IBKR's multi-section CSV. Read PDFs with the pdf skill when needed.
   - Write the parsing code as `<data>/build_events_<period>.py`, not as ad-hoc commands, so the next run or an accountant can reproduce `events.csv`.
   - **31/12/2025 values** (for `holding` rows and the pre-2026 lot cost):
     - Prices come **only from the user's own documents**. Don't use market-data tools or the web: the only external connection this skill uses is BCU.
     - IBKR: *Mark-to-Market Performance Summary* "Prior Quantity"/"Prior Price" in an Activity Statement that starts 2026-01-01, or *Open Positions* in `ibkr_2025-12-31.csv`. For Treasury Bills, the price is per 100 of face value.
     - Schwab: *Positions* in `schwab_2025-12_statement.pdf` (quantity, price, cost basis).
     - eToro: *Holdings* "Current Rate" in `etoro_2025-12-31.xlsx`, after checking that its *Snapshot Date* is 2025-12-31.
     - If a snapshot is missing, ask the user to fill `<data>/precios_2025-12-31.csv` (`symbol,price,source`; format in `reference/brokers.md`).
     - If there is still no price, leave it blank. The report marks `real_2025` as incomplete.
     - Put the price and its source in `notes`, for example "34 x 151.95 (estado Schwab dic-2025)".

4. **Reconcile before calculating.** Show a per-broker table with the row count, total proceeds, realized P/L, gross dividends, WHT and interest (all in USD). Compare it with the broker's own summary:
   - IBKR: *Realized & Unrealized Performance Summary*
   - Schwab: Realized G/L totals
   - eToro: *Financial Summary*

   Reconcile the whole year to date, which is what the statements cover. Also show the count of sales after the period, so the user sees what the year view adds.

   Check the positions too. Replay holdings + buys − sales (with splits) per symbol: the result must equal the open positions the brokers report today. A gap means a missing buy, sale or snapshot.

   Explain any differences. **Wait for the user's OK.**

5. **Calculate:**
   ```
   python3 -I <skill>/scripts/irpf_calc.py <data>/events.csv \
     --period 2026-01..2026-06 --out <data>/report-2026H1.html
   open <data>/report-2026H1.html
   ```
   - The report is a self-contained HTML page with light and dark mode. It stays local and is never published. Use `--out *.md` only if the user asks for Markdown.
   - BCU rates are fetched automatically and cached in `<data>/fx_cache.json`.
   - If BCU is unreachable, ask for or build a `--fx-file` (`date,rate`) from the BCU "consulta histórica" page.
   - When `events.csv` has events outside the period, the report adds **"Vista del año a la fecha"**. It shows, per method, the tax for the period, for the rest of the year to date and for the year. The recommended method is the one with the lower **annual** tax. The amount to pay is still the period's amount under that method.
   - Optimization tips, top 10 tables, per-broker totals and event detail cover the year to date. The "Resultado" and "Totales" sections cover only the period.
   - **For H2**: run with `--period 2026-07..2026-12 --prior-paid-uyu <H1 amount paid>`. The report gives both the Jul–Dec amount and the annual netting (year minus anticipos paid). Present both: the anticipo is usually described as covering Jul–Dec only, and the user should confirm with an accountant which one applies.
   - If the user wants to double-check the script itself, run `--selftest`.

6. **Present the result:**
   - The method table and the recommended amount
   - The warning that the method is locked for the whole year. Use the year view: say whether the sales after the period change which method is cheaper. Ask what sales they still expect before Dec 31.
   - The ficto vs real trade-off: ficto needs a declaración jurada
   - The boleto 2908 steps
   - The open questions (A–I) printed in the report. If the methods differ a lot, recommend confirming A and B with an accountant before paying.
   - The **Optimización de inversiones** box: summarize its 2–3 most relevant tips. The script only prints a tip when the data triggers it (break-even margin vs 20%, sales that earned less than the 2.4% ficto cost, realized losses, loss harvesting or carry-forward, US withholding over 20%, untaxed pre-2026 gains). Add your own context-specific tips in chat, but don't invent numbers.
   - The **Mejores / Peores ventas (top 10)** tables: one row per sale order (broker + date + symbol, lots summed), ranked by fiscal result (31/12/2025 basis for pre-2026 lots). Mention the biggest winner and loser briefly.

## Guardrails

- Never edit files in `inputs/`. They are the evidence.
- Don't invent missing data such as cost basis, open dates or prices. Ask, or leave the field blank and let the report flag it.
- Everything in `<data>` is personal financial data: never publish it or copy it into the skill directory.
- This is a calculation aid, not tax advice. Say so once, briefly.
