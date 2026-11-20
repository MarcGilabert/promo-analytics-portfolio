"""Pruebas del circuito agente -> politicas -> auditoria."""
from agent import _cifras_citadas, responder
from policies import BLOCK, Contexto, evaluar
from tools import get_category_forecast


def test_grounding_detecta_cifra_inventada():
    out = get_category_forecast("FLUID MILK PRODUCTS", 4)
    texto_malo = "Venderás unas 9999 unidades."      # 9999 no viene de la tool
    cifras = _cifras_citadas(texto_malo, [out])
    assert any(rid is None for _, rid in cifras)
    ctx = Contexto(pregunta="x", salidas_tools=[out], borrador=texto_malo,
                   cifras_citadas=cifras)
    decision, veredictos = evaluar(ctx)
    assert decision == "BLOQUEADA"
    assert any(v.regla == "Grounding" and v.estado == BLOCK for v in veredictos)


def test_grounding_acepta_cifras_de_la_tool():
    out = get_category_forecast("FLUID MILK PRODUCTS", 4)
    total = out["resultado"]["prediccion_total"]
    cifras = _cifras_citadas(f"Previsión: {total} unidades en 4 semanas.", [out])
    assert all(rid is not None for _, rid in cifras)


def test_claim_canonico_verifica():
    from claims import construir_claims, verificar_todos
    out = get_category_forecast("FLUID MILK PRODUCTS", 4)
    verif = verificar_todos(construir_claims(out), [out])
    assert verif and all(ok for _, ok, _ in verif)


def test_claim_con_categoria_cambiada_se_rechaza():
    """Atribuir un valor real a OTRA categoria debe fallar la verificacion."""
    from claims import construir_claims, verificar
    out = get_category_forecast("FLUID MILK PRODUCTS", 4)
    claim = construir_claims(out)[0]
    claim.categoria = "CHEESE"          # mismo valor, categoria incorrecta
    assert verificar(claim, [out]) is False


def test_claim_con_valor_cambiado_se_rechaza():
    from claims import construir_claims, verificar
    out = get_category_forecast("FLUID MILK PRODUCTS", 4)
    claim = construir_claims(out)[0]
    claim.valor = claim.valor + 1000    # valor manipulado
    assert verificar(claim, [out]) is False


def test_forecast_estructura():
    out = get_category_forecast("FLUID MILK PRODUCTS", 4)
    assert out["ok"]
    assert out["resultado"]["prediccion_total"] > 0
    assert out["run_id"].startswith("run_")
    assert out["metadata"]["wape_referencia"] == 0.11


def test_categoria_desconocida_no_inventa():
    out = get_category_forecast("CERVEZA", 4)
    assert out["ok"] is False
    assert "resultado" not in out


def test_verde():
    r = responder("¿Cuánto venderé de leche la próxima semana?")
    assert r["decision"] == "ENTREGAR"


def test_roi_conocido_se_entrega():
    r = responder("¿Qué ROI tendrá una promo de leche?")
    assert r["decision"] in ("ENTREGAR", "ENTREGAR_CON_AVISO")
    assert r["evidencia"][0]["tool"] == "evaluate_promo_roi"


def test_bloqueo_economico_sin_datos():
    r = responder("¿Qué ROI tendrá una promo de cervezas?")
    assert r["decision"] == "BLOQUEADA"


def test_agente_elige_tool():
    assert responder("¿Cuánto venderé de queso en 4 semanas?")["evidencia"][0]["tool"] \
        == "get_category_forecast"
    assert responder("¿Es rentable una promo de queso?")["evidencia"][0]["tool"] \
        == "evaluate_promo_roi"


def test_bloqueo_sin_datos():
    r = responder("Previsión de cervezas 4 semanas")
    assert r["decision"] == "BLOQUEADA"


def test_aviso_fiabilidad():
    r = responder("¿Cuánto venderé de sopa en 4 semanas?")
    assert r["decision"] == "ENTREGAR_CON_AVISO"


def test_horizonte_invalido():
    assert get_category_forecast("FLUID MILK PRODUCTS", 0)["ok"] is False
    assert get_category_forecast("FLUID MILK PRODUCTS", 100)["ok"] is False


def test_roi_argumentos_invalidos():
    from tools import evaluate_promo_roi
    assert evaluate_promo_roi("FLUID MILK PRODUCTS", puntos_descuento_extra=90)["ok"] is False


def test_claim_con_periodo_cambiado_se_rechaza():
    from claims import construir_claims, verificar_detalle
    out = get_category_forecast("FLUID MILK PRODUCTS", 4)
    claim = construir_claims(out)[0]
    claim.periodo = "12 semanas"         # valor real, pero de otro plazo
    ok, motivo = verificar_detalle(claim, [out])
    assert ok is False and "periodo" in motivo


def test_claim_con_unidad_cambiada_se_rechaza():
    from claims import construir_claims, verificar_detalle
    out = get_category_forecast("FLUID MILK PRODUCTS", 4)
    claim = construir_claims(out)[0]
    claim.unidad = "EUR"                 # unidades presentadas como euros
    ok, motivo = verificar_detalle(claim, [out])
    assert ok is False and "unidad" in motivo


def test_horizonte_no_validado_avisa():
    r = responder("¿Cuánto venderé de leche en 4 semanas?")
    assert r["decision"] == "ENTREGAR_CON_AVISO"
    assert any(reg == "Extrapolacion" and est == "warn" for reg, est, _ in r["veredictos"])


def test_horizonte_validado_entrega():
    r = responder("¿Cuánto venderé de leche la próxima semana?")
    assert r["decision"] == "ENTREGAR"


def test_fallo_tecnico_distinto_de_falta_de_datos(monkeypatch=None):
    import tools
    original = tools.TOOLS["get_category_forecast"]["fn"]
    def roto(**_):
        raise RuntimeError("simulado")
    tools.TOOLS["get_category_forecast"]["fn"] = roto
    try:
        r = responder("¿Cuánto venderé de leche la próxima semana?")
    finally:
        tools.TOOLS["get_category_forecast"]["fn"] = original
    assert r["decision"] == "BLOQUEADA"
    msg = [m for reg, est, m in r["veredictos"] if est == "block"][0]
    assert "tecnico" in msg.lower()


def test_jerarquia_block_gana_a_todo():
    """Un claim manipulado bloquea aunque el modelo sea fiable y no haya avisos."""
    from claims import construir_claims, verificar_todos
    out = get_category_forecast("FLUID MILK PRODUCTS", 1)   # fiabilidad alta, h validado
    claims = construir_claims(out)
    claims[0].valor = claims[0].valor + 500
    ctx = Contexto(pregunta="x", salidas_tools=[out], borrador="",
                   claims_verificados=verificar_todos(claims, [out]))
    decision, veredictos = evaluar(ctx)
    assert decision == "BLOQUEADA"
    assert any(v.regla == "Fiabilidad del modelo" and v.estado == "pass" for v in veredictos)


def test_auditoria_reconstruible():
    import json
    r = responder("¿Qué ROI tendrá una promo de leche?")
    from audit import RUNS
    import os
    reg = json.load(open(os.path.join(RUNS, r["audit_id"] + ".json"), encoding="utf-8"))
    for k in ("modo", "policy_version", "solicitado", "ejecutado", "aprobado",
              "claims", "checks", "version_datos", "errores"):
        assert k in reg
    assert "ANTHROPIC_API_KEY" not in json.dumps(reg)


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Todas las pruebas pasan.")
