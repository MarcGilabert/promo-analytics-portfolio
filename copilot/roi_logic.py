"""Logica del Promo Calendar Validator: ROI de una promocion a nivel de categoria.

Todas las funciones son aritmetica pura sobre los parametros exportados del
estudio de forecasting (data/parametros_validador.csv).
"""
import numpy as np

UMBRAL_VERDE = 0.15


def unidades_promo(par, n_mailer, n_display):
    """Unidades previstas con una actividad promocional dada (modelo lineal)."""
    ue = (par["unidades_base"]
          + par["b_mailer"] * (n_mailer - par["mailer_medio"])
          + par["b_display"] * (n_display - par["display_medio"]))
    return max(ue, 0.0)


def semaforo(roi, coste, inc, umbral=UMBRAL_VERDE):
    if coste <= 0:
        return "VERDE" if inc > 0 else "SIN PROMO"
    if roi >= umbral:
        return "VERDE"
    if roi >= 0:
        return "AMBAR"
    return "ROJO"


def evaluar(par, n_mailer, n_display, pct_desc, margen, halo=0.0, umbral=UMBRAL_VERDE):
    """ROI de la promocion frente a la actividad media de la categoria.

    pct_desc   descuento total (fraccion del precio de lista)
    El distribuidor asume todo el descuento promocional (no se modela financiacion
    del fabricante: el dataset no la incluye).
    margen     margen del distribuidor (fraccion del precio de lista)
    halo       valor de cesta por unidad incremental (fraccion del precio de lista)
    """
    p = par["precio_lista"]
    m = margen * p
    h = halo * p
    e = max(pct_desc - par["pct_base"], 0.0) * p          # descuento promocional por unidad

    ub = par["unidades_base"]
    ue = unidades_promo(par, n_mailer, n_display)
    coste = ue * e
    inc = ue * (m - e) - ub * m + (ue - ub) * h
    roi = inc / coste if coste > 0 else np.nan

    # Ventas en euros a precio de cliente (lo que paga el comprador en caja).
    # Base: actividad media al descuento estructural; promo: al descuento total.
    ventas_base = ub * p * (1 - par["pct_base"])
    ventas_promo = ue * p * (1 - max(pct_desc, par["pct_base"]))

    # Aumento de volumen necesario para ROI = 0
    if m + h > e:
        uplift_nec = (m + h) / (m + h - e) - 1
    else:
        uplift_nec = np.inf

    return {
        "unidades_base": ub,
        "unidades_promo": ue,
        "uplift": ue / ub - 1 if ub else np.nan,
        "uplift_necesario": uplift_nec,
        "desc_promo": e / p if p else 0.0,
        "coste_eur": coste,
        "beneficio_incremental_eur": inc,
        "ventas_incrementales_eur": ventas_promo - ventas_base,
        "descuento_total_eur": ue * e,           # coincide con el coste: el distribuidor lo asume entero
        "roi": roi,
        "semaforo": semaforo(roi, coste, inc, umbral),
    }
