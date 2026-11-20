"""Paso 7: backtest de la decision con actividad sintetica (sin el CSV real)."""
import os
import tempfile

import pandas as pd

import backtest_decision as bd
from tools import _load_roi

TMP = tempfile.mkdtemp(prefix="bt_")


def _actividad_sintetica():
    """Actividad media en todas las semanas salvo folleto alto en leche y sopa
    semanas alternas; ventas reales = exactamente lo que predice el modelo."""
    par = _load_roi()
    filas, ventas = [], []
    for cat in par.index:
        p = par.loc[cat]
        for w in range(1, 103):
            f = 2.0 if cat in ("FLUID MILK PRODUCTS", "SOUP") and w % 2 == 0 else 1.0
            d = 1.0
            filas.append({"semana": w, "categoria": cat, "folleto": f, "display": d})
            base = (p["unidades_base"] - p["b_mailer"] * p["mailer_medio"]
                    - p["b_display"] * p["display_medio"])
            ventas.append({"semana": w, "categoria": cat,
                           "unidades": round(base + p["b_mailer"] * f + p["b_display"] * d)})
    a, v = os.path.join(TMP, "a.csv"), os.path.join(TMP, "v.csv")
    pd.DataFrame(filas).to_csv(a, index=False)
    pd.DataFrame(ventas).to_csv(v, index=False)
    bd.ACTIVIDAD, bd.VENTAS = a, v


_actividad_sintetica()


def test_nivel_1_con_ventas_iguales_al_modelo_error_cero_y_calibracion_uno():
    r = bd.nivel_1()
    assert r["total"]["wape"] < 0.001
    leche = r["por_categoria"].set_index("categoria").loc["FLUID MILK PRODUCTS"]
    assert leche["semanas_promo"] == 6 and abs(leche["calibracion"] - 1) < 0.01


def test_plan_real_detecta_las_semanas_con_folleto():
    real = bd.plan_real()
    assert {r["categoria"] for r in real} == {"FLUID MILK PRODUCTS", "SOUP"}
    assert len(real) == 12 and all(1 <= r["semana"] <= 12 for r in real)


def test_nivel_2_misma_restriccion_y_el_optimo_no_pierde():
    r = bd.nivel_2(objetivo="ventas")
    assert r["ok"]
    rc = r["restricciones_comunes"]
    assert r["plan_recomendado"]["coste_eur"] <= rc["presupuesto_eur"]
    assert r["mejora_objetivo"] >= 0


def test_nivel_2_volumen():
    r = bd.nivel_2(objetivo="volumen")
    assert r["ok"] and r["mejora_objetivo"] >= 0


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas del backtest de la decision correctas.")
