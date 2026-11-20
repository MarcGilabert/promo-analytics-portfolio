"""Proyeccion semanal con supuestos: aritmetica y limites."""
import math

from proyeccion import ELASTICIDAD_REFERENCIA, proyectar

CAL = [{"semana": 2, "categoria": "FLUID MILK PRODUCTS", "unidades_inc": 263},
       {"semana": 3, "categoria": "SOUP", "unidades_inc": 170}]


def test_sin_supuestos_la_base_es_el_nivel_del_modelo():
    p = proyectar("FLUID MILK PRODUCTS", 4)
    assert {f["base"] for f in p["semanas"]} == {1367}
    assert p["resumen"]["efecto_precio_unidades_pct"] == 0


def test_promocion_solo_en_su_semana_y_su_categoria():
    p = proyectar("FLUID MILK PRODUCTS", 4, CAL)
    s = {f["semana"]: f for f in p["semanas"]}
    assert s[2]["con_programa"] - s[2]["base"] == 263
    assert s[3]["con_programa"] == s[3]["base"]


def test_efecto_promocion_escala_el_aumento():
    p = proyectar("FLUID MILK PRODUCTS", 4, CAL, efecto_promo_pct=50)
    s = p["semanas"][1]
    assert abs((s["con_programa"] - s["base"]) - 131.5) <= 1


def test_subida_de_precio_con_elasticidad():
    # +3 % de precio con elasticidad -1,76: unidades x 1,03^-1,76 = -5,1 %
    p = proyectar("FLUID MILK PRODUCTS", 12, cambio_precio_pct=3)
    assert p["resumen"]["efecto_precio_unidades_pct"] == round((1.03 ** -1.76 - 1) * 100, 1)
    assert p["resumen"]["efecto_precio_ingresos_pct"] == round((1.03 ** -0.76 - 1) * 100, 1)
    assert p["resumen"]["unidades_base"] < p["resumen"]["unidades_base_sin_cambio"]


def test_con_demanda_inelastica_subir_precio_sube_ingresos():
    p = proyectar("FLUID MILK PRODUCTS", 12, cambio_precio_pct=3, elasticidad=-0.5)
    assert p["resumen"]["efecto_precio_ingresos_pct"] > 0


def test_banda_se_abre_fuera_del_horizonte_validado():
    p = proyectar("FLUID MILK PRODUCTS", 9)
    anchos = [f["banda_alta"] - f["banda_baja"] for f in p["semanas"]]
    assert anchos[0] < anchos[3] < anchos[8]
    assert p["semanas"][0]["validada"] and not p["semanas"][1]["validada"]
    assert math.isclose(anchos[3] / anchos[0], 2, rel_tol=0.02)


def test_supuestos_declarados_con_fuente_de_la_elasticidad():
    p = proyectar("SOUP", 4, cambio_precio_pct=3)
    el = next(s for s in p["supuestos"] if s["nombre"] == "elasticidad_precio")
    assert el["valor"] == ELASTICIDAD_REFERENCIA and "Tellis" in el["origen"]
    assert "no medida" in el["origen"]


def test_argumentos_fuera_de_rango():
    for kw in ({"semanas": 0}, {"cambio_precio_pct": 80}, {"elasticidad": 1}):
        args = {"categoria": "SOUP", "semanas": 4, **kw}
        try:
            proyectar(**args)
            raise AssertionError(kw)
        except ValueError:
            pass


def test_historico_descarta_la_ultima_semana_incompleta():
    from proyeccion import historico
    h = historico("FLUID MILK PRODUCTS")
    assert h is not None and len(h) == 26
    assert h["semana"].max() == 101          # la 102 esta incompleta en el dataset


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas de la proyeccion correctas.")
