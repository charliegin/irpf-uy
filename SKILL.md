---
name: irpf-uy
description: Calculate the Uruguay IRPF anticipo (DGI código 119, boleto 2908) owed on foreign-broker income — sales, dividends, interest, coupons — from eToro, Charles Schwab and Interactive Brokers statements, comparing ficto vs real. Use when the user asks how much IRPF to pay/anticipar, mentions the 26 October or January anticipo, uploads broker statements for Uruguayan taxes, or asks how to download the statements Claude needs from eToro, Schwab or IBKR.
---

## What this does

Turns broker exports into one exact UYU figure for the DGI anticipo, with an auditable per-event report. **Claude only parses and normalizes.** All FX lookups and tax math run in `scripts/irpf_calc.py`, so never compute the tax by hand.

Paths:
- Skill: the directory this file is in (`<skill>` below).
- **Data directory** (`<data>` below) holds `inputs/`, `events.csv`, `fx_cache.json` and `report-<period>.html`. Use the current working directory if it already has `inputs/` or `events.csv`. Otherwise ask the user where to keep their files, suggesting `~/irpf-uy/`, and create `inputs/` there. Each user has their own; never mix two people's data.
- Download guide: `reference/brokers.md`. If the user only asks "¿cómo bajo el extracto de X?", show that broker's section and stop.

Reply in Spanish (rioplatense is fine), since the user is filing with DGI Uruguay.

## Tax rules

These rules summarize the tax reform in force since 2026-01-01 as publicly explained in October 2026. They are not a legal text. When a rule is marked **default**, the script applies it and the report lists it under "Preguntas abiertas". Tell the user about each default once, on the first run, and recommend confirming it with an accountant.

- Since **2026-01-01**, IRPF Cat. I taxes, for foreign brokers that do not withhold:
  - dividends, interest and coupons
  - **sales of financial assets**
- Rate: **12%**. The 8% rate is only for local BCU brokers. Crypto held directly (for example eToro rows of type Crypto) is **out of scope**.
- **Crypto ETFs** (IBIT, ETHA and similar) — **default: included** as financial assets (question F). If the user holds any, ask once whether they agree. Whatever they choose, apply it every period, for losses and for gains alike.
- A tax event happens only when income is received or a sale is made. Open positions are never taxed.
- **Fresh start** — **default** (question A): returns accrued up to 2025-12-31 are outside IRPF; only growth from 2026-01-01 is taxed. Under real, the fiscal cost of a lot bought before 2026 is its **market value on 2025-12-31** (quantity × close price). This works both ways: pre-2026 losses cannot be used either. The original-cost row in the report is only for reconciling with the broker.
- **Ficto:** 20% of the sale price × 12% = 2.4% of the proceeds, plus 12% of dividends and interest. A declaración jurada with documents is required after the year ends.
- **Real:** (proceeds − fiscal cost) × 12%. Sale losses net against gains *and* against dividends and interest. A net loss carries forward 2 years. With the 2 anticipos this is final; whether a declaración jurada is still needed when foreign withholding is credited is part of question B.
- **Foreign withholding credit** — **default: applied** (question B). Tax withheld abroad (US 30%, since there is no treaty) is credited against the 12% IRPF.
  - The cap is per dividend: at most 12% of the gross amount it was withheld from. The excess is lost, with no refund and no use against other taxes.
  - The script matches `wht` rows to income by broker + date + symbol and warns about any it cannot match, so keep those fields identical.
  - Dividends and the credit go in the annual declaración jurada even when the net is 0.
  - It is open whether the credit can be taken in the anticipo or only in the declaración jurada. If the user's accountant says only in the declaración jurada, run the script with `--no-wht-credit`.
- The method chosen in H1 **must be kept for the whole year**.
- Each event is converted at the **BCU USD billete rate (code 2225) of its date**, or the previous business day.
- Anticipos:
  - **H1 (Jan–Jun): due 26/10**, período "hasta mes 06/<year>"
  - **H2 (Jul–Dec): early January** of the next year, período 12/<year>
- How to pay: DGI Servicios en línea → Boleto 2908 → RUT = cédula → código **119** → period → amount in pesos → pay online.

## Workflow

1. **Period.** Ask which period: H1 = Jan 1..Jun 30, H2 = Jul 1..Dec 31 of the tax year. Default to the one whose deadline is next.

2. **Collect files.** List `<data>/inputs/` and check it against the checklist in `reference/brokers.md`. Also check `~/Downloads` for recent eToro, Schwab or IBKR statements and offer to copy them in.
   - Ask which of the three brokers the user has accounts at. Don't demand files for a broker they don't use.
   - For every broker or file that is missing, print **that broker's full step-by-step section** from `reference/brokers.md`, then wait for the user.

3. **Parse into `<data>/events.csv`.** Use these columns:
   `broker,date,type,symbol,open_date,proceeds_usd,cost_usd,cost_basis_2025_usd,amount_usd,notes`
   - `type`: `sale` | `dividend` | `interest` | `coupon` | `wht`. Use the date the income was received or the trade date of the sale.
   - `sale` rows: one row per closed lot with `proceeds_usd` (net of commissions), `cost_usd` (including buy commissions) and `open_date`.
   - `dividend`, `interest` and `coupon` rows: the **gross** amount. Foreign withholding goes in its own `wht` row as a positive number.
   - **Only include events with dates inside the period.** Statements often cover more.
   - Exclude crypto. Put flags (CFD, leverage, fees not deducted, refunds) in `notes`.
   - Use pandas or openpyxl for XLS and the csv module for IBKR's multi-section CSV. Read PDFs with the pdf skill when needed.
   - **Pre-2026 lots** (needed for `cost_basis_2025_usd`):
     - IBKR: quantity × close price from the 31/12/2025 Open Positions.
     - Schwab: from the December 2025 statement.
     - eToro, or when there is no snapshot: look up the 2025-12-31 close with whatever market-data tool is available (for example FMP or Financial Datasets MCP), and show the user the prices used.
     - If no price can be found, leave the field blank. The report marks `real_2025` as incomplete.

4. **Reconcile before calculating.** Show a per-broker table with the row count, total proceeds, realized P/L, gross dividends, WHT and interest (all in USD). Compare it with the broker's own summary:
   - IBKR: *Realized & Unrealized Performance Summary*
   - Schwab: Realized G/L totals
   - eToro: *Financial Summary*

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
   - **For H2**, run it twice:
     1. Once on the H2 events only.
     2. Once on the full year's events with `--prior-paid-uyu <H1 amount paid>`, to show the annual netting view.

     Present both: the anticipo is usually described as covering Jul–Dec only, but the annual view shows the netting.
   - If the user wants to double-check the script itself, run `--selftest`.

6. **Present the result:**
   - The method table and the recommended amount
   - The warning that the method is locked for the whole year. Ask what sales they expect in H2.
   - The ficto vs real trade-off: ficto needs a declaración jurada
   - The boleto 2908 steps
   - The open questions (A–F) printed in the report. If the methods differ a lot, recommend confirming A and B with an accountant before paying.
   - The **Optimización de inversiones** box: summarize its 2–3 most relevant tips. The script only prints a tip when the data triggers it (break-even margin vs 20%, sales that earned less than the 2.4% ficto cost, realized losses, loss harvesting or carry-forward, US withholding over 20%, untaxed pre-2026 gains). Add your own context-specific tips in chat, but don't invent numbers.
   - The **Mejores / Peores ventas (top 10)** tables: one row per sale order (broker + date + symbol, lots summed), ranked by fiscal result (31/12/2025 basis for pre-2026 lots). Mention the biggest winner and loser briefly.

## Guardrails

- Never edit files in `inputs/`. They are the evidence.
- Don't invent missing data such as cost basis, open dates or prices. Ask, or leave the field blank and let the report flag it.
- Everything in `<data>` is personal financial data: never publish it or copy it into the skill directory.
- This is a calculation aid, not tax advice. Say so once, briefly.
