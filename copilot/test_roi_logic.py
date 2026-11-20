"""Pruebas de la formula economica del ROI y de sus casos limite."""
import math

import roi_logic
from tools import evaluate_promo_roi

# Parametros sinteticos con numeros redondos para comprobar la formula a mano.
PAR = {"unidades_base": 1000, "b_mailer": 100.0, "b_display": 0.0,
       "mailer_medio": 0.0, "display_medio": 0.0,
       "precio_lista": 2.0, "pct_base": 0.05}


def test_formula_a_mano():
    # actividad 2 -> unidades promo = 1000 + 100*2 = 1200
    # descuento promocional = (0.25 - 0.05) * 2 = 0.40 EUR/ud, todo a cargo del distribuidor
    # margen = 0.30 * 2 = 0.60 EUR/ud
    # beneficio inc = 1200*(0.60-0.40) - 1000*0.60 = 240 - 600 = -360
    # coste = 1200 * 0.40 = 480 -> ROI = -0.75
    r = roi_logic.evaluar(PAR, 2.0, 0.0, 0.25, 0.30)
    assert r["unidades_promo"] == 1200
    assert math.isclose(r["coste_eur"], 480)
    assert math.isclose(r["beneficio_incremental_eur"], -360)
    assert math.isclose(r["roi"], -0.75)
    assert r["semaforo"] == "ROJO"


def test_umbrales_semaforo_explicitos():
    assert roi_logic.semaforo(0.15, 1, 1) == "VERDE"
    assert roi_logic.semaforo(0.149, 1, 1) == "AMBAR"
    assert roi_logic.semaforo(0.0, 1, 1) == "AMBAR"
    assert roi_logic.semaforo(-0.01, 1, 1) == "ROJO"


def test_sin_descuento_promocional_no_hay_coste():
    # descuento total igual al estructural -> coste 0, ROI indefinido
    r = roi_logic.evaluar(PAR, 2.0, 0.0, 0.05, 0.30)
    assert r["coste_eur"] == 0
    assert math.isnan(r["roi"])
    assert r["semaforo"] == "VERDE"          # hay uplift sin coste


def test_el_coste_es_todo_el_descuento():
    r = roi_logic.evaluar(PAR, 2.0, 0.0, 0.25, 0.30)
    assert math.isclose(r["coste_eur"], r["descuento_total_eur"])


def test_descuento_mayor_que_margen_no_alcanzable():
    # descuento efectivo >= margen -> no hay aumento de volumen que lo pague
    r = roi_logic.evaluar(PAR, 2.0, 0.0, 0.60, 0.30)
    assert math.isinf(r["uplift_necesario"])


def test_tool_declara_supuestos_con_origen_y_fecha():
    out = evaluate_promo_roi("FLUID MILK PRODUCTS")
    for s in out["metadata"]["supuestos"]:
        assert s["origen"] and s["fecha"]
    sens = out["metadata"]["sensibilidad"]
    m = sens["roi_por_margen"]
    assert m["-5pp"] < m["base"] < m["+5pp"]  # mas margen, mejor ROI


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas de ROI correctas.")
