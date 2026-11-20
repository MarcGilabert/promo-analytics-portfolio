"""Pruebas del optimizador de programa promocional."""
from itertools import combinations

import pandas as pd

import roi_logic
from agent import responder
from claims import construir_claims, verificar_todos
from policies import Contexto, evaluar
from tools import DATA, optimize_promo_program


def _candidatos(puntos=15):
    """Recalcula a mano las promociones con coste (misma formula que la tool) y su
    aportacion a las ventas incrementales, el objetivo por defecto."""
    par_df = pd.read_csv(f"{DATA}/parametros_validador.csv").set_index("categoria")
    out = []
    for cat, f in par_df.iterrows():
        par = f.to_dict()
        e = roi_logic.evaluar(par, par["mailer_p90"], par["display_p90"],
                              par["pct_base"] + puntos / 100, par["margen_defecto"])
        if e["roi"] == e["roi"]:
            out.append((cat, round(e["coste_eur"]), round(e["ventas_incrementales_eur"])))
    return out


def test_optimo_por_fuerza_bruta():
    """Una semana, 60 EUR: el solver debe igualar la mejor combinacion."""
    cands = _candidatos()
    mejor = 0
    for k in range(0, 4):                       # como mucho 3 huecos por semana
        for combo in combinations(cands, k):
            if sum(c[1] for c in combo) <= 60:
                mejor = max(mejor, sum(c[2] for c in combo))
    r = optimize_promo_program(60, 1)
    assert r["resultado"]["metricas"]["ventas_incrementales_eur"] == mejor


def test_restricciones_respetadas():
    r = optimize_promo_program(1000, 4, max_promos_semana=3, max_promos_categoria=2)
    cal = r["resultado"]["calendario"]
    assert r["resultado"]["totales"]["coste_eur"] <= 1000
    for w in range(1, 5):
        assert sum(1 for x in cal if x["semana"] == w) <= 3
    for cat in {x["categoria"] for x in cal}:
        assert sum(1 for x in cal if x["categoria"] == cat) <= 2


def test_presupuesto_limita():
    holgado = optimize_promo_program(1000, 4)["resultado"]["metricas"]
    justo = optimize_promo_program(100, 4)["resultado"]["metricas"]
    assert justo["coste_eur"] <= 100
    assert justo["ventas_incrementales_eur"] < holgado["ventas_incrementales_eur"]


def test_con_roi_minimo_pedido_solo_entran_promociones_que_lo_superan():
    r = optimize_promo_program(1000, 4, roi_minimo=roi_logic.UMBRAL_VERDE)
    assert all(x["roi"] >= roi_logic.UMBRAL_VERDE for x in r["resultado"]["calendario"])


def test_sin_rentables_el_programa_es_vacio_y_lista_las_excluidas():
    r = optimize_promo_program(1000, 4, roi_minimo=5)
    assert r["resultado"]["totales"]["n_promociones"] == 0
    exc = r["resultado"]["excluidas"]
    assert len(exc) == 8
    vals = [e["valor_objetivo"] for e in exc]
    assert vals == sorted(vals, reverse=True)


def test_argumentos_invalidos():
    assert optimize_promo_program(0)["tipo_error"] == "argumento"
    assert optimize_promo_program(1000, 20)["tipo_error"] == "argumento"
    assert optimize_promo_program(1000, 4, -1)["tipo_error"] == "argumento"


def test_programa_a_varias_semanas_avisa_de_horizonte():
    r = responder("Optimiza el programa de promociones del próximo mes con 1.000 €")
    assert r["evidencia"][0]["tool"] == "optimize_promo_program"
    assert any(reg == "Extrapolacion" and est == "warn" for reg, est, _ in r["veredictos"])
    assert all(c["verificado"] for c in r["claims"])


def test_claim_de_programa_manipulado_se_bloquea():
    out = optimize_promo_program(60, 1)
    claims = construir_claims(out)
    benef = next(c for c in claims if c.metrica == "programa_beneficio")
    benef.valor += 100
    ctx = Contexto(pregunta="programa", salidas_tools=[out], borrador="",
                   claims_verificados=verificar_todos(claims, [out]))
    assert evaluar(ctx)[0] == "BLOQUEADA"


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas del programa correctas.")
