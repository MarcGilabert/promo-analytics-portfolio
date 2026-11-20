"""Paso 4: motor de decision y politica de recomendacion robusta."""
from decision_engine import recommend_promo_decision, verificar_recomendacion
from policies import BLOCK, PASS, WARN, Contexto, r_robustez

ACTUAL = [{"semana": w, "categoria": c} for w in (1, 2) for c in ("CHEESE", "SOFT DRINKS",
                                                                   "BAG SNACKS")]


def _dec(**kw):
    base = dict(presupuesto_eur=1000, semanas=4, calendario_actual=ACTUAL)
    return recommend_promo_decision(**{**base, **kw})


def test_recomienda_el_mejor_viable_segun_el_objetivo():
    for obj in ("ventas", "volumen"):
        r = _dec(objetivo=obj, alternativa={"mecanica": "folleto"})
        esc = {e["nombre"]: e for e in r["resultado"]["escenarios"] if e["viable"]}
        mejor = max(e["valor_objetivo"] for e in esc.values())
        assert r["resultado"]["recomendacion"]["valor_objetivo"] == mejor


def test_estado_propuesta_y_requiere_aprobacion():
    r = _dec()
    assert r["resultado"]["estado"] == "propuesta"
    assert r["metadata"]["requiere_aprobacion_humana"]


def test_explica_ventaja_y_descartadas():
    r = _dec(objetivo="volumen", alternativa={"mecanica": "folleto"})
    pq = r["resultado"]["por_que"]
    assert pq["ventaja_vs_segundo"] >= 0 and pq["segundo"]
    assert len(r["resultado"]["descartadas"]) == len(r["resultado"]["escenarios"]) - 1


def test_compromisos_frente_al_actual():
    r = _dec(objetivo="volumen")
    comp = r["resultado"]["compromisos"]
    assert comp and all(c["frente_a"] == "actual" for c in comp)


def test_empate_elige_el_de_menor_coste():
    # Una alternativa idéntica a la base empata en el objetivo: gana la de menor coste.
    r = _dec(calendario_actual=None, alternativa={"max_promos_semana": 3})
    esc = {e["nombre"]: e for e in r["resultado"]["escenarios"]}
    rec = r["resultado"]["recomendacion"]
    assert esc["alternativa"]["valor_objetivo"] == esc["optimizada"]["valor_objetivo"]
    assert rec["metricas"]["coste_eur"] == min(esc["alternativa"]["metricas"]["coste_eur"],
                                               esc["optimizada"]["metricas"]["coste_eur"])


def test_supuesto_critico_es_el_margen():
    r = _dec(objetivo="volumen")["resultado"]
    crit = [c for c in r["supuestos_criticos"] if c["supuesto"] == "margen"]
    assert len(crit) == 1 and all(c["supuesto"] == "margen" for c in r["supuestos_criticos"])
    assert r["margen_critico_pp"] is None or 0 < r["margen_critico_pp"] <= r["margen_critico_tope_pp"]


def test_robusta_pasa_cuando_todo_aguanta():
    # Con 50 EUR no cabe ninguna promocion: recomendar no promocionar no pierde dinero.
    r = _dec(objetivo="volumen", presupuesto_eur=50)
    assert r_robustez(Contexto("", [r])).estado == PASS


def test_avisa_si_la_mejora_queda_dentro_del_error():
    r = _dec(objetivo="ventas")
    v = r_robustez(Contexto("", [r]))
    assert v.estado == WARN and "error del modelo" in v.mensaje


def test_avisa_si_pierde_dinero_con_algun_margen():
    r = _dec(objetivo="volumen", calendario_actual=None)
    v = r_robustez(Contexto("", [r]))
    assert v.estado == WARN and "margen supuesto" in v.mensaje


def test_recomendacion_manipulada_se_bloquea():
    r = _dec(objetivo="volumen")
    r["resultado"]["recomendacion"]["palancas"]["presupuesto_eur"] = 50
    assert verificar_recomendacion(r) == ["presupuesto"]
    assert r_robustez(Contexto("", [r])).estado == BLOCK


def test_errores_se_propagan():
    assert _dec(objetivo="beneficio")["tipo_error"] == "argumento"
    assert _dec(alternativa={"objetivo": "volumen"})["tipo_error"] == "argumento"


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas del motor de decision correctas.")
