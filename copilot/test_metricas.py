"""Paso 1: todas las tools devuelven el mismo bloque de metricas."""
import math

import roi_logic
from claims import construir_claims, verificar_todos
from tools import (METRICAS, evaluate_promo_roi, get_category_forecast,
                   optimize_promo_program)

PAR = {"unidades_base": 1000, "b_mailer": 100.0, "b_display": 0.0,
       "mailer_medio": 0.0, "display_medio": 0.0,
       "precio_lista": 2.0, "pct_base": 0.05}


def _todas():
    return [get_category_forecast("FLUID MILK PRODUCTS", 1),
            evaluate_promo_roi("CHEESE"),
            optimize_promo_program(1000, 4)]


def test_ventas_y_descuento_a_mano():
    # promo: 1200 ud a 2 € con 25 % de descuento -> 1200 * 1.5 = 1800 €
    # base:  1000 ud a 2 € con  5 % de descuento -> 1000 * 1.9 = 1900 €
    # ventas incrementales = -100 €; descuento promocional total = 1200 * 0.40 = 480 €
    r = roi_logic.evaluar(PAR, 2.0, 0.0, 0.25, 0.5, 0.30)
    assert math.isclose(r["ventas_incrementales_eur"], -100)
    assert math.isclose(r["descuento_total_eur"], 480)


def test_mismas_claves_en_todas_las_tools():
    for s in _todas():
        assert s["ok"], s.get("motivo")
        assert list(s["resultado"]["metricas"]) == list(METRICAS)


def test_toda_metrica_vacia_tiene_motivo():
    for s in _todas():
        vacias = {k for k, v in s["resultado"]["metricas"].items() if v is None}
        assert vacias == set(s["metadata"]["metricas_no_disponibles"])
        assert all(s["metadata"]["metricas_no_disponibles"].values())


def test_todas_declaran_limites():
    for s in _todas():
        assert s["metadata"]["limites"]


def test_metricas_coherentes_con_campos_previos():
    roi = evaluate_promo_roi("CHEESE")
    m, r = roi["resultado"]["metricas"], roi["resultado"]
    assert m["coste_eur"] == r["coste_eur"]
    assert m["beneficio_eur"] == r["beneficio_incremental_eur"]
    assert m["roi"] == r["roi"]
    prog = optimize_promo_program(1000, 4)
    m, cal = prog["resultado"]["metricas"], prog["resultado"]["calendario"]
    assert m["coste_eur"] == sum(c["coste_eur"] for c in cal)
    assert m["ventas_incrementales_eur"] == sum(c["ventas_inc_eur"] for c in cal)
    assert m["descuento_total_eur"] >= m["coste_eur"]     # el distribuidor paga una parte


def test_claims_de_ventas_verifican():
    for s in _todas()[1:]:
        cl = construir_claims(s)
        assert any(c.metrica in ("ventas_incrementales", "programa_ventas") for c in cl)
        assert all(ok for _, ok, _ in verificar_todos(cl, [s]))


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas de metricas correctas.")
