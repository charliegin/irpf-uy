#!/usr/bin/env python3
"""IRPF Uruguay (Cat. I, capital mobiliario) anticipo calculator for foreign brokers.

Reads a normalized events.csv, converts each event to UYU at the BCU rate of its
date (USD billete, code 2225), and computes the anticipo under three methods:
  - ficto:      12% x 20% of sale proceeds  +  12% of dividends/interest/coupons
  - real_orig:  12% x (gains - losses + dividends/interest), original cost basis
  - real_2025:  same, but pre-2026 lots use their 31/12/2025 market value as cost
Foreign withholding is credited against each method's tax, capped at 12% of the
income it was withheld from.

events.csv columns (header required, extra columns ignored):
  broker, date, type, symbol, open_date, proceeds_usd, cost_usd,
  cost_basis_2025_usd, amount_usd, notes
  type in {sale, dividend, interest, coupon, wht}
  - sale:      proceeds_usd, cost_usd required; open_date (YYYY-MM-DD, or
               'pre2026' if only that is known) tells if the lot predates
               2026; cost_basis_2025_usd optional.
  - dividend/interest/coupon: amount_usd = GROSS amount (before withholding).
  - wht:       amount_usd = foreign tax withheld, positive number.

Usage:
  python3 -I irpf_calc.py events.csv --period "2026-01..2026-06" [--out report.html|report.md]
          [--fx-file rates.csv] [--prior-paid-uyu 0] [--no-wht-credit] [--selftest]
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
VALID_TYPES = INCOME_TYPES | {"sale", "wht"}
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
        self.offline = offline
        if cache_path and os.path.exists(cache_path):
            with open(cache_path) as f:
                self.rates.update(json.load(f))
        if fx_file:
            with open(fx_file, newline="") as f:
                for row in csv.DictReader(f):
                    self.rates[row["date"].strip()] = row["rate"].strip()

    def ensure(self, dates):
        missing = [x for x in dates if self._lookup(x) is None]
        if not missing or self.offline:
            return
        start = min(missing) - timedelta(days=FX_LOOKBACK_DAYS)
        self.rates.update(fetch_bcu(start, max(missing)))
        if self.cache_path:
            with open(self.cache_path, "w") as f:
                json.dump(dict(sorted(self.rates.items())), f, indent=1)

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
            elif t != "sale" and ev["amount"] is None:
                errors.append(f"line {n}: {t} needs amount_usd")
            else:
                events.append(ev)
    return events, errors


def compute(events, fx, wht_credit=True):
    fx.ensure(sorted({e["date"] for e in events}))
    warnings = []
    r = {
        "proceeds_uyu": Decimal(0), "gain_orig_uyu": Decimal(0), "gain_2025_uyu": Decimal(0),
        "income_uyu": Decimal(0), "wht_uyu": Decimal(0), "real_2025_complete": True,
        "by_broker": {},
    }
    for e in events:
        fx_date, rate = fx.get(e["date"])
        e["fx_date"], e["rate"] = fx_date, rate
        b = r["by_broker"].setdefault(e["broker"], {
            "proceeds_usd": Decimal(0), "gain_orig_usd": Decimal(0),
            "income_usd": Decimal(0), "wht_usd": Decimal(0), "rows": 0,
        })
        b["rows"] += 1
        if e["type"] == "sale":
            pre2026 = e["open_date"] is not None and e["open_date"] < FRESH_START
            if e["open_date"] is None:
                warnings.append(f"line {e['line']} {e['symbol']}: no open_date; assumed bought in 2026")
            basis2025 = e["cost"]
            if pre2026:
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


def optimization_tips(events, r, sales):
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
        tips.append(f"**Pérdida neta de {money(-net_real)} UYU (método real)**, que se traslada 2 años: "
                    "podés realizar ganancias por ese monto sin pagar IRPF. Es buen momento para tomar ganancias "
                    "de posiciones que ya querías vender.")

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

    tips.append("_Sugerencias generadas a partir de las operaciones del período; no son asesoramiento financiero "
                "ni tributario._")
    return tips


def report(events, r, warnings, period, prior_paid):
    m = r["methods"]
    out = [f"# Anticipo IRPF — período {period}", ""]
    out += ["## Resultado", "",
            "| Método | Base imponible (UYU) | Impuesto (UYU) | Crédito retenciones exterior | "
            "A pagar (redondeado) | Pérdida a trasladar |",
            "|---|---:|---:|---:|---:|---:|"]
    labels = {
        "ficto": "Ficto (2,4% ventas + 12% rendimientos)",
        "real_orig": "Real — costo original (solo referencia)",
        "real_2025": "Real — costo = valor 31/12/2025" + ("" if r["real_2025_complete"] else " ⚠️ incompleto"),
    }
    for k, label in labels.items():
        tax = max(m[k]["to_pay"] - prior_paid, Decimal(0))
        out.append(f"| {label} | {money(m[k]['base'])} | {money(m[k]['tax'])} | {money(-m[k]['credit']) if m[k]['credit'] else money(0)} | "
                   f"**{round_uyu(tax):,}** | {money(m[k]['carry_forward'])} |")
    if prior_paid:
        out += ["", f"_A pagar descuenta anticipos previos: {money(prior_paid)} UYU._"]
    if r["wht_credit_applied"]:
        out += ["", "_A pagar descuenta el crédito por impuestos retenidos en el exterior: cada retención hasta el 12% "
                "del dividendo del que se retuvo (pregunta B)._"]
    else:
        out += ["", "_Crédito por retenciones del exterior **no aplicado** (`--no-wht-credit`): se recupera en la "
                "declaración jurada anual (pregunta B)._"]

    # Gains (and losses) accrued up to 31/12/2025 are outside IRPF, so pre-2026 lots
    # must use their 31/12/2025 value: real_orig is never a valid choice.
    candidates = ["ficto", "real_2025"]
    best = min(candidates, key=lambda k: m[k]["to_pay"])
    if not r["real_2025_complete"]:
        warnings.append("Falta valor al 31/12/2025 de algún lote anterior a 2026: real_2025 está incompleto")
    out += ["", "## Recomendación", "",
            f"Menor impuesto en este período: **{labels[best]}** → "
            f"**{round_uyu(max(m[best]['to_pay'] - prior_paid, Decimal(0))):,} UYU**.", "",
            "- El método elegido **debe mantenerse todo el año** (el anticipo de julio–diciembre usa el mismo). "
            "Pensá qué ventas vas a hacer en el segundo semestre antes de elegir.",
            "- **Ficto** requiere declaración jurada al cierre del año con documentación. "
            "**Real** con los dos anticipos queda como definitivo (confirmalo con un contador, ver pregunta B).",
            "- Ventas con pérdida solo ayudan en el método real; en ficto se tributa sobre el 20% del monto vendido igual.",
            "- Los dividendos con retención en el exterior y el crédito aplicado **deben figurar en la declaración "
            "jurada anual**, aunque el saldo por ese concepto sea 0.",
            "",
            "**Cómo pagar:** DGI → Servicios en línea → *Boleto 2908 – generación, impresión y pago* → "
            f"RUT = tu cédula → código de impuesto **119** → período **{boleto_period(period)}** "
            "→ importe en pesos → pagar online.", ""]

    out += ["## Totales", "",
            f"- Ventas (precio de venta): {money(r['proceeds_uyu'])} UYU",
            f"- Resultado de ventas, costo original: {money(r['gain_orig_uyu'])} UYU",
            f"- Resultado de ventas, costo 31/12/2025: {money(r['gain_2025_uyu'])} UYU",
            f"- Dividendos + intereses + cupones (brutos): {money(r['income_uyu'])} UYU",
            f"- Retenciones en el exterior: {money(r['wht_uyu'])} UYU "
            + (f"→ crédito aplicable {money(r['wht_credit_cap_uyu'])} UYU; el excedente de {money(r['wht_lost_uyu'])} UYU "
             "se pierde (no se reintegra ni descuenta otros impuestos)" if r["wht_credit_applied"]
             else "→ crédito no aplicado en este cálculo"),
            ""]

    sales = group_sales(events)
    out += ["## Optimización de inversiones", ""] + [f"- {t}" for t in optimization_tips(events, r, sales)] + [""]
    if sales:
        note = ("_Una fila por orden de venta (lotes sumados). Costo fiscal y resultado usan el valor al "
                "31/12/2025 para lotes anteriores a 2026._")
        best = sorted((g for g in sales if g["gain"] > 0), key=lambda g: g["gain"], reverse=True)[:TOP_N]
        worst = sorted((g for g in sales if g["gain"] < 0), key=lambda g: g["gain"])[:TOP_N]
        out += [f"## Mejores ventas (top {TOP_N})", "", note, ""]
        out += (sales_table(best) if best else ["Ninguna venta con ganancia en el período."]) + [""]
        out += [f"## Peores ventas (top {TOP_N})", "", note, ""]
        out += (sales_table(worst) if worst else ["Ninguna venta con pérdida en el período."]) + [""]

    out += ["## Por broker (USD, para conciliar con el extracto)", "",
            "| Broker | Filas | Ventas | Resultado ventas (costo orig.) | Rendimientos brutos | Retenciones |",
            "|---|---:|---:|---:|---:|---:|"]
    for name, b in sorted(r["by_broker"].items()):
        out.append(f"| {name} | {b['rows']} | {money(b['proceeds_usd'])} | {money(b['gain_orig_usd'])} | "
                   f"{money(b['income_usd'])} | {money(b['wht_usd'])} |")

    out += ["", "## Detalle por evento", "",
            "| # | Broker | Fecha | Tipo | Símbolo | USD | Resultado USD (orig / 2025) | TC BCU (fecha) | UYU | Notas |",
            "|---:|---|---|---|---|---:|---:|---|---:|---|"]
    for e in sorted(events, key=lambda e: (e["date"], e["broker"])):
        if e["type"] == "sale":
            usd, uyu = e["proceeds"], e["proceeds_uyu"]
            res = f"{money(e['gain_orig_usd'])} / {money(e['gain_2025_usd'])}"
        else:
            usd, uyu, res = e["amount"], e["amount_uyu"], ""
        out.append(f"| {e['line']} | {e['broker']} | {e['date']} | {e['type']} | {e['symbol']} | "
                   f"{money(usd)} | {res} | {e['rate']} ({e['fx_date']}) | {money(uyu)} | {e['notes']} |")

    if warnings:
        out += ["", "## Advertencias", ""] + [f"- {w}" for w in warnings]

    out += ["", "## Preguntas abiertas para confirmar con un contador", "",
            "- **A.** (Criterio aplicado) Lotes comprados antes de 2026: costo fiscal = valor de mercado al 31/12/2025. "
            "La rentabilidad hasta esa fecha no está gravada, y las pérdidas previas tampoco se computan.",
            "- **B.** (Criterio aplicado) Las retenciones del exterior se descuentan como crédito fiscal, hasta el 12% de "
            "IRPF de cada dividendo; el excedente se pierde. Dividendos y crédito van en la declaración jurada anual. "
            "Confirmar si el crédito puede descontarse ya en el anticipo o solo en la declaración jurada "
            "(en ese caso, recalcular con `--no-wht-credit`).",
            "- **C.** ¿Ficto/real debe ser el mismo para todos los brokers? (se asumió que sí)",
            "- **D.** ¿El importe del boleto se redondea o se trunca? (se redondeó al peso más cercano)",
            "- **E.** Ganancias en USD convertidas al TC de la fecha de venta (criterio aplicado); "
            "verificar si el costo debería convertirse al TC de la fecha de compra.",
            "- **F.** (Criterio aplicado) ETFs que replican cripto (IBIT, ETHA): se tratan como activo financiero alcanzado, "
            "tanto sus pérdidas como sus ganancias futuras. Solo se excluye la cripto tenida directamente.",
            "",
            "_Este cálculo es una ayuda, no asesoramiento tributario._", ""]
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
                       "TC BCU dólar billete (2225) por fecha de cada evento</p>")
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
        return compute(evs, fx)[0]["methods"]

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
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("events", nargs="?")
    ap.add_argument("--period", default="2026-01..2026-06")
    ap.add_argument("--out")
    ap.add_argument("--fx-file", help="CSV with columns date,rate to override/skip BCU")
    ap.add_argument("--fx-cache", help="default: fx_cache.json next to events.csv")
    ap.add_argument("--prior-paid-uyu", default="0", help="anticipos already paid this year")
    ap.add_argument("--no-wht-credit", action="store_true",
                    help="do not credit foreign withholding in this anticipo (question B)")
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
    cache = args.fx_cache or os.path.join(os.path.dirname(os.path.abspath(args.events)), "fx_cache.json")
    fx = FX(cache_path=cache, fx_file=args.fx_file)
    r, warnings = compute(events, fx, wht_credit=not args.no_wht_credit)
    text = report(events, r, warnings, args.period, Decimal(args.prior_paid_uyu))
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
