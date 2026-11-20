"""Optimizador de surtido: modelo, referencia, validacion y circuito del copiloto."""
from itertools import combinations
import tempfile

import decision_record as dr
from agent import _ruta_reglas, responder
from claims import construir_claims, verificar_todos
from policies import Contexto, evaluar
from surtido import (NOMBRE_SUB, _resolver, curva, grupos, optimize_assortment,
                     ventas_conservadas)

dr.DIR = tempfile.mkdtemp(prefix="decisions_")
LATAS = "SOFT DRINKS 12/18&15PK CAN CAR"


def test_optimo_por_fuerza_bruta():
    g = grupos("SOFT DRINKS CAN NON-CARB (EXCE")
    for k in (2, 3, 4):
        for f in (0.5, 1.0):
            rec = _resolver(g, k, f, "ventas_a1", (), 0)
            mejor = max(ventas_conservadas(g, set(c), f, "ventas_a1")
                        for c in combinations(g["fabricante"], k))
            assert abs(ventas_conservadas(g, rec, f, "ventas_a1") - mejor) < 0.01


def test_restricciones_numero_y_marca_propia():
    r = optimize_assortment(LATAS, max_grupos=3)
    mant = [x for x in r["resultado"]["grupos"] if x["mantener"]]
    assert len(mant) == 3 and any(x["marca_propia"] for x in mant)


def test_mas_transferencia_conserva_mas():
    a = optimize_assortment(LATAS, max_grupos=3, factor_transferencia=0.5)
    b = optimize_assortment(LATAS, max_grupos=3, factor_transferencia=1.0)
    assert b["resultado"]["metricas"]["pct_conservado"] > a["resultado"]["metricas"]["pct_conservado"]


def test_sin_transferencia_conserva_solo_lo_mantenido():
    r = optimize_assortment(LATAS, max_grupos=3, factor_transferencia=0.0)
    m = r["resultado"]["metricas"]
    assert abs(m["ventas_conservadas_eur"] + m["ventas_retiradas_eur"] - m["ventas_a1_eur"]) <= 2


def test_cobertura_objetivo_elige_el_minimo_de_grupos():
    r = optimize_assortment(LATAS, cobertura_objetivo=0.98)
    k = r["parametros"]["max_grupos"]
    assert r["resultado"]["metricas"]["pct_conservado"] >= 0.98
    c = curva(LATAS)
    assert c[c["grupos"] == k - 1]["optimizado"].iloc[0] < 0.98


def test_curva_monotona():
    c = curva(LATAS)
    assert (c["optimizado"].diff().dropna() >= -1e-9).all()
    assert (c["optimizado"] >= c["sin_transferencia"] - 1e-9).all()


def test_validacion_con_el_ano_siguiente_y_arrepentimiento_no_negativo():
    for s in NOMBRE_SUB:
        v = optimize_assortment(s)["resultado"]["validacion"]
        assert v["arrepentimiento_eur"] >= 0


def test_argumentos_y_datos():
    assert optimize_assortment("POTATO CHIPS")["tipo_error"] == "datos"
    assert optimize_assortment(LATAS, max_grupos=99)["tipo_error"] == "argumento"
    assert optimize_assortment(LATAS, factor_transferencia=2)["tipo_error"] == "argumento"


def test_claims_verifican_y_manipulado_se_bloquea():
    r = optimize_assortment(LATAS)
    cl = construir_claims(r)
    assert all(ok for _, ok, _ in verificar_todos(cl, [r]))
    next(c for c in cl if c.metrica == "surtido_pct_conservado").valor = 0.5
    ctx = Contexto("surtido", [r], supuestos_declarados=True,
                   claims_verificados=verificar_todos(cl, [r]))
    assert evaluar(ctx)[0] == "BLOQUEADA"


def test_agente_enruta_y_entrega():
    assert _ruta_reglas("¿Qué fabricantes mantengo en el surtido de pretzels?")["tool"] == \
        "optimize_assortment"
    r = responder("Surtido de refrescos en lata 12/18 conservando el 98 % de las ventas")
    assert r["decision"] != "BLOQUEADA" and all(c["verificado"] for c in r["claims"])
    assert "estimado" in r["conclusion"]


def test_subcategoria_sin_datos_se_bloquea_y_lo_explica():
    r = responder("¿Qué referencias retiro de patatas fritas?")
    assert r["decision"] == "BLOQUEADA" and "Pretzels" in r["conclusion"]


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas del surtido correctas.")
