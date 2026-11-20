"""Paso 7: calidad de la decision en semanas que el modelo no vio.

Nivel 1. ¿Acierta el modelo en las semanas con promocion?
    Para cada categoria y semana de validacion se predicen las unidades con el
    modelo lineal del estudio de forecasting (entrenado hasta la semana 80):
        prediccion = base + b_folleto * folleto + b_display * display
    y se compara con lo vendido. Se mide el error (WAPE) por separado en semanas
    promocionadas y no promocionadas, y la calibracion del aumento: aumento real
    frente a aumento predicho en las semanas promocionadas. Es lo que el
    optimizador da por bueno; si falla aqui, la recomendacion no se sostiene.

Nivel 2. Plan real frente a plan recomendado, simulados con el mismo modelo.
    "Plan real" = semanas y categorias en las que el retailer promociono de verdad
    (folleto por encima de un umbral, supuesto declarado). El plan recomendado lo
    construye el optimizador con el MISMO presupuesto, huecos y semanas. Ambos se
    evaluan con las mismas metricas. Es una simulacion: no demuestra cuanto habria
    vendido el retailer siguiendo la recomendacion (nivel 3, requiere experimento).
"""
import os

import pandas as pd

from tools import DATA, _load_roi, evaluar_promocion, optimize_promo_program

VENTAS = os.path.join(DATA, "ventas_semanales.csv")
ACTIVIDAD = os.path.join(DATA, "actividad_semanal.csv")
SEMANAS_VALIDACION = list(range(90, 102))      # la 102 esta incompleta
UMBRAL_PROMOCION = 1.3                         # folleto >= 1,3 veces su media


def disponible():
    return os.path.exists(VENTAS) and os.path.exists(ACTIVIDAD)


def _datos(semanas):
    v = pd.read_csv(VENTAS)
    a = pd.read_csv(ACTIVIDAD)
    df = v.merge(a[["semana", "categoria", "folleto", "display"]], on=["semana", "categoria"])
    return df[df["semana"].isin(semanas)].copy()


def _wape(real, pred):
    return float((real - pred).abs().sum() / real.sum()) if real.sum() else None


def nivel_1(semanas=SEMANAS_VALIDACION, umbral=UMBRAL_PROMOCION):
    """Error y calibracion del aumento en semanas no vistas."""
    df = _datos(semanas)
    par = _load_roi()
    filas = []
    for cat, g in df.groupby("categoria"):
        p = par.loc[cat]
        base = (float(p["unidades_base"]) - float(p["b_mailer"]) * float(p["mailer_medio"])
                - float(p["b_display"]) * float(p["display_medio"]))
        g = g.assign(
            pred=base + float(p["b_mailer"]) * g["folleto"] + float(p["b_display"]) * g["display"],
            pred_sin_promo=base + float(p["b_mailer"]) * float(p["mailer_medio"])
            + float(p["b_display"]) * float(p["display_medio"]),
            promo=g["folleto"] >= umbral)
        pm = g[g["promo"]]
        aum_pred = float((pm["pred"] - pm["pred_sin_promo"]).sum())
        aum_real = float((pm["unidades"] - pm["pred_sin_promo"]).sum())
        # Ruido: dispersion del error en semanas SIN promocion. Si el aumento
        # predicho no supera dos veces el ruido acumulado, no es medible.
        res_sin = (g[~g["promo"]]["unidades"] - g[~g["promo"]]["pred"])
        ruido = float(res_sin.std(ddof=1)) * len(pm) ** 0.5 if len(res_sin) > 2 and len(pm) else None
        medible = bool(ruido is not None and aum_pred > 2 * ruido)
        filas.append({
            "categoria": cat, "semanas": len(g), "semanas_promo": int(g["promo"].sum()),
            "wape": _wape(g["unidades"], g["pred"]),
            "wape_promo": _wape(pm["unidades"], pm["pred"]) if len(pm) else None,
            "wape_sin_promo": _wape(g[~g["promo"]]["unidades"], g[~g["promo"]]["pred"])
            if (~g["promo"]).any() else None,
            "aumento_predicho": round(aum_pred), "aumento_real": round(aum_real),
            "ruido_acumulado": None if ruido is None else round(ruido),
            "aumento_medible": medible,
            "calibracion": round(aum_real / aum_pred, 2) if aum_pred > 0 else None,
        })
    res = pd.DataFrame(filas)
    med = res[res["aumento_medible"]]
    total = {
        "calibracion_medibles": round(med["aumento_real"].sum() / med["aumento_predicho"].sum(), 2)
        if len(med) and med["aumento_predicho"].sum() > 0 else None,
        "categorias_medibles": med["categoria"].tolist(),
        "wape": _wape(df["unidades"], pd.concat([
            _pred_cat(g, par.loc[c]) for c, g in df.groupby("categoria")])),
        "calibracion_global": round(res["aumento_real"].sum() / res["aumento_predicho"].sum(), 2)
        if res["aumento_predicho"].sum() > 0 else None,
    }
    return {"por_categoria": res, "total": total, "semanas": semanas, "umbral": umbral}


def _pred_cat(g, p):
    base = (float(p["unidades_base"]) - float(p["b_mailer"]) * float(p["mailer_medio"])
            - float(p["b_display"]) * float(p["display_medio"]))
    return base + float(p["b_mailer"]) * g["folleto"] + float(p["b_display"]) * g["display"]


def plan_real(semanas=SEMANAS_VALIDACION, umbral=UMBRAL_PROMOCION):
    """Calendario que el retailer ejecuto: categorias con folleto >= umbral."""
    df = _datos(semanas)
    w0 = min(semanas)
    pr = df[df["folleto"] >= umbral]
    return [{"semana": int(r.semana) - w0 + 1, "categoria": r.categoria}
            for r in pr.itertuples()]


def _evaluar(cal):
    tot = {"n_promociones": 0, "unidades_inc": 0, "ventas_inc_eur": 0, "coste_eur": 0,
           "descuento_eur": 0, "beneficio_base_eur": 0}
    for r in cal:
        e = evaluar_promocion(r["categoria"])
        tot["n_promociones"] += 1
        tot["unidades_inc"] += e["unidades_inc"]
        tot["ventas_inc_eur"] += e["ventas_inc"]
        tot["coste_eur"] += e["coste"]
        tot["descuento_eur"] += e["descuento"]
        tot["beneficio_base_eur"] += e["beneficio_por_margen"]["base"]["beneficio"]
    return tot


def _evaluar_calibrado(cal, factores):
    """Como _evaluar, pero escalando el aumento de cada categoria por su
    calibracion medida en el nivel 1 (aumento real / predicho)."""
    par = _load_roi()
    tot = {"unidades_inc": 0.0, "ventas_inc_eur": 0.0}
    for r in cal:
        e = evaluar_promocion(r["categoria"])
        f = factores.get(r["categoria"], 1.0)
        p = par.loc[r["categoria"]]
        precio_promo = float(p["precio_lista"]) * (1 - (float(p["pct_base"]) + 0.15))
        tot["unidades_inc"] += e["unidades_inc"] * f
        tot["ventas_inc_eur"] += e["ventas_inc"] + (f - 1) * e["unidades_inc"] * precio_promo
    return {k: round(v) for k, v in tot.items()}


def nivel_2(objetivo="ventas", semanas=SEMANAS_VALIDACION,
            umbral=UMBRAL_PROMOCION):
    """Plan real frente a recomendado con el mismo presupuesto, huecos y semanas."""
    real = plan_real(semanas, umbral)
    ev_real = _evaluar(real)
    n_sem = len(semanas)
    huecos = max([sum(1 for r in real if r["semana"] == w) for w in range(1, n_sem + 1)] or [1])
    por_cat = max([sum(1 for r in real if r["categoria"] == c)
                   for c in {r["categoria"] for r in real}] or [1])
    presupuesto = max(ev_real["coste_eur"], 1)
    opt = optimize_promo_program(presupuesto, min(n_sem, 12), 15, min(huecos, 8),
                                 por_cat, objetivo)
    if not opt["ok"]:
        return {"ok": False, "motivo": opt["motivo"]}
    rec = [{"semana": r["semana"], "categoria": r["categoria"]}
           for r in opt["resultado"]["calendario"]]
    ev_rec = _evaluar(rec)
    campo = {"ventas": "ventas_inc_eur", "volumen": "unidades_inc"}[objetivo]
    # Sensibilidad: mismos dos planes con el aumento corregido por la calibracion
    # medida (acotada entre 0 y 2; las categorias no medibles usan la global).
    n1 = nivel_1(semanas, umbral)
    glob = n1["total"]["calibracion_global"] or 1.0
    factores = {}
    for r in n1["por_categoria"].itertuples():
        c = r.calibracion if r.aumento_medible and r.calibracion is not None else glob
        factores[r.categoria] = float(min(max(c, 0.0), 2.0))
    cal_real = _evaluar_calibrado(real, factores)
    cal_rec = _evaluar_calibrado(rec, factores)
    return {
        "ok": True, "objetivo": objetivo,
        "restricciones_comunes": {"presupuesto_eur": round(presupuesto), "huecos_por_semana": huecos,
                                  "promos_por_categoria": por_cat, "semanas": n_sem},
        "plan_real": {"calendario": real, **ev_real},
        "plan_recomendado": {"calendario": rec, **ev_rec},
        "mejora_objetivo": ev_rec[campo] - ev_real[campo],
        "con_calibracion": {"plan_real": cal_real, "plan_recomendado": cal_rec,
                            "mejora_objetivo": cal_rec[campo] - cal_real[campo],
                            "factores": {k: round(v, 2) for k, v in factores.items()}},
        "supuestos": [
            f"Plan real = categorias con folleto >= {umbral} veces su media semanal.",
            "Ambos planes se evaluan con el mismo modelo y las mismas restricciones: "
            "es una simulacion, no una medicion de lo que habria pasado.",
            "Beneficio con margen supuesto por categoria; el distribuidor asume todo el descuento.",
        ],
    }
