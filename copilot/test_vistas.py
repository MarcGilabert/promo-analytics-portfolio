"""Pestana Prevision: eficiencia, descomposicion y backtest."""
import os
import tempfile

import pandas as pd

import vistas_prevision as vp
from tools import _load_roi

TMP = tempfile.mkdtemp(prefix="vistas_")


def test_eficiencia_coste_por_unidad_incremental():
    e = vp.eficiencia("FLUID MILK PRODUCTS")
    f = e[e["mecanica"] == "folleto_y_display"].iloc[0]
    assert abs(f["coste_por_unidad_inc"] - f["descuento_eur"] / f["unidades_inc"]) < 0.01


def test_ranking_ordenado_de_mas_barato_a_mas_caro():
    rk = vp.ranking_eficiencia()
    v = rk["coste_por_unidad_inc"].dropna().tolist()
    assert v == sorted(v) and len(rk) == 8


def test_descomposicion_suma_las_unidades():
    par = _load_roi().loc["CHEESE"]
    act = pd.DataFrame({"semana": range(80, 102), "categoria": "CHEESE",
                        "folleto": 1.5, "display": 0.5})
    ruta = os.path.join(TMP, "act.csv")
    act.to_csv(ruta, index=False)
    vp.ACTIVIDAD = ruta
    d = vp.descomposicion("CHEESE")
    t = d["tabla"]
    assert ((t["base"] + t["aporte_folleto"] + t["aporte_display"] + t["no_explicado"])
            == t["unidades"]).all()
    esperado = round(float(par["b_mailer"]) * 1.5)
    assert (t["aporte_folleto"] == esperado).all()
    assert 0 < d["cuota_promocion"] < 1


def test_backtest_calcula_el_wape():
    real = pd.read_csv(vp.HISTORICO)
    r = real[(real["categoria"] == "SOUP") & real["semana"].between(70, 81)]
    bt = r.assign(prediccion=r["unidades"] * 1.1)[["semana", "categoria", "prediccion"]]
    ruta = os.path.join(TMP, "bt.csv")
    bt.to_csv(ruta, index=False)
    vp.BACKTEST = ruta
    res = vp.backtest("SOUP")
    assert res["semanas"] == 12 and abs(res["wape"] - 0.1) < 0.001


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas de la pestana Prevision correctas.")
