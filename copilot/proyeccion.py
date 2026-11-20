"""Proyeccion semanal de ventas de una categoria con supuestos declarados.

Dibuja dos lineas:
  base          nivel semanal estimado de la categoria, ajustado por el cambio de
                precio que se suponga
  con programa  la base mas las unidades incrementales de las semanas en que el
                programa recomendado promociona la categoria, escaladas por el
                efecto de promocion supuesto

Supuestos (todos editables y declarados en la salida):
  - efecto_promo_pct: que parte del aumento estimado por el modelo se cree (100 =
    el del modelo).
  - cambio_precio_pct y elasticidad: el efecto de una subida o bajada de precio
    sobre las unidades es (1 + cambio) ** elasticidad. LA ELASTICIDAD NO ESTA
    MEDIDA EN ESTOS DATOS: es un supuesto. Referencia por defecto: -1,76, media de
    367 elasticidades de marca (Tellis, 1988). A nivel de categoria puede ser
    menor en valor absoluto.
  - banda de error: WAPE medido a 1 semana; mas alla se abre con la raiz del
    horizonte. Es una regla ilustrativa: solo la semana 1 esta validada.
"""
import math
import os

import pandas as pd

from tools import DATA, HORIZONTE_VALIDADO, _load, _load_roi

ELASTICIDAD_REFERENCIA = -1.76
FUENTE_ELASTICIDAD = ("Tellis (1988), 'The Price Elasticity of Selective Demand', media de "
                      "367 elasticidades de marca")
HISTORICO = os.path.join(DATA, "ventas_semanales.csv")


def historico(categoria: str, ultimas: int = 26):
    """Ventas semanales historicas si existe data/ventas_semanales.csv
    (columnas: semana, categoria, unidades). Si no existe, None."""
    if not os.path.exists(HISTORICO):
        return None
    df = pd.read_csv(HISTORICO)
    # La ultima semana del dataset esta incompleta (los datos acaban a mitad de
    # semana): si el total de las 8 categorias cae mas de un 20 % frente a la
    # mediana de las 8 semanas anteriores, se descarta.
    tot = df.groupby("semana")["unidades"].sum().sort_index()
    if len(tot) > 9 and tot.iloc[-1] < 0.8 * tot.iloc[-9:-1].median():
        df = df[df["semana"] != tot.index[-1]]
    df = df[df["categoria"] == categoria].sort_values("semana").tail(ultimas)
    return df if len(df) else None


def proyectar(categoria: str, semanas: int, calendario: list | None = None,
              efecto_promo_pct: float = 100, cambio_precio_pct: float = 0,
              elasticidad: float = ELASTICIDAD_REFERENCIA) -> dict:
    if not 1 <= semanas <= 52:
        raise ValueError("El horizonte debe estar entre 1 y 52 semanas.")
    if not 0 <= efecto_promo_pct <= 300:
        raise ValueError("El efecto de la promocion debe estar entre 0 % y 300 %.")
    if not -50 <= cambio_precio_pct <= 50:
        raise ValueError("El cambio de precio debe estar entre -50 % y +50 %.")
    if not -6 <= elasticidad <= 0:
        raise ValueError("La elasticidad debe estar entre -6 y 0.")
    store = _load()
    if categoria not in store.index:
        raise ValueError(f"La categoria '{categoria}' no esta en los datos.")
    nivel = float(store.loc[categoria, "nivel_semanal"])
    wape = float(store.loc[categoria, "wape_referencia"])
    par = _load_roi().loc[categoria]
    precio = float(par["precio_lista"]) * (1 - float(par["pct_base"]))

    factor_precio = (1 + cambio_precio_pct / 100) ** elasticidad
    inc = {}
    for r in calendario or []:
        if r["categoria"] == categoria:
            inc[r["semana"]] = inc.get(r["semana"], 0) + r["unidades_inc"]

    filas = []
    for w in range(1, semanas + 1):
        base = nivel * factor_precio
        promo = base + inc.get(w, 0) * efecto_promo_pct / 100 * factor_precio
        ancho = wape * math.sqrt(w / HORIZONTE_VALIDADO)
        filas.append({"semana": w, "base": round(base), "con_programa": round(promo),
                      "banda_baja": round(promo * (1 - ancho)),
                      "banda_alta": round(promo * (1 + ancho)),
                      "validada": w <= HORIZONTE_VALIDADO, "promocion": w in inc})

    total_sin_cambio = nivel * semanas
    total_base = sum(f["base"] for f in filas)
    ingresos_factor = (1 + cambio_precio_pct / 100) ** (1 + elasticidad)
    return {
        "categoria": categoria,
        "semanas": filas,
        "resumen": {
            "unidades_base_sin_cambio": round(total_sin_cambio),
            "unidades_base": total_base,
            "unidades_con_programa": sum(f["con_programa"] for f in filas),
            "efecto_precio_unidades_pct": round((factor_precio - 1) * 100, 1),
            "efecto_precio_ingresos_pct": round((ingresos_factor - 1) * 100, 1),
            "ingresos_base_sin_cambio_eur": round(total_sin_cambio * precio),
            "ingresos_base_eur": round(total_base * precio * (1 + cambio_precio_pct / 100)),
        },
        "supuestos": [
            {"nombre": "efecto_promocion", "valor": f"{efecto_promo_pct:.0f} % del estimado",
             "nivel": "supuesto" if efecto_promo_pct != 100 else "estimado"},
            {"nombre": "cambio_precio", "valor": f"{cambio_precio_pct:+.1f} %",
             "nivel": "supuesto"},
            {"nombre": "elasticidad_precio", "valor": elasticidad, "nivel": "supuesto",
             "origen": FUENTE_ELASTICIDAD + " (no medida en estos datos)"},
            {"nombre": "banda_error", "valor": f"WAPE {wape:.0%} x raiz(semanas)",
             "nivel": "supuesto", "origen": f"solo validada a {HORIZONTE_VALIDADO} semana"},
            {"nombre": "nivel_base", "valor": round(nivel), "nivel": "estimado",
             "origen": "nivel semanal del modelo de forecasting, sin estacionalidad"},
        ],
    }
