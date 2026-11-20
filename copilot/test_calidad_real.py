"""Paso 7 con los datos reales exportados de Dunnhumby (si estan presentes)."""
import os

import backtest_decision as bd
import reconstruir_backtest as rb

HAY = os.path.exists(os.path.join(rb.DATA, "actividad_semanal.csv"))


def test_backtest_reconstruido_cerca_del_error_de_referencia():
    if not HAY:
        return
    _, wape, chk = rb.reconstruir()
    assert 0.08 < wape < 0.15                      # referencia del estudio: 11 %
    assert chk["semana"].min() == 66 and chk["semana"].max() == 101


def test_nivel_1_real():
    if not HAY:
        return
    r = bd.nivel_1()
    assert 0.05 < r["total"]["wape"] < 0.2
    assert "FLUID MILK PRODUCTS" in r["total"]["categorias_medibles"]


def test_nivel_2_real_recomendado_no_pierde_ni_con_calibracion():
    if not HAY:
        return
    for obj in ("ventas", "volumen"):
        r = bd.nivel_2(obj)
        assert r["plan_recomendado"]["coste_eur"] <= r["restricciones_comunes"]["presupuesto_eur"]
        assert r["mejora_objetivo"] >= 0 and r["con_calibracion"]["mejora_objetivo"] >= 0


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas con datos reales correctas.")
