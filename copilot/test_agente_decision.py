"""Paso 6: la recomendacion pasa por el agente con todo el circuito de gobierno."""
import tempfile

import decision_record as dr
from agent import _ruta_reglas, ejecutar, responder
from claims import construir_claims, render, verificar_todos
from decision_engine import recommend_promo_decision
from policies import Contexto, evaluar

dr.DIR = tempfile.mkdtemp(prefix="decisions_")


def test_enruta_recomendaciones_y_alternativas():
    r = _ruta_reglas("Recomiéndame un programa de volumen con 1.000 €. "
                     "¿Y si permitimos 4 promociones por categoría?")
    assert r["tool"] == "recommend_promo_decision"
    assert r["parametros"]["objetivo"] == "volumen"
    assert r["parametros"]["alternativa"] == {"max_promos_categoria": 4}
    r = _ruta_reglas("Compara el programa con 1.000 € frente a solo folleto")
    assert r["parametros"]["alternativa"] == {"mecanica": "folleto"}


def test_pregunta_vaga_no_se_convierte_en_recomendacion():
    assert _ruta_reglas("¿Me recomiendas rebajar algo este mes?") is None


def test_recomendacion_se_entrega_con_afirmaciones_verificadas_y_se_registra():
    r = responder("Recomiéndame el programa de volumen de la próxima semana con 1.000 € "
                  "y 90 % de financiación")
    assert r["decision"] != "BLOQUEADA"
    assert r["claims"] and all(c["verificado"] for c in r["claims"])
    reg = dr.leer(r["decision_id"])
    assert reg["estado"] == "propuesta"
    assert reg["contenido"]["politicas"]["decision"] == r["decision"]
    assert reg["contenido"]["audit_id"] == r["audit_id"]


def test_el_texto_empieza_por_la_decision_y_no_dice_optimo_en_beneficio():
    r = responder("Recomiéndame el programa del próximo mes con 1.000 €")
    assert r["conclusion"].startswith("Recomendación (propuesta, pendiente de aprobación)")
    assert "no es un óptimo en beneficio" in r["conclusion"]


def test_cifra_de_la_recomendacion_manipulada_se_bloquea():
    d = recommend_promo_decision(presupuesto_eur=1000, semanas=1, 
                                 objetivo="volumen")
    cl = construir_claims(d)
    next(c for c in cl if c.metrica == "decision_unidades").valor += 300
    ver = verificar_todos(cl, [d])
    ctx = Contexto("decision", [d], borrador=render(d, cl), supuestos_declarados=True,
                   claims_verificados=ver)
    assert evaluar(ctx)[0] == "BLOQUEADA"


def test_recomendacion_bloqueada_no_se_puede_aprobar():
    r = responder("Recomiéndame un programa que maximice el beneficio con 1.000 €")
    assert r["decision"] == "BLOQUEADA" and r["decision_id"] is None


def test_ejecutar_desde_formulario_con_plan_actual():
    actual = [{"semana": 1, "categoria": "CHEESE"}, {"semana": 1, "categoria": "SOUP"}]
    r = ejecutar("formulario", {"tool": "recommend_promo_decision", "parametros": {
        "presupuesto_eur": 1000, "semanas": 1, "objetivo": "volumen",
        "calendario_actual": actual}})
    assert r["decision_id"] and any(c["metrica"] == "decision_ventaja_actual"
                                    for c in r["claims"])
    reg = dr.cambiar_estado(r["decision_id"], "aprobada", "MG", "plan de volumen validado",
                            avisos_reconocidos=True)
    assert reg["estado"] == "aprobada"


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas del agente con decisiones correctas.")
