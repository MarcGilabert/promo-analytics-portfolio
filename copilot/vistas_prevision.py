"""Calculos de la pestana Prevision: demanda y efecto de las promociones.

Demanda
  - historico real, prediccion del backtesting (si se ha exportado) y proyeccion
    hacia delante (proyeccion.py).
Efecto de las promociones (vision CPG / RGM)
  - descomposicion historica: con el modelo lineal del estudio de forecasting,
        unidades ~ a + b_folleto * folleto + b_display * display
    las unidades de cada semana se reparten en base (actividad cero), aportacion
    del folleto y aportacion del display. El resto es lo que el modelo no explica.
    Es una ASOCIACION estimada por el modelo, no un efecto causal.
  - eficiencia por mecanica: unidades incrementales de una semana de promocion y
    coste del descuento por unidad incremental.
"""
import os

import pandas as pd

from proyeccion import HISTORICO
from tools import DATA, MECANICAS, _load_roi, evaluar_promocion

ACTIVIDAD = os.path.join(DATA, "actividad_semanal.csv")
BACKTEST = os.path.join(DATA, "backtest_semanal.csv")


def _ventas():
    df = pd.read_csv(HISTORICO)
    tot = df.groupby("semana")["unidades"].sum().sort_index()
    if len(tot) > 9 and tot.iloc[-1] < 0.8 * tot.iloc[-9:-1].median():
        df = df[df["semana"] != tot.index[-1]]          # ultima semana incompleta
    return df


def hay_actividad():
    return os.path.exists(ACTIVIDAD) and os.path.exists(HISTORICO)


def hay_backtest():
    return os.path.exists(BACKTEST) and os.path.exists(HISTORICO)


# ---- Demanda -----------------------------------------------------------------

def backtest(categoria: str):
    """Real frente a predicho en las semanas de validacion, con su WAPE."""
    if not hay_backtest():
        return None
    bt = pd.read_csv(BACKTEST)
    bt = bt[bt["categoria"] == categoria]
    if bt.empty:
        return None
    real = _ventas()
    df = bt.merge(real[real["categoria"] == categoria][["semana", "unidades"]], on="semana")
    if df.empty:
        return None
    wape = (df["unidades"] - df["prediccion"]).abs().sum() / df["unidades"].sum()
    return {"tabla": df.sort_values("semana"), "wape": round(float(wape), 3),
            "semanas": len(df)}


# ---- Efecto de las promociones ---------------------------------------------------

def descomposicion(categoria: str, ultimas: int = 52):
    """Unidades semanales repartidas en base, folleto, display y no explicado."""
    if not hay_actividad():
        return None
    par = _load_roi().loc[categoria]
    act = pd.read_csv(ACTIVIDAD)
    act = act[act["categoria"] == categoria]
    real = _ventas()
    df = (real[real["categoria"] == categoria]
          .merge(act[["semana", "folleto", "display"]], on="semana", how="inner")
          .sort_values("semana").tail(ultimas))
    if df.empty:
        return None
    base = (float(par["unidades_base"]) - float(par["b_mailer"]) * float(par["mailer_medio"])
            - float(par["b_display"]) * float(par["display_medio"]))
    df = df.assign(
        base=round(base),
        aporte_folleto=(float(par["b_mailer"]) * df["folleto"]).round(),
        aporte_display=(float(par["b_display"]) * df["display"]).round())
    df["no_explicado"] = df["unidades"] - df["base"] - df["aporte_folleto"] - df["aporte_display"]
    total = df["unidades"].sum()
    promo = (df["aporte_folleto"] + df["aporte_display"]).sum()
    return {
        "tabla": df,
        "cuota_promocion": round(float(promo / total), 3) if total else None,
        "cuota_folleto": round(float(df["aporte_folleto"].sum() / total), 3) if total else None,
        "cuota_display": round(float(df["aporte_display"].sum() / total), 3) if total else None,
        "semanas": len(df),
    }


def eficiencia(categoria: str, puntos: float = 15):
    """Por mecanica: unidades incrementales de una semana de promocion, descuento
    total (que asume el distribuidor) y coste por unidad incremental."""
    par = _load_roi().loc[categoria]
    precio = float(par["precio_lista"]) * (1 - float(par["pct_base"]))   # precio habitual
    filas = []
    for mec in MECANICAS:
        e = evaluar_promocion(categoria, puntos, mec)
        u = e["unidades_inc"]
        desc = e["descuento"]
        filas.append({
            "mecanica": mec, "unidades_inc": u, "ventas_inc_eur": e["ventas_inc"],
            "descuento_eur": desc,
            "coste_por_unidad_inc": round(desc / u, 2) if u > 0 else None,
            "precio_eur": round(precio, 2),
            "coste_vs_precio": round(desc / u / precio, 2) if u > 0 else None,
        })
    return pd.DataFrame(filas)


def ranking_eficiencia(mecanica: str = "folleto_y_display"):
    """Coste del descuento por unidad incremental en todas las categorias."""
    filas = []
    for cat in _load_roi().index:
        e = eficiencia(cat)
        f = e[e["mecanica"] == mecanica].iloc[0].to_dict()
        filas.append({"categoria": cat, **f})
    return pd.DataFrame(filas).sort_values("coste_por_unidad_inc", na_position="last")
