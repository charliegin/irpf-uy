# Normativa: IRPF sobre rentas del exterior (desde 2026)

Fuentes oficiales revisadas en octubre de 2026. El texto vigente de cada artículo está en IMPO. Antes de cada anticipo conviene revisar si salieron decretos o resoluciones nuevas: el régimen se ajustó varias veces durante 2026.

## Normas

| Norma | Qué hace | Enlace |
|---|---|---|
| Ley 20.446 (16/12/2025), arts. 645 y siguientes | Extiende el IRPF a los rendimientos de capital y a los incrementos patrimoniales por activos en el exterior, desde el 1/1/2026 | — |
| Decreto 95/026 (06/05/2026) | Reglamenta la ley y modifica el Decreto 148/007 | [IMPO](https://www.impo.com.uy/bases/decretos/95-2026) |
| Decreto 237/026 (01/10/2026) | Ajusta la reglamentación: art. 29 ter incs. 3 y 4, art. 30, y otros | [IMPO](https://www.impo.com.uy/bases/decretos/237-2026) |
| Resolución DGI 1517/026 (29/06/2026) | Plazos de los pagos a cuenta, fuentes de precios, opción por carácter definitivo | [IMPO](https://impo.com.uy/bases/resoluciones-dgi/1517-2026) |
| Resolución DGI 1783/026 (05/08/2026) | Vencimiento transitorio del 1er pago a cuenta de 2026: 26/10/2026 | [IMPO](https://impo.com.uy/bases/resoluciones-dgi/1783-2026) |
| Resolución DGI 2294/026 (08/10/2026) | Régimen simplificado (monto fijo) para 2026 y redacción de los nums. 21 y 22 de la 1517 | [IMPO](https://impo.com.uy/bases/resoluciones-dgi/2294-2026) |

## Artículos del Decreto 148/007 que usa el skill

| Artículo | Regla | Dónde la aplica el skill |
|---|---|---|
| [29 ter](https://www.impo.com.uy/bases/decretos/148-2007/29_TER) | Renta = precio de venta − costo fiscal. El costo, en la moneda de la inversión, se valúa a la cotización del día anterior a la enajenación. Si se vende parte de bienes idénticos, el costo es el promedio ponderado. Si el activo cotiza y se compró antes de 2026, el costo "será" su cotización al 31/12/2025. La opción por el 20% del precio de venta es anual y se ejerce por declaración jurada. | `--cost-method average`, `--fx-mode day-before`, método ficto |
| [30](https://www.impo.com.uy/bases/decretos/148-2007/30) | Las pérdidas se deducen de incrementos patrimoniales si se prueban fehacientemente. Las del art. 29 ter también se compensan con rendimientos de capital mobiliario del exterior. No regula el arrastre a ejercicios siguientes. | El neteo del método real |
| [44 quater](https://www.impo.com.uy/bases/decretos/148-2007/44_QUATER) | Los responsables locales retienen el 12%. El criterio ficto o real se comunica a cada responsable y no cambia en el año. | Pregunta C |
| [44 sexies](https://www.impo.com.uy/bases/decretos/148-2007/44_SEXIES) | Retención del 8% por intermediarios locales con custodia. No aplica a brokers del exterior. | — |
| [44 terdecies](https://www.impo.com.uy/bases/decretos/148-2007/44_TERDECIES) | Pagos a cuenta semestrales sobre las rentas acumuladas desde el 1/1, al 12%, menos lo pagado en el 1er semestre. Pueden darse por definitivos, y entonces no hay declaración jurada por esas rentas. | Vista anual y 2º anticipo |
| [76 bis](https://www.impo.com.uy/bases/decretos/148-2007/76_BIS) | Crédito por el impuesto a la renta análogo pagado en el exterior sobre la misma renta, con tope en el IRPF de esa renta. El pago tiene que probarse. | Crédito por retenciones (pregunta B) |

## Resolución 1517/026

- **Art. 12:** se aceptan las cotizaciones de Bloomberg para los activos que cotizan.
- **Art. 18:** la opción por carácter definitivo se comunica antes del 31/01 del año siguiente. Aplica cuando hay un responsable que retiene.
- **Arts. 21 y 22:** el pago a cuenta de enero a junio se paga en agosto, y el de julio a diciembre en febrero del año siguiente.
- **Art. 26 y Res. 1783 num. 4:** el 1er pago a cuenta de 2026 vence el **26/10/2026**.

## Lo que la normativa no resuelve (preguntas abiertas del informe)

- **B:** si el crédito por impuestos del exterior se puede descontar en el pago a cuenta o solo en la declaración jurada.
- **D:** el redondeo del importe del boleto.
- **E:** el tipo de cambio de dividendos e intereses. El art. 29 ter lo fija solo para las ventas.
- **F:** la cripto tenida directamente y los ETFs de cripto. No se mencionan.
- **G:** si el promedio ponderado es por contribuyente o por cuenta.
- **H:** el tratamiento de comisiones y gastos.
- **I:** el arrastre de pérdidas a ejercicios siguientes.
- **Operaciones especiales:** la normativa no menciona splits, cash in lieu ni transferencias entre brokers.

## Fuentes secundarias consultadas

Sirven para orientarse, pero en caso de diferencia manda el texto oficial:
- [Resumen de Moore](https://msla.moore-global.com/wp-content/uploads/sites/19/2026/06/Dec.-96-2026-Modificacion-IRPF-Rentas-del-exterior.pdf). Dice que las pérdidas de activos anteriores a 2026 no se compensan, y eso no figura en el art. 29 ter vigente.
- [Forvis Mazars](https://www.forvismazars.com/uy/es/insights/nuestras-publicaciones/impuestos/reglamentacion-ampliacion-de-la-fuente-en-el-irpf)
- [EY](https://www.ey.com/es_uy/newsroom/2026/07/invertis_en_el_exterior)
