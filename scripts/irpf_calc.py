#!/usr/bin/env python3
"""IRPF Uruguay (Cat. I, capital mobiliario) anticipo calculator for foreign brokers.

Reads a normalized events.csv, converts each event to UYU at the BCU rate (USD
billete, code 2225) of the day before it (Decreto 148/007 art. 29 ter), and
computes the anticipo under three methods:
  - ficto:      12% x 20% of sale proceeds  +  12% of dividends/interest/coupons
  - real_orig:  12% x (gains - losses + dividends/interest), original cost basis
  - real_2025:  same, but shares held on 31/12/2025 cost their market value that day
Foreign withholding is credited against each method's tax, capped at 12% of the
income it was withheld from.

Cost of a sale (--cost-method): 'average' (default, art. 29 ter) pools each symbol
across all brokers: the 31/12/2025 holdings at their value that day plus every
later buy, and each sale takes the weighted average cost. 'lot' uses cost_usd /
cost_basis_2025_usd as given on each sale row (the broker's own lot matching).

events.csv columns (header required, extra columns ignored):
  broker, date, type, symbol, open_date, quantity, proceeds_usd, cost_usd,
  cost_basis_2025_usd, amount_usd, notes
  type in {sale, dividend, interest, coupon, wht, buy, holding, split}
  - sale:      proceeds_usd, cost_usd required (broker lot cost, used by 'lot');
               quantity required for 'average'; open_date (YYYY-MM-DD or
               'pre2026') and cost_basis_2025_usd only matter for 'lot'.
  - dividend/interest/coupon: amount_usd = GROSS amount (before withholding).
  - wht:       amount_usd = foreign tax withheld, positive number.
  - buy:       quantity and cost_usd (including commissions). Not taxable.
  - holding:   position on 31/12/2025 (date 2025-12-31): quantity,
               cost_basis_2025_usd (market value) and cost_usd (original cost,
               only for the real_orig reference). Not taxable.
  - split:     quantity = old shares per new share (3 for a 1-for-3 reverse
               split, 0.5 for a 2-for-1 split). Not taxable.
  Rows of the same date are applied in file order, so list them in the order
  they happened.

Usage:
  python3 -I irpf_calc.py events.csv --period "2026-01..2026-06" [--out report.html|report.md]
          [--fx-file rates.csv] [--fx-mode day-before|event|period-end]
          [--cost-method average|lot] [--prior-paid-uyu 0] [--no-wht-credit] [--selftest]
"""

import argparse
import csv
import html
import json
import os
import re
import sys
import urllib.request
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

RATE = Decimal("0.12")
FICTO = Decimal("0.20")
INCOME_TYPES = {"dividend", "interest", "coupon"}
TAXABLE_TYPES = INCOME_TYPES | {"sale", "wht"}
POSITION_TYPES = {"buy", "holding", "split"}  # only feed the average-cost pools
VALID_TYPES = TAXABLE_TYPES | POSITION_TYPES
FRESH_START = date(2026, 1, 1)
BCU_URL = "https://cotizaciones.bcu.gub.uy/wscotizaciones/servlet/awsbcucotizaciones"
BCU_USD_BILLETE = "2225"
FX_LOOKBACK_DAYS = 10


def d(value):
    value = (value or "").strip().replace(",", "")
    return Decimal(value) if value else None


def money(x):
    return f"{x:,.2f}"


# ---------------------------------------------------------------- FX (BCU)

def fetch_bcu(start, end):
    body = (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:cot="Cotiza"><soapenv:Header/><soapenv:Body><cot:wsbcucotizaciones.Execute>'
        f"<cot:Entrada><cot:Moneda><cot:item>{BCU_USD_BILLETE}</cot:item></cot:Moneda>"
        f"<cot:FechaDesde>{start.isoformat()}</cot:FechaDesde>"
        f"<cot:FechaHasta>{end.isoformat()}</cot:FechaHasta>"
        "<cot:Grupo>0</cot:Grupo></cot:Entrada>"
        "</cot:wsbcucotizaciones.Execute></soapenv:Body></soapenv:Envelope>"
    ).encode()
    req = urllib.request.Request(
        BCU_URL, data=body, headers={"Content-Type": "text/xml; charset=utf-8"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        xml = resp.read().decode("utf-8")
    rates = {}
    for fecha, tcc in re.findall(r"<Fecha>([\d-]+)</Fecha>.*?<TCC>([\d.]+)</TCC>", xml, re.S):
        rates[fecha] = tcc
    if not rates and "<codigoerror>0</codigoerror>" not in xml:
        raise RuntimeError(f"BCU error response: {xml[:500]}")
    return rates


class FX:
    """USD->UYU at the BCU rate of the date, or the previous business day."""

    def __init__(self, cache_path=None, fx_file=None, offline=False):
        self.cache_path = cache_path
        self.rates = {}
        # Date ranges already asked to BCU: a day inside one with no rate is a
        # non-business day, so falling back to the previous rate is correct.
        self.fetched = []
        self.offline = offline
        if cache_path and os.path.exists(cache_path):
            with open(cache_path) as f:
                cached = json.load(f)
            self.fetched = [tuple(x) for x in cached.pop("_fetched", [])]
            self.rates.update(cached)
        if fx_file:
            with open(fx_file, newline="") as f:
                for row in csv.DictReader(f):
                    self.rates[row["date"].strip()] = row["rate"].strip()

    def _known(self, day):
        iso = day.isoformat()
        return iso in self.rates or any(s <= iso <= e for s, e in self.fetched)

    def ensure(self, dates):
        # A cached rate from a few days earlier is not enough: the exact day may
        # have its own rate that was never fetched.
        missing = [x for x in dates if not self._known(x)]
        if not missing or self.offline:
            return
        start = min(missing) - timedelta(days=FX_LOOKBACK_DAYS)
        try:
            self.rates.update(fetch_bcu(start, max(missing)))
        except OSError as err:
            if all(self._lookup(x) for x in missing):
                print(f"BCU no responde ({err}); se usan cotizaciones del cache", file=sys.stderr)
                return
            raise
        self.fetched.append((start.isoformat(), max(missing).isoformat()))
        if self.cache_path:
            with open(self.cache_path, "w") as f:
                json.dump({**dict(sorted(self.rates.items())), "_fetched": sorted(self.fetched)}, f, indent=1)

    def _lookup(self, day):
        for back in range(FX_LOOKBACK_DAYS + 1):
            key = (day - timedelta(days=back)).isoformat()
            if key in self.rates:
                return key, Decimal(self.rates[key])
        return None

    def get(self, day):
        hit = self._lookup(day)
        if hit is None:
            raise KeyError(f"No BCU rate for {day} (or {FX_LOOKBACK_DAYS} days before)")
        return hit


# ---------------------------------------------------------------- events

def parse_open_date(value):
    """ISO date, empty (unknown), or 'pre2026' when only the year side is known."""
    value = value.strip().lower()
    if not value:
        return None
    if value == "pre2026":
        return FRESH_START - timedelta(days=1)
    return date.fromisoformat(value)


def load_events(path):
    events, errors = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            t = row.get("type", "").lower()
            if t not in VALID_TYPES:
                errors.append(f"line {n}: unknown type '{t}'")
                continue
            try:
                ev = {
                    "line": n,
                    "broker": row.get("broker", ""),
                    "date": date.fromisoformat(row["date"]),
                    "type": t,
                    "symbol": row.get("symbol", ""),
                    "open_date": parse_open_date(row.get("open_date", "")),
                    "quantity": d(row.get("quantity")),
                    "proceeds": d(row.get("proceeds_usd")),
                    "cost": d(row.get("cost_usd")),
                    "basis2025": d(row.get("cost_basis_2025_usd")),
                    "amount": d(row.get("amount_usd")),
                    "notes": row.get("notes", ""),
                }
            except (ValueError, KeyError, ArithmeticError) as e:
                errors.append(f"line {n}: {e}")
                continue
            if t == "sale" and (ev["proceeds"] is None or ev["cost"] is None):
                errors.append(f"line {n}: sale needs proceeds_usd and cost_usd")
            elif t == "buy" and (ev["quantity"] is None or ev["cost"] is None):
                errors.append(f"line {n}: buy needs quantity and cost_usd")
            elif t == "holding" and (ev["quantity"] is None or ev["basis2025"] is None):
                errors.append(f"line {n}: holding needs quantity and cost_basis_2025_usd")
            elif t == "split" and not ev["quantity"]:
                errors.append(f"line {n}: split needs quantity (old shares per new share)")
            elif t in TAXABLE_TYPES - {"sale"} and ev["amount"] is None:
                errors.append(f"line {n}: {t} needs amount_usd")
            else:
                events.append(ev)
    return events, errors


def apply_average_cost(events):
    """Replace each sale's cost with the weighted average of its symbol's pool.

    One pool per symbol for the whole taxpayer (all brokers), so a transfer between
    brokers changes nothing. Pools start with the 31/12/2025 holdings at their value
    that day (fresh start) and their original cost (real_orig reference).
    """
    warnings, pools = [], {}
    for e in sorted(events, key=lambda e: (e["date"], e["line"])):
        if e["type"] not in POSITION_TYPES | {"sale"}:
            continue
        p = pools.setdefault(e["symbol"].upper(), {"qty": Decimal(0), "orig": Decimal(0), "b2025": Decimal(0)})
        if e["type"] == "holding":
            p["qty"] += e["quantity"]
            p["b2025"] += e["basis2025"]
            p["orig"] += e["cost"] if e["cost"] is not None else e["basis2025"]
            if e["cost"] is None:
                warnings.append(f"line {e['line']} {e['symbol']}: posición al 31/12/2025 sin costo original; "
                                "real_orig usa el valor a esa fecha")
        elif e["type"] == "buy":
            p["qty"] += e["quantity"]
            p["orig"] += e["cost"]
            p["b2025"] += e["cost"]
        elif e["type"] == "split":
            p["qty"] /= e["quantity"]
        else:  # sale
            q = e["quantity"]
            if q is None or q > p["qty"] * Decimal("1.000001") or p["qty"] <= 0:
                why = "sin quantity" if q is None else f"vende {q} y el pool tiene {p['qty']:.6f}"
                warnings.append(f"line {e['line']} {e['symbol']}: {why}; se usa el costo del lote del broker "
                                "(faltan compras o la foto al 31/12/2025)")
                continue
            share = min(q / p["qty"], Decimal(1))
            cost, b2025 = p["orig"] * share, p["b2025"] * share
            e["lot_cost"], e["lot_basis2025"] = e["cost"], e["basis2025"]
            e["cost"], e["basis2025"], e["avg"] = cost, b2025, True
            p["qty"] -= q
            p["orig"] -= cost
            p["b2025"] -= b2025
            if p["qty"] < Decimal("0.000001"):
                p["qty"] = p["orig"] = p["b2025"] = Decimal(0)
    return warnings


def semester_end(day):
    return date(day.year, 6, 30) if day.month <= 6 else date(day.year, 12, 31)


def compute(events, fx, wht_credit=True, fx_mode="day-before", today=None):
    """fx_mode 'day-before' (default): each event at the BCU rate of the day before it,
    as art. 29 ter of Decreto 148/007 sets for sales ("cotización del día anterior al
    de la enajenación"); a non-business day falls back to the previous one.
    'event': the rate of the event's own date. 'period-end': the rate of the
    semester's close (30/06 or 31/12); a semester still open uses the latest rate."""
    today = today or date.today()

    def fx_day(e):
        if fx_mode == "day-before":
            return e["date"] - timedelta(days=1)
        return e["date"] if fx_mode == "event" else min(semester_end(e["date"]), today)

    fx.ensure(sorted({fx_day(e) for e in events}))
    warnings = []
    r = {
        "proceeds_uyu": Decimal(0), "gain_orig_uyu": Decimal(0), "gain_2025_uyu": Decimal(0),
        "income_uyu": Decimal(0), "wht_uyu": Decimal(0), "real_2025_complete": True,
        "by_broker": {}, "fx_mode": fx_mode, "fx_rates": {}, "fx_estimated": set(),
    }
    for e in events:
        fx_date, rate = fx.get(fx_day(e))
        if fx_mode == "period-end":
            end = semester_end(e["date"])
            r["fx_rates"][end] = (fx_date, rate)
            if end > today:
                r["fx_estimated"].add(end)
        e["fx_date"], e["rate"] = fx_date, rate
        b = r["by_broker"].setdefault(e["broker"], {
            "proceeds_usd": Decimal(0), "gain_orig_usd": Decimal(0),
            "income_usd": Decimal(0), "wht_usd": Decimal(0), "rows": 0,
        })
        b["rows"] += 1
        if e["type"] == "sale":
            pre2026 = e["open_date"] is not None and e["open_date"] < FRESH_START
            if e["open_date"] is None and not e.get("avg"):
                warnings.append(f"line {e['line']} {e['symbol']}: no open_date; assumed bought in 2026")
            basis2025 = e["cost"]
            if e.get("avg"):
                basis2025 = e["basis2025"]  # weighted average from apply_average_cost
            elif pre2026:
                if e["basis2025"] is None:
                    r["real_2025_complete"] = False
                    warnings.append(f"line {e['line']} {e['symbol']}: lot opened {e['open_date']} "
                                    "without cost_basis_2025_usd; real_2025 uses original cost")
                else:
                    basis2025 = e["basis2025"]
            e["gain_orig_usd"] = e["proceeds"] - e["cost"]
            e["gain_2025_usd"] = e["proceeds"] - basis2025
            e["proceeds_uyu"] = e["proceeds"] * rate
            r["proceeds_uyu"] += e["proceeds_uyu"]
            r["gain_orig_uyu"] += e["gain_orig_usd"] * rate
            r["gain_2025_uyu"] += e["gain_2025_usd"] * rate
            b["proceeds_usd"] += e["proceeds"]
            b["gain_orig_usd"] += e["gain_orig_usd"]
        elif e["type"] in INCOME_TYPES:
            e["amount_uyu"] = e["amount"] * rate
            r["income_uyu"] += e["amount_uyu"]
            b["income_usd"] += e["amount"]
        else:  # wht
            e["amount_uyu"] = abs(e["amount"]) * rate
            r["wht_uyu"] += e["amount_uyu"]
            b["wht_usd"] += abs(e["amount"])

    income_tax = r["income_uyu"] * RATE
    methods = {}
    methods["ficto"] = {
        "base": r["proceeds_uyu"] * FICTO + r["income_uyu"],
        "tax": r["proceeds_uyu"] * FICTO * RATE + income_tax,
        "carry_forward": Decimal(0),
    }
    for key, gain in (("real_orig", r["gain_orig_uyu"]), ("real_2025", r["gain_2025_uyu"])):
        net = gain + r["income_uyu"]
        methods[key] = {
            "base": net,
            "tax": max(net, Decimal(0)) * RATE,
            "carry_forward": -net if net < 0 else Decimal(0),
        }
    # Foreign tax credit (question B): each withholding offsets at most 12% of the gross
    # income it was withheld from (same broker, date and symbol); the excess is lost.
    gross, withheld = {}, {}
    for e in events:
        key = (e["broker"], e["date"], e["symbol"].upper())
        if e["type"] in INCOME_TYPES:
            gross[key] = gross.get(key, Decimal(0)) + e["amount_uyu"]
        elif e["type"] == "wht":
            withheld[key] = withheld.get(key, Decimal(0)) + e["amount_uyu"]
    credit = Decimal(0)
    for key, wht in withheld.items():
        if key not in gross:
            warnings.append(f"retención {key[0]} {key[1]} {key[2]} sin dividendo/interés con la misma "
                            "fecha y símbolo: no se usó como crédito")
            continue
        credit += min(wht, gross[key] * RATE)
    r["wht_credit_applied"] = wht_credit
    if not wht_credit:
        credit = Decimal(0)
    r["wht_credit_cap_uyu"] = credit
    r["wht_lost_uyu"] = r["wht_uyu"] - credit
    for meth in methods.values():
        # Under real, losses can shrink the tax below the dividends' 12%; never go negative.
        meth["credit"] = min(credit, meth["tax"])
        meth["to_pay"] = meth["tax"] - meth["credit"]
    r["methods"] = methods
    return r, warnings


# ---------------------------------------------------------------- report

def round_uyu(x):
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def period_bounds(period):
    """'2026-01..2026-06' -> (date(2026, 1, 1), date(2026, 6, 30))."""
    m = re.fullmatch(r"\s*(\d{4})-(\d{2})\s*\.\.\s*(\d{4})-(\d{2})\s*", period)
    if not m:
        raise ValueError(f"--period must look like 2026-01..2026-06, got {period!r}")
    y1, m1, y2, m2 = map(int, m.groups())
    end = date(y2 + (m2 == 12), m2 % 12 + 1, 1) - timedelta(days=1)
    return date(y1, m1, 1), end


def boleto_period(period):
    """'2026-01..2026-06' -> 'hasta mes 06/2026'; a period ending in December -> '12/2026'."""
    m = re.search(r"(\d{4})-(\d{2})\s*$", period)
    if not m:
        return "hasta mes 06/<año> (1er anticipo) o 12/<año> (2º)"
    year, month = m.groups()
    return f"12/{year}" if month == "12" else f"hasta mes {month}/{year}"


TOP_N = 10


def group_sales(events):
    """One row per sale order (broker, date, symbol), summing its closed lots."""
    groups = {}
    for e in events:
        if e["type"] != "sale":
            continue
        g = groups.setdefault((e["broker"], e["date"], e["symbol"]), {
            "broker": e["broker"], "date": e["date"], "symbol": e["symbol"], "lots": 0,
            "proceeds": Decimal(0), "basis": Decimal(0), "gain": Decimal(0),
            "gain_uyu": Decimal(0), "first_open": None,
        })
        g["lots"] += 1
        g["proceeds"] += e["proceeds"]
        g["basis"] += e["proceeds"] - e["gain_2025_usd"]
        g["gain"] += e["gain_2025_usd"]
        g["gain_uyu"] += e["gain_2025_usd"] * e["rate"]
        if e["open_date"] and (g["first_open"] is None or e["open_date"] < g["first_open"]):
            g["first_open"] = e["open_date"]
    return list(groups.values())


def sales_table(rows):
    out = ["| # | Fecha | Broker | Símbolo | Lotes | Venta USD | Costo fiscal USD | Resultado USD | % | "
           "Resultado UYU | Efecto IRPF real (12%) |",
           "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for n, g in enumerate(rows, start=1):
        pct = g["gain"] / g["basis"] * 100 if g["basis"] else Decimal(0)
        out.append(f"| {n} | {g['date']} | {g['broker']} | {g['symbol']} | {g['lots']} | "
                   f"{money(g['proceeds'])} | {money(g['basis'])} | **{money(g['gain'])}** | "
                   f"{pct:+.1f}% | {money(g['gain_uyu'])} | {money(g['gain_uyu'] * RATE)} |")
    return out


def optimization_tips(events, r, sales, scope="del período"):
    """Data-driven suggestions; each one only appears when the period's data triggers it."""
    tips = []
    proceeds_usd = sum((g["proceeds"] for g in sales), Decimal(0))
    gain_usd = sum((g["gain"] for g in sales), Decimal(0))
    income_usd = sum((e["amount"] for e in events if e["type"] in INCOME_TYPES), Decimal(0))
    wht_usd = sum((abs(e["amount"]) for e in events if e["type"] == "wht"), Decimal(0))

    if proceeds_usd:
        margin = gain_usd / proceeds_usd * 100
        better = "real" if margin < FICTO * 100 else "ficto"
        tips.append(f"**Margen realizado: {margin:.1f}% del monto vendido.** El punto de equilibrio entre "
                    f"métodos es 20%: por debajo conviene real, por encima ficto. Con este perfil conviene "
                    f"**{better}**. Si en el 2º semestre pensás vender posiciones con mucha ganancia, "
                    "recalculá antes de fijar el método del año.")

    # Under ficto every sale pays 2.4% of proceeds, even with a tiny gain or a loss.
    churn = [g for g in sales if g["gain"] < g["proceeds"] * FICTO * RATE]
    if churn:
        churn_tax = sum((g["proceeds"] * FICTO * RATE for g in churn), Decimal(0))
        short = [g for g in churn if g["first_open"] and (g["date"] - g["first_open"]).days <= 30]
        tips.append(f"**{len(churn)} de {len(sales)} ventas ganaron menos de lo que cuesta el ficto** (2,4% del "
                    f"monto: USD {money(churn_tax)} en total). "
                    + (f"{len(short)} eran posiciones de 30 días o menos. " if short else "")
                    + "Operar seguido con márgenes chicos se come la ganancia en ficto; con menos rotación, "
                    "o con el método real, no pagás impuesto por operaciones que no ganaron.")

    losses = [g for g in sales if g["gain"] < 0]
    if losses:
        loss_uyu = -sum((g["gain_uyu"] for g in losses), Decimal(0))
        tips.append(f"**Pérdidas realizadas: {len(losses)} ventas, {money(loss_uyu)} UYU.** En real compensan "
                    f"ganancias, dividendos e intereses (ahorro de hasta {money(loss_uyu * RATE)} UYU); "
                    "en ficto no se pueden usar.")

    net_real = r["methods"]["real_2025"]["base"]
    if net_real > 0:
        tips.append(f"**Cosecha de pérdidas (método real):** el resultado neto gravado es {money(net_real)} UYU. "
                    "Si tenés posiciones abiertas con pérdida respecto al 31/12/2025 que igual pensás rotar, "
                    "venderlas antes del 31/12 baja el impuesto en el 12% de esa pérdida. Para mantener la "
                    "exposición podés recomprar un activo similar (confirmá con un contador que la DGI lo acepta).")
    elif net_real < 0:
        tips.append(f"**Pérdida neta de {money(-net_real)} UYU (método real)**. Dentro del mismo año podés realizar ganancias por ese monto sin pagar IRPF: "
                    "es buen momento para tomar ganancias de posiciones que ya querías vender. Si sobra al cierre, "
                    "no está confirmado que se pueda trasladar a años siguientes (pregunta I).")

    if income_usd and wht_usd / income_usd > Decimal("0.2"):
        tips.append(f"**Retención de EE.UU.: {wht_usd / income_usd * 100:.0f}% de los dividendos** "
                    f"(USD {money(wht_usd)} de USD {money(income_usd)}), porque Uruguay no tiene tratado con EE.UU. "
                    "El crédito fiscal cubre el 12% de IRPF, pero el 18% restante se pierde. Los ETFs UCITS de acumulación domiciliados en Irlanda (p. ej. CSPX, "
                    "VWRA) retienen 15% dentro del fondo y no reparten dividendos, así que no hay evento gravado hasta "
                    "que vendés. También reducen la exposición al impuesto sucesorio de EE.UU. (aplica a no "
                    "residentes con más de USD 60.000 en activos de EE.UU.).")

    pre_gain = [e for e in events if e["type"] == "sale" and e["basis2025"] is not None
                and e["open_date"] and e["open_date"] < FRESH_START and e["basis2025"] > e["cost"]]
    if pre_gain:
        exempt = sum((e["basis2025"] - e["cost"] for e in pre_gain), Decimal(0))
        tips.append(f"**Ganancia anterior a 2026 no gravada: USD {money(exempt)}** en {len(pre_gain)} lotes vendidos. "
                    "Las posiciones que todavía tenés desde 2025 conservan ese beneficio: guardá el valor al "
                    "31/12/2025 de cada una (extracto de diciembre) para usarlo como costo cuando las vendas.")

    tips.append(f"_Sugerencias generadas a partir de las operaciones {scope}; no son asesoramiento financiero "
                "ni tributario._")
    return tips


def year_table(m, my, labels, prior_paid):
    paid_col = prior_paid > 0
    out = ["| Método | Este período | Resto del año a la fecha | Año a la fecha | "
           + ("Año menos anticipos pagados | " if paid_col else "") + "Pérdida neta (arrastre a confirmar) |",
           "|---|---:|---:|---:|" + ("---:|" if paid_col else "") + "---:|"]
    for k in ("ficto", "real_2025"):
        rest = my[k]["to_pay"] - m[k]["to_pay"]
        net = f"{round_uyu(max(my[k]['to_pay'] - prior_paid, Decimal(0))):,} | " if paid_col else ""
        out.append(f"| {labels[k]} | {round_uyu(m[k]['to_pay']):,} | {round_uyu(rest):,} | "
                   f"**{round_uyu(my[k]['to_pay']):,}** | {net}{money(my[k]['carry_forward'])} |")
    out += ["", "_Impuesto a pagar en UYU, ya descontado el crédito por retenciones. En real, el año compensa "
            "ganancias y pérdidas de todos los meses, así que el resto del año puede ser negativo: significa que "
            "las pérdidas de esos meses bajan el total anual._"]
    if paid_col:
        out += ["", f"_Anticipos ya pagados este año: {money(prior_paid)} UYU._"]
    return out


def fx_note(r):
    if r["fx_mode"] == "day-before":
        return ("_Tipo de cambio: BCU dólar billete del día anterior a cada evento, o el hábil previo "
                "(Decreto 148/007 art. 29 ter, pregunta E)._")
    if r["fx_mode"] == "event":
        return "_Tipo de cambio: BCU dólar billete de la fecha de cada evento (`--fx-mode event`)._"
    parts = []
    for end, (fx_date, rate) in sorted(r["fx_rates"].items()):
        if end in r["fx_estimated"]:
            parts.append(f"cierre {end:%d/%m/%Y}: **todavía no existe**, se usó el último disponible "
                         f"({rate} del {fx_date}) ⚠️ estimado")
        else:
            parts.append(f"cierre {end:%d/%m/%Y}: {rate} (BCU del {fx_date})")
    return ("_Tipo de cambio: todos los montos de cada semestre se convierten al BCU dólar billete del cierre "
            "del semestre (pregunta E) — " + "; ".join(parts) + "._")


def questions_section(questions, decisions, warnings):
    """Split the open questions into the ones the user already decided and the rest."""
    decided, still_open, letters = [], [], set()
    for q in questions:
        letter = re.match(r"- \*\*([A-Z])\.\*\*", q).group(1)
        letters.add(letter)
        d = decisions.get(letter)
        if d:
            source = ", ".join(x for x in (d.get("fuente"), d.get("fecha")) if x)
            decided.append(f"- **{letter}.** {d['decision']}" + (f" _({source})_" if source else ""))
        else:
            still_open.append(q)
    for letter in sorted(set(decisions) - letters):
        warnings.append(f"decisiones.json: no existe la pregunta {letter}")
    out = []
    if decided:
        out += ["", "## Decisiones tomadas", ""] + decided
    if still_open:
        out += ["", "## Preguntas abiertas para confirmar con un contador", ""] + still_open
    return out


def report(events, r, warnings, period, prior_paid, year=None, decisions=None):
    """year: None, or (year_events, year_result, first_day, last_day) for the year-to-date view.
    decisions: {letter: {"decision", "fecha", "fuente"}} the user settled (decisiones.json)."""
    m = r["methods"]
    my = year[1]["methods"] if year else None
    if year:
        scope_events, scope_r = year[0], year[1]
        scope = f"del {year[2]:%d/%m/%Y} al {year[3]:%d/%m/%Y}"
    else:
        scope_events, scope_r, scope = events, r, "del período"
    out = [f"# Anticipo IRPF — período {period}", ""]
    out += ["## Resultado", "",
            "| Método | Base imponible (UYU) | Impuesto (UYU) | Crédito retenciones exterior | "
            "A pagar (redondeado) | Pérdida neta (arrastre a confirmar) |",
            "|---|---:|---:|---:|---:|---:|"]
    labels = {
        "ficto": "Ficto (2,4% ventas + 12% rendimientos)",
        "real_orig": "Real — costo original (solo referencia)",
        "real_2025": "Real — costo = valor 31/12/2025" + ("" if r["real_2025_complete"] else " ⚠️ incompleto"),
    }
    # With a year view, prior anticipos are netted against the year (see year_table),
    # not against this period alone.
    period_paid = Decimal(0) if year else prior_paid
    for k, label in labels.items():
        tax = max(m[k]["to_pay"] - period_paid, Decimal(0))
        out.append(f"| {label} | {money(m[k]['base'])} | {money(m[k]['tax'])} | {money(-m[k]['credit']) if m[k]['credit'] else money(0)} | "
                   f"**{round_uyu(tax):,}** | {money(m[k]['carry_forward'])} |")
    if period_paid:
        out += ["", f"_A pagar descuenta anticipos previos: {money(period_paid)} UYU._"]
    if r["wht_credit_applied"]:
        out += ["", "_A pagar descuenta el crédito por impuestos retenidos en el exterior: cada retención hasta el 12% "
                "del dividendo del que se retuvo (pregunta B)._"]
    else:
        out += ["", "_Crédito por retenciones del exterior **no aplicado** (`--no-wht-credit`): se recupera en la "
                "declaración jurada anual (pregunta B)._"]
    out += ["", fx_note(year[1] if year else r)]

    # Gains (and losses) accrued up to 31/12/2025 are outside IRPF, so pre-2026 lots
    # must use their 31/12/2025 value: real_orig is never a valid choice.
    candidates = ["ficto", "real_2025"]
    best = min(candidates, key=lambda k: m[k]["to_pay"])
    if not (scope_r if year else r)["real_2025_complete"]:
        warnings.append("Falta valor al 31/12/2025 de algún lote anterior a 2026: real_2025 está incompleto")

    if year:
        out += ["", f"## Vista del año a la fecha ({scope})", "",
                "El método se elige una vez para todo el año, así que la comparación que importa es la anual."]
        out += [""] + year_table(m, my, labels, prior_paid)
        best_year = min(candidates, key=lambda k: my[k]["to_pay"])
        pay = round_uyu(m[best_year]["to_pay"])
        lines = [f"En el año a la fecha conviene **{labels[best_year]}** "
                 f"({round_uyu(my[best_year]['to_pay']):,} UYU en el año). "
                 f"Con ese método, este anticipo es **{pay:,} UYU**.", ""]
        if prior_paid:
            net = round_uyu(max(my[best_year]["to_pay"] - prior_paid, Decimal(0)))
            lines += [f"- Ese monto cubre solo las operaciones del período. Con compensación anual (año a la fecha "
                      f"menos los {money(prior_paid)} UYU ya pagados) serían **{net:,} UYU**. "
                      "Confirmá con un contador cuál corresponde.", ""]
        if best_year != best:
            lines += [f"- ⚠️ Mirando solo este período convendría **{labels[best]}**, pero las operaciones del resto "
                      "del año dan vuelta la comparación. Como el método no se puede cambiar, se recomienda el anual.", ""]
        lines += ["- Las operaciones de acá a fin de año todavía pueden cambiar la comparación: "
                  "recalculá antes de cada anticipo."]
    else:
        lines = [f"Menor impuesto en este período: **{labels[best]}** → "
                 f"**{round_uyu(max(m[best]['to_pay'] - prior_paid, Decimal(0))):,} UYU**.", "",
                 "- El método elegido **debe mantenerse todo el año** (el anticipo de julio–diciembre usa el mismo). "
                 "Pensá qué ventas vas a hacer en el segundo semestre antes de elegir."]
    out += ["", "## Recomendación", ""] + lines + [
            "- **Ficto** requiere declaración jurada al cierre del año con documentación. "
            "**Real** con los dos anticipos queda como definitivo (confirmalo con un contador, ver pregunta B).",
            "- Ventas con pérdida solo ayudan en el método real; en ficto se tributa sobre el 20% del monto vendido igual.",
            "- Los dividendos con retención en el exterior y el crédito aplicado **deben figurar en la declaración "
            "jurada anual**, aunque el saldo por ese concepto sea 0.",
            "",
            "**Cómo pagar:** DGI → Servicios en línea → *Boleto 2908 – generación, impresión y pago* → "
            f"RUT = tu cédula → código de impuesto **119** → período **{boleto_period(period)}** "
            "→ importe en pesos → pagar online.", ""]

    out += [f"## Totales del período {period}", "",
            f"- Ventas (precio de venta): {money(r['proceeds_uyu'])} UYU",
            f"- Resultado de ventas, costo original: {money(r['gain_orig_uyu'])} UYU",
            f"- Resultado de ventas, costo 31/12/2025: {money(r['gain_2025_uyu'])} UYU",
            f"- Dividendos + intereses + cupones (brutos): {money(r['income_uyu'])} UYU",
            f"- Retenciones en el exterior: {money(r['wht_uyu'])} UYU "
            + (f"→ crédito aplicable {money(r['wht_credit_cap_uyu'])} UYU; el excedente de {money(r['wht_lost_uyu'])} UYU "
             "se pierde (no se reintegra ni descuenta otros impuestos)" if r["wht_credit_applied"]
             else "→ crédito no aplicado en este cálculo"),
            ""]

    sales = group_sales(scope_events)
    out += [f"## Optimización de inversiones ({scope})", ""]
    out += [f"- {t}" for t in optimization_tips(scope_events, scope_r, sales, scope)] + [""]
    if sales:
        note = ("_Una fila por orden de venta (lotes sumados). Costo fiscal y resultado usan el valor al "
                "31/12/2025 para lotes anteriores a 2026._")
        best = sorted((g for g in sales if g["gain"] > 0), key=lambda g: g["gain"], reverse=True)[:TOP_N]
        worst = sorted((g for g in sales if g["gain"] < 0), key=lambda g: g["gain"])[:TOP_N]
        out += [f"## Mejores ventas (top {TOP_N}, {scope})", "", note, ""]
        out += (sales_table(best) if best else ["Ninguna venta con ganancia."]) + [""]
        out += [f"## Peores ventas (top {TOP_N}, {scope})", "", note, ""]
        out += (sales_table(worst) if worst else ["Ninguna venta con pérdida."]) + [""]

    out += [f"## Por broker (USD {scope}, para conciliar con el extracto)", "",
            "| Broker | Filas | Ventas | Resultado ventas (costo orig.) | Rendimientos brutos | Retenciones |",
            "|---|---:|---:|---:|---:|---:|"]
    for name, b in sorted(scope_r["by_broker"].items()):
        out.append(f"| {name} | {b['rows']} | {money(b['proceeds_usd'])} | {money(b['gain_orig_usd'])} | "
                   f"{money(b['income_usd'])} | {money(b['wht_usd'])} |")

    out += ["", f"## Detalle por evento ({scope})", "",
            "| # | Broker | Fecha | Tipo | Símbolo | USD | Resultado USD (orig / 2025) | TC BCU (fecha) | UYU | Notas |",
            "|---:|---|---|---|---|---:|---:|---|---:|---|"]
    for e in sorted(scope_events, key=lambda e: (e["date"], e["broker"])):
        if e["type"] == "sale":
            usd, uyu = e["proceeds"], e["proceeds_uyu"]
            res = f"{money(e['gain_orig_usd'])} / {money(e['gain_2025_usd'])}"
        else:
            usd, uyu, res = e["amount"], e["amount_uyu"], ""
        out.append(f"| {e['line']} | {e['broker']} | {e['date']} | {e['type']} | {e['symbol']} | "
                   f"{money(usd)} | {res} | {e['rate']} ({e['fx_date']}) | {money(uyu)} | {e['notes']} |")

    if warnings:
        out += ["", "## Advertencias", ""] + [f"- {w}" for w in warnings]

    questions = [
            "- **A.** (Según el decreto) Activos cotizantes comprados antes de 2026: costo fiscal = cotización al 31/12/2025 "
            "(art. 29 ter, obligatorio). La rentabilidad hasta esa fecha no está gravada, y las pérdidas previas tampoco "
            "se computan. Confirmar el tratamiento de activos que no cotizan.",
            "- **B.** (Criterio aplicado) Las retenciones del exterior se descuentan como crédito fiscal, hasta el 12% de "
            "IRPF de cada dividendo; el excedente se pierde. Dividendos y crédito van en la declaración jurada anual. "
            "Confirmar si el crédito puede descontarse ya en el anticipo o solo en la declaración jurada "
            "(en ese caso, recalcular con `--no-wht-credit`).",
            "- **C.** (Según el decreto) Sin intermediario local que retenga, la opción ficto/real es una sola por "
            "año para todas las rentas; el criterio por responsable aplica solo a quienes retienen (art. 44 quater).",
            "- **D.** ¿El importe del boleto se redondea o se trunca? (se redondeó al peso más cercano)",
            {"day-before": "- **E.** (Según el decreto) Montos en USD convertidos al TC BCU del día anterior a cada "
                           "operación (art. 29 ter). Pendiente: el decreto lo dice para las ventas; para dividendos e "
                           "intereses se aplicó el mismo criterio. Con `--fx-mode period-end` o `event`, para comparar.",
             "event": "- **E.** Montos en USD convertidos al TC BCU de la fecha de cada evento (`--fx-mode event`). "
                      "El decreto (art. 29 ter) indica el del día anterior a la operación.",
             "period-end": "- **E.** Montos en USD convertidos al TC BCU del cierre de cada semestre "
                           "(`--fx-mode period-end`). El decreto (art. 29 ter) indica el del día anterior a la "
                           "operación."}[r["fx_mode"]],
            "- **F.** (Criterio aplicado) ETFs que replican cripto (IBIT, ETHA): se tratan como activo financiero alcanzado, "
            "tanto sus pérdidas como sus ganancias. La normativa no menciona criptoactivos: el tratamiento de la cripto "
            "tenida directamente (aquí excluida) también está sin confirmar.",
            ("- **G.** (Según el decreto) Costo fiscal por promedio ponderado de las compras de bienes idénticos "
             "(art. 29 ter), con las tenencias al 31/12/2025 a su valor a esa fecha. Se promedió por contribuyente, "
             "sumando todos los brokers; confirmar si corresponde promediar por cuenta." if r.get("cost_method") == "average"
             else "- **G.** Costo de cada venta según el lote que asignó el broker (`--cost-method lot`). El decreto "
                  "(art. 29 ter) indica promedio ponderado."),
            "- **H.** Comisiones: se sumaron al costo de compra y se restaron del precio de venta; los gastos de "
            "transferencia, retiro e intereses deudores no se dedujeron. La normativa no lo detalla.",
            "- **I.** Arrastre de pérdidas a ejercicios siguientes: la reglamentación revisada no lo menciona "
            "(la columna \"Pérdida\" es informativa).",
    ]
    out += questions_section(questions, decisions or {}, warnings)
    out += ["", "_Este cálculo es una ayuda, no asesoramiento tributario._", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

HTML_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1f2328;--muted:#656d76;--line:#d8dee4;--accent:#0b6e4f;--accent-bg:#e6f4ee;--warn-bg:#fff8e1;--info:#1f5fbf;--info-bg:#eaf1fb;--neg:#b42318}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--fg:#e6e6e6;--muted:#9aa4b2;--line:#2c313a;--accent:#4ccb9a;--accent-bg:#13261f;--warn-bg:#2a2414;--info:#7fb0ff;--info-bg:#141d2b;--neg:#ff8a7a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 24px}
h2{font-size:18px;margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:4px 20px 16px;margin-bottom:20px}
section.resultado,section.recomendación{border-color:var(--accent)}
section.recomendación{background:var(--accent-bg)}
section.advertencias,section.preguntas{background:var(--warn-bg)}
section.decisiones{border-color:var(--accent)}
section.optimización{border-color:var(--info);background:var(--info-bg)}
section.optimización strong{color:var(--info)}
section.optimización li{margin-bottom:8px}
section.mejores{border-left:4px solid var(--accent)}
section.peores{border-left:4px solid var(--neg)}
section.peores strong{color:var(--neg)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap}
td.r,th.r{text-align:right;white-space:nowrap}
tbody tr:hover{background:color-mix(in srgb,var(--accent) 7%,transparent)}
strong{color:var(--accent)}
ul{padding-left:20px}
code{font-size:13px}
.meta{color:var(--muted);font-size:13px;margin-top:-16px}
"""


def _inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", text)


def to_html(md, title):
    """Render the report's small Markdown subset (headings, tables, lists, paragraphs)."""
    out, lines, i = [], md.splitlines(), 0
    in_section = False
    while i < len(lines):
        line = lines[i]
        if line.startswith("# "):
            out.append(f"<h1>{_inline(line[2:])}</h1>")
            out.append(f'<p class="meta">Generado {date.today().isoformat()} · '
                       "TC BCU dólar billete (2225)</p>")
        elif line.startswith("## "):
            if in_section:
                out.append("</section>")
            heading = line[3:]
            cls = heading.split()[0].lower()
            out.append(f'<section class="{html.escape(cls)}"><h2>{_inline(heading)}</h2>')
            in_section = True
        elif line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            right = [c.endswith(":") for c in block[1]] if len(block) > 1 else []
            cell = lambda tag, k, v: (f'<{tag} class="r">' if k < len(right) and right[k] else f"<{tag}>") \
                + _inline(v) + f"</{tag}>"
            out.append('<div class="scroll"><table><thead><tr>'
                       + "".join(cell("th", k, v) for k, v in enumerate(block[0])) + "</tr></thead><tbody>")
            for row in block[2:]:
                out.append("<tr>" + "".join(cell("td", k, v) for k, v in enumerate(row)) + "</tr>")
            out.append("</tbody></table></div>")
            continue
        elif line.startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].startswith("- "):
                out.append(f"<li>{_inline(lines[i][2:])}</li>")
                i += 1
            out.append("</ul>")
            continue
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")
        i += 1
    if in_section:
        out.append("</section>")
    return ("<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(title)}</title><style>{HTML_CSS}</style></head>"
            f"<body><main>{''.join(out)}</main></body></html>")


# ---------------------------------------------------------------- selftest

def selftest():
    fx = FX(offline=True)
    fx.rates = {"2026-06-30": "40.116", "2026-03-02": "1", "2026-03-03": "1"}
    jun30, mar = date(2026, 6, 30), date(2026, 3, 2)

    def run(evs):
        for i, e in enumerate(evs):
            e.setdefault("line", i + 2)
            e.setdefault("broker", "t")
            e.setdefault("symbol", "X")
            e.setdefault("open_date", date(2026, 2, 1))
            e.setdefault("basis2025", None)
        return compute(evs, fx, fx_mode="event")[0]["methods"]

    # Example: buy 100 sell 200 -> real 12, ficto 4.8
    m = run([{"date": mar, "type": "sale", "proceeds": Decimal(200), "cost": Decimal(100)}])
    assert m["real_orig"]["tax"] == Decimal("12"), m
    assert m["ficto"]["tax"] == Decimal("4.8"), m
    # Example: +10 and -10 net to zero
    m = run([{"date": mar, "type": "sale", "proceeds": Decimal(20), "cost": Decimal(10)},
             {"date": mar, "type": "sale", "proceeds": Decimal(10), "cost": Decimal(20)}])
    assert m["real_orig"]["tax"] == 0, m
    # Loss offsets dividend, remainder carries forward
    m = run([{"date": mar, "type": "sale", "proceeds": Decimal(50), "cost": Decimal(100)},
             {"date": mar, "type": "dividend", "amount": Decimal(20)}])
    assert m["real_orig"]["tax"] == 0 and m["real_orig"]["carry_forward"] == Decimal(30), m
    # Example: USD 100 net gain on 30/06/2026 -> 12 USD x 40.116 = 481.392
    m = run([{"date": jun30, "type": "sale", "proceeds": Decimal(200), "cost": Decimal(100)}])
    assert m["real_orig"]["tax"] == Decimal("481.392"), m
    assert round_uyu(m["real_orig"]["tax"]) == 481
    # Weekend falls back to previous business day
    assert fx.get(date(2026, 3, 4))[0] == "2026-03-03"
    # Pre-2026 lot uses 31/12/2025 basis in real_2025
    m = run([{"date": mar, "type": "sale", "proceeds": Decimal(200), "cost": Decimal(50),
              "open_date": date(2024, 5, 1), "basis2025": Decimal(180)}])
    assert m["real_orig"]["tax"] == Decimal("18") and m["real_2025"]["tax"] == Decimal("2.4"), m
    # 30% US withholding: credit capped at 12% of that dividend, excess lost
    m = run([{"date": mar, "type": "dividend", "amount": Decimal(100)},
             {"date": mar, "type": "wht", "amount": Decimal(30)},
             {"date": mar, "type": "interest", "amount": Decimal(10), "symbol": "USD"}])
    assert m["ficto"]["credit"] == Decimal(12) and m["ficto"]["to_pay"] == Decimal("1.2"), m
    # Real with losses: credit never exceeds the tax
    m = run([{"date": mar, "type": "sale", "proceeds": Decimal(50), "cost": Decimal(140)},
             {"date": mar, "type": "dividend", "amount": Decimal(100)},
             {"date": mar, "type": "wht", "amount": Decimal(30)}])
    assert m["real_orig"]["tax"] == Decimal("1.2") and m["real_orig"]["to_pay"] == 0, m
    # Period parsing, including a December end
    assert period_bounds("2026-01..2026-06") == (date(2026, 1, 1), jun30)
    assert period_bounds("2026-07..2026-12") == (date(2026, 7, 1), date(2026, 12, 31))
    # A cached rate from 26/06 must not stand in for an unfetched 30/06
    probe = FX(offline=True)
    probe.rates = {"2026-06-26": "40.0"}
    assert not probe._known(date(2026, 6, 30))
    probe.fetched = [("2026-06-20", "2026-06-30")]
    assert probe._known(date(2026, 6, 28))
    # Period-end FX: a March sale is converted at the 30/06 rate (40.116), not March's (1)
    evs = [{"date": mar, "type": "sale", "proceeds": Decimal(200), "cost": Decimal(100), "line": 2,
            "broker": "t", "symbol": "X", "open_date": date(2026, 2, 1), "basis2025": None}]
    m = compute(evs, fx, fx_mode="period-end", today=date(2026, 10, 21))[0]["methods"]
    assert m["real_orig"]["tax"] == Decimal("481.392"), m
    # Day-before FX: a sale on 03/03 uses the 02/03 rate
    evs = [{"date": date(2026, 3, 3), "type": "sale", "proceeds": Decimal(200), "cost": Decimal(100), "line": 2,
            "broker": "t", "symbol": "X", "open_date": date(2026, 2, 1), "basis2025": None}]
    compute(evs, fx, today=date(2026, 10, 21))
    assert evs[0]["fx_date"] == "2026-03-02", evs[0]

    # Weighted average across brokers: 10 held on 31/12/2025 worth 100 each (cost 80),
    # 10 bought at 120 in another broker; selling 5 costs the average 110 (orig 100).
    def pos(t, q, cost=None, b25=None, line=0, broker="A", day=mar, proceeds=None):
        return {"type": t, "quantity": Decimal(q), "cost": cost, "basis2025": b25, "line": line,
                "broker": broker, "symbol": "Y", "date": day, "open_date": None, "proceeds": proceeds}
    evs = [pos("holding", 10, Decimal(800), Decimal(1000), 1, day=date(2025, 12, 31)),
           pos("buy", 10, Decimal(1200), None, 2, broker="B"),
           pos("sale", 5, Decimal(400), Decimal(500), 3, proceeds=Decimal(700))]
    assert not apply_average_cost(evs)
    assert evs[2]["basis2025"] == Decimal(550) and evs[2]["cost"] == Decimal(500), evs[2]
    # A 1-for-2 reverse split halves the shares, keeps the cost
    evs = [pos("buy", 10, Decimal(1000), None, 1), pos("split", 2, line=2),
           pos("sale", 5, Decimal(0), None, 3, proceeds=Decimal(1500))]
    assert not apply_average_cost(evs) and evs[2]["cost"] == Decimal(1000), evs[2]
    # Selling more than the pool falls back to the broker's lot cost, with a warning
    evs = [pos("buy", 1, Decimal(100), None, 1), pos("sale", 5, Decimal(400), None, 2, proceeds=Decimal(600))]
    assert apply_average_cost(evs) and evs[1]["cost"] == Decimal(400) and not evs[1].get("avg")
    # A settled question moves from "Preguntas abiertas" to "Decisiones tomadas"
    w = []
    out = questions_section(["- **A.** x", "- **B.** y"], {"B": {"decision": "Sí", "fecha": "2026-10-21"}}, w)
    assert out.index("## Decisiones tomadas") < out.index("## Preguntas abiertas para confirmar con un contador")
    assert "- **B.** Sí _(2026-10-21)_" in out and "- **B.** y" not in out and not w
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("events", nargs="?")
    ap.add_argument("--period", default="2026-01..2026-06")
    ap.add_argument("--out")
    ap.add_argument("--fx-file", help="CSV with columns date,rate to override/skip BCU")
    ap.add_argument("--fx-cache", help="default: fx_cache.json next to events.csv")
    ap.add_argument("--prior-paid-uyu", default="0", help="anticipos already paid this year")
    ap.add_argument("--fx-mode", choices=["day-before", "event", "period-end"], default="day-before",
                    help="BCU rate of the day before each event (default, art. 29 ter), of its own date, "
                         "or of the semester's close (question E)")
    ap.add_argument("--cost-method", choices=["average", "lot"], default="average",
                    help="weighted average per symbol across brokers (default, art. 29 ter) "
                         "or each broker's own lot cost (question G)")
    ap.add_argument("--no-wht-credit", action="store_true",
                    help="do not credit foreign withholding in this anticipo (question B)")
    ap.add_argument("--decisions", help="JSON of settled open questions; default: decisiones.json next to events.csv")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if not args.events:
        ap.error("events.csv is required")

    events, errors = load_events(args.events)
    if errors:
        print("Errors in events.csv:\n  " + "\n  ".join(errors), file=sys.stderr)
        sys.exit(1)
    if not events:
        print("events.csv has no events", file=sys.stderr)
        sys.exit(1)
    start, end = period_bounds(args.period)
    # Average cost needs every buy and the 31/12/2025 holdings, so it runs on the
    # whole file before any filtering.
    cost_warnings = apply_average_cost(events) if args.cost_method == "average" else []
    if args.cost_method == "average" and not any(e["type"] in POSITION_TYPES for e in events):
        cost_warnings.append("events.csv no tiene filas buy/holding: el promedio ponderado no se pudo "
                             "calcular y se usó el costo de cada lote")
    taxable = [e for e in events if e["type"] in TAXABLE_TYPES]
    # events.csv may hold the whole year to date: the anticipo uses the period, and
    # the method comparison uses the year, because the method is fixed for the year.
    period_events = [e for e in taxable if start <= e["date"] <= end]
    year_events = [e for e in taxable if e["date"].year == start.year]
    if not period_events:
        print(f"events.csv has no events in {args.period}", file=sys.stderr)
        sys.exit(1)
    cache = args.fx_cache or os.path.join(os.path.dirname(os.path.abspath(args.events)), "fx_cache.json")
    fx = FX(cache_path=cache, fx_file=args.fx_file)
    credit = not args.no_wht_credit
    r, warnings = compute(period_events, fx, wht_credit=credit, fx_mode=args.fx_mode)
    year = None
    if len(year_events) > len(period_events):
        ry, warnings = compute(year_events, fx, wht_credit=credit, fx_mode=args.fx_mode)
        year = (year_events, ry, date(start.year, 1, 1), max(e["date"] for e in year_events))
    warnings = cost_warnings + warnings
    r["cost_method"] = args.cost_method
    ignored = len(taxable) - len(year_events)
    if ignored:
        warnings.append(f"{ignored} eventos de otros años en events.csv: no se usaron")
    decisions_path = args.decisions or os.path.join(os.path.dirname(os.path.abspath(args.events)), "decisiones.json")
    decisions = {}
    if os.path.exists(decisions_path):
        with open(decisions_path, encoding="utf-8") as f:
            decisions = {k.upper(): v for k, v in json.load(f).items()}
    if decisions.get("B") and args.no_wht_credit:
        warnings.append("decisiones.json dice que el crédito se descuenta (B), pero se usó --no-wht-credit")
    text = report(period_events, r, warnings, args.period, Decimal(args.prior_paid_uyu), year, decisions)
    if args.out:
        if args.out.endswith(".html"):
            content = to_html(text, f"Anticipo IRPF {args.period}")
        else:
            content = text
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Report written to {args.out}")
    print(text)


if __name__ == "__main__":
    main()
