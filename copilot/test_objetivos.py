"""Paso 2: selector de objetivo y restricciones explicitas del optimizador."""
from itertools import combinations

from agent import responder
from policies import BLOCK, WARN, Contexto, evaluar, r_objetivo
from tools import OBJETIVOS, optimize_promo_program

CAMPO = {o: d["metrica"] for o, d in OBJETIVOS.items()}


def _valor(salida, objetivo):
    return salida["resultado"]["metricas"][CAMPO[objetivo]] or 0


def test_cada_objetivo_gana_en_su_metrica():
    progs = {o: optimize_promo_program(1000, 4, objetivo=o) for o in OBJETIVOS}
    for o, prog in progs.items():
        for otro in progs.values():
            assert _valor(prog, o) >= _valor(otro, o), o


def test_objetivo_cambia_el_programa():
    vol = optimize_promo_program(1000, 4, objetivo="volumen")
    ven = optimize_promo_program(1000, 4, objetivo="ventas")
    assert vol["resultado"]["calendario"] != ven["resultado"]["calendario"]


def test_beneficio_no_es_un_objetivo_y_lo_explica():
    r = optimize_promo_program(1000, 4, objetivo="beneficio")
    assert r["tipo_error"] == "argumento" and "margenes" in r["motivo"]


def test_beneficio_se_ilustra_con_tres_margenes_ordenados():
    s = optimize_promo_program(1000, 4)
    ilu = s["resultado"]["beneficio_ilustrativo"]
    assert ilu["bajo"]["beneficio_eur"] < ilu["base"]["beneficio_eur"] < ilu["alto"]["beneficio_eur"]
    assert ilu["base"]["beneficio_eur"] == s["resultado"]["metricas"]["beneficio_eur"]


def test_cada_metrica_declara_su_nivel_de_evidencia():
    s = optimize_promo_program(1000, 4)
    ev = s["metadata"]["evidencia"]
    assert ev["ventas_incrementales_eur"]["nivel"] == "estimado"
    assert ev["beneficio_eur"]["nivel"] == "supuesto" and ev["roi"]["nivel"] == "supuesto"


def test_optimo_por_fuerza_bruta_en_cada_objetivo():
    for o in OBJETIVOS:
        s = optimize_promo_program(300, 1, objetivo=o, max_promos_semana=3)
        cand = s["resultado"]["candidatas"]
        mejor = 0
        for k in range(0, 4):
            for comb in combinations(cand, k):
                if sum(c["coste"] for c in comb) <= 300:
                    mejor = max(mejor, sum(c["valor_objetivo"] for c in comb))
        assert _valor(s, o) == mejor, (o, _valor(s, o), mejor)


def test_ventas_nunca_elige_promociones_que_restan_ventas():
    s = optimize_promo_program(1000, 4, objetivo="ventas")
    assert all(r["ventas_inc_eur"] > 0 for r in s["resultado"]["calendario"])


def test_tope_de_descuento_se_respeta_y_limita():
    libre = optimize_promo_program(5000, 4, objetivo="volumen")
    tope = libre["resultado"]["metricas"]["descuento_total_eur"] // 2
    s = optimize_promo_program(5000, 4, objetivo="volumen",
                               max_descuento_total_eur=tope)
    assert s["resultado"]["metricas"]["descuento_total_eur"] <= tope
    activas = {r["nombre"] for r in s["metadata"]["restricciones"] if r["activa"]}
    assert "descuento_total_maximo" in activas


def test_restricciones_recalculadas_y_cumplidas():
    s = optimize_promo_program(1000, 4)
    assert all(r["cumple"] for r in s["metadata"]["restricciones"])
    assert r_objetivo(Contexto("", [s])).estado in ("pass", WARN)   # avisa si pierde dinero


def test_programa_manipulado_que_incumple_se_bloquea():
    s = optimize_promo_program(1000, 4)
    s["resultado"]["calendario"].append(dict(s["resultado"]["calendario"][0]))  # promo extra
    s["parametros"]["presupuesto_eur"] = 100
    v = r_objetivo(Contexto("", [s]))
    assert v.estado == BLOCK and "presupuesto" in v.mensaje


def test_programa_que_pierde_con_el_margen_base_avisa():
    s = optimize_promo_program(1000, 4, objetivo="volumen")
    assert s["resultado"]["metricas"]["beneficio_eur"] < 0
    assert s["metadata"]["conflicto_objetivo"]
    assert r_objetivo(Contexto("", [s])).estado == WARN


def test_por_defecto_no_filtra_con_margen_supuesto():
    s = optimize_promo_program(1000, 4, objetivo="volumen")
    assert s["parametros"]["roi_minimo"] is None and s["resultado"]["totales"]["n_promociones"] > 0


def test_roi_minimo_pedido_avisa_de_que_usa_margen_supuesto():
    s = optimize_promo_program(1000, 4, roi_minimo=0.15)
    v = r_objetivo(Contexto("", [s]))
    assert v.estado == WARN and "margen supuesto" in v.mensaje


def test_argumentos_invalidos():
    assert optimize_promo_program(objetivo="cuota")["tipo_error"] == "argumento"
    assert optimize_promo_program(objetivo="beneficio")["tipo_error"] == "argumento"
    assert optimize_promo_program(roi_minimo=9)["tipo_error"] == "argumento"


def test_agente_lee_objetivo_y_avisa():
    r = responder("Maximiza el volumen con 1000 € aunque pierda dinero")
    p = r["evidencia"][0]["parametros"]
    assert p["objetivo"] == "volumen" and p["roi_minimo"] is None
    assert r["decision"] == "ENTREGAR_CON_AVISO"
    assert "pierde" in r["conclusion"]


def test_agente_bloquea_maximizar_beneficio_y_explica():
    r = responder("Maximiza el beneficio con 1000 €")
    assert r["decision"] == "BLOQUEADA" and "margenes" in r["conclusion"]


def test_texto_que_se_presenta_optimo_en_beneficio_se_bloquea():
    from policies import r_supuestos
    s = optimize_promo_program(1000, 4)
    ctx = Contexto("programa", [s], borrador="Este es el programa óptimo en beneficio.",
                   supuestos_declarados=True)
    assert r_supuestos(ctx).estado == BLOCK
    ctx.borrador = "La promoción es rentable."
    assert r_supuestos(ctx).estado == BLOCK


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas de objetivos correctas.")
