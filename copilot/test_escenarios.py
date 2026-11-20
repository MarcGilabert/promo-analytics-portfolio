"""Paso 3: comparacion de escenarios con las mismas metricas y restricciones."""
import random

from scenarios import METRICAS_COMPARADAS, compare_scenarios
from tools import OBJETIVOS, _load_roi, evaluar_promocion

CATS = list(_load_roi().index)


def _calendario_aleatorio(rng, semanas=4, huecos=3, por_cat=2):
    usadas, cal = {}, []
    for w in range(1, semanas + 1):
        for c in rng.sample(CATS, rng.randint(0, huecos)):
            if usadas.get(c, 0) < por_cat:
                usadas[c] = usadas.get(c, 0) + 1
                cal.append({"semana": w, "categoria": c})
    return cal


def test_mismas_metricas_en_todos_los_escenarios():
    r = compare_scenarios(1000, 4, alternativa={"mecanica": "folleto"})
    for e in r["resultado"]["escenarios"]:
        assert set(METRICAS_COMPARADAS) <= set(e["metricas"])
        assert set(e["diferencia_vs_actual"]) == set(METRICAS_COMPARADAS)


def test_optimizada_nunca_pierde_frente_a_un_actual_viable():
    rng = random.Random(7)
    for objetivo in OBJETIVOS:
        for _ in range(15):
            cal = _calendario_aleatorio(rng)
            r = compare_scenarios(1000, 4, objetivo=objetivo, calendario_actual=cal,
                                  roi_minimo=None)
            act, opt = r["resultado"]["escenarios"][0], r["resultado"]["escenarios"][-1]
            if act["viable"]:
                assert opt["valor_objetivo"] >= act["valor_objetivo"], (objetivo, cal)


def test_diferencias_frente_al_actual():
    cal = [{"semana": 1, "categoria": "CHEESE"}, {"semana": 2, "categoria": "SOUP"}]
    r = compare_scenarios(1000, 4, calendario_actual=cal)
    act, opt = r["resultado"]["escenarios"][0], r["resultado"]["escenarios"][-1]
    for k in METRICAS_COMPARADAS:
        if opt["metricas"][k] is not None and act["metricas"][k] is not None:
            assert opt["diferencia_vs_actual"][k] == round(opt["metricas"][k] - act["metricas"][k], 2)


def test_actual_que_incumple_restricciones_no_es_viable_y_va_al_final():
    cal = [{"semana": 1, "categoria": c} for c in CATS[:5]]      # 5 promos con 3 huecos
    r = compare_scenarios(1000, 4, calendario_actual=cal)
    act = r["resultado"]["escenarios"][0]
    assert not act["viable"] and "huecos_por_semana" in act["restricciones_incumplidas"]
    assert r["resultado"]["ranking"][-1] == "actual"


def test_actual_con_promociones_por_debajo_del_roi_minimo_se_senala():
    r = compare_scenarios(1000, 4, calendario_actual=[{"semana": 1, "categoria": "CHEESE"}],
                          roi_minimo=0.15)
    assert r["resultado"]["escenarios"][0]["promociones_bajo_roi_minimo"]


def test_sin_calendario_el_actual_es_la_actividad_media():
    r = compare_scenarios(1000, 4)
    act = r["resultado"]["escenarios"][0]
    assert act["metricas"]["n_promociones"] == 0 and act["valor_objetivo"] == 0


def test_alternativa_que_relaja_la_restriccion_activa_gana():
    # Con objetivo ventas la limitacion es el maximo de promociones por categoria.
    r = compare_scenarios(1000, 4, objetivo="volumen", alternativa={"max_promos_categoria": 4})
    assert "promociones_por_categoria" in r["resultado"]["escenarios"][-1]["restricciones_activas"]
    assert r["resultado"]["mejor"] == "alternativa"


def test_el_retailer_asume_todo_el_descuento():
    r = compare_scenarios(1000, 4, objetivo="volumen")
    for e in r["resultado"]["escenarios"]:
        m = e["metricas"]
        assert m["descuento_total_eur"] == m["coste_eur"]


def test_mecanica_parcial_aumenta_menos_las_ventas():
    ambos = evaluar_promocion("CHEESE", 15, "folleto_y_display")
    for m in ("folleto", "display"):
        assert evaluar_promocion("CHEESE", 15, m)["unidades_inc"] < ambos["unidades_inc"]


def test_errores_de_argumentos_y_datos():
    assert compare_scenarios(alternativa={"objetivo": "ventas"})["tipo_error"] == "argumento"
    assert compare_scenarios(alternativa={"puntos_descuento_extra": 30})["tipo_error"] == "argumento"
    assert compare_scenarios(calendario_actual=[{"semana": 1, "categoria": "CERVEZA"}])[
        "tipo_error"] == "datos"
    assert compare_scenarios(calendario_actual=[{"semana": 9, "categoria": "SOUP"}])[
        "tipo_error"] == "argumento"
    assert compare_scenarios(mecanica="radio")["tipo_error"] == "argumento"


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas de escenarios correctas.")
