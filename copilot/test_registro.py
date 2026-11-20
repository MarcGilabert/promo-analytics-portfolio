"""Paso 5: registro de decisiones, ciclo de vida e integridad."""
import json
import os
import tempfile

import decision_record as dr
from decision_engine import recommend_promo_decision

dr.DIR = tempfile.mkdtemp(prefix="decisions_")          # no ensucia el repo


def _registro(politica="ENTREGAR", veredictos=None):
    d = recommend_promo_decision(presupuesto_eur=1000, semanas=4, 
                                 objetivo="volumen", alternativa={"max_promos_categoria": 4})
    ver = veredictos or [("Recomendacion robusta", "pass", "ok")]
    return dr.crear(d, {"decision": politica, "veredictos": ver, "policy_version": "1.4.0"},
                    audit_id="audit_x")


def _falla(fn, *a, **k):
    try:
        fn(*a, **k)
    except dr.ErrorRegistro as e:
        return str(e)
    raise AssertionError("debia fallar")


def test_registro_guarda_lo_necesario_para_defender_la_decision():
    c = _registro()["contenido"]
    for k in ("datos", "modelo", "politicas", "objetivo", "parametros", "escenarios",
              "recomendacion", "por_que", "compromisos", "robustez", "supuestos",
              "supuestos_criticos", "limites", "run_ids"):
        assert c[k] not in (None, [], {}), k
    assert c["recomendacion"]["evidencia"]["beneficio_eur"]["nivel"] == "supuesto"


def test_nace_como_propuesta_y_se_aprueba_con_usuario_y_motivo():
    reg = _registro()
    assert reg["estado"] == "propuesta"
    reg = dr.cambiar_estado(reg["decision_id"], "aprobada", "MG", "encaja con el plan de volumen")
    assert reg["estado"] == "aprobada" and reg["historial"][-1]["usuario"] == "MG"


def test_estados_finales_no_cambian():
    reg = _registro()
    dr.cambiar_estado(reg["decision_id"], "rechazada", "MG", "financiacion no confirmada")
    assert "no permitida" in _falla(dr.cambiar_estado, reg["decision_id"], "aprobada", "MG",
                                    "cambio de opinion")


def test_revision_y_despues_aprobacion():
    reg = _registro()
    dr.cambiar_estado(reg["decision_id"], "en_revision", "MG", "pendiente de compras")
    reg = dr.cambiar_estado(reg["decision_id"], "aprobada", "MG", "compras confirma 90 %")
    assert [h["a"] for h in reg["historial"]] == ["propuesta", "en_revision", "aprobada"]


def test_aprobar_exige_motivo_y_usuario():
    reg = _registro()
    assert "motivo" in _falla(dr.cambiar_estado, reg["decision_id"], "aprobada", "MG", "")
    assert "quien" in _falla(dr.cambiar_estado, reg["decision_id"], "aprobada", " ", "motivo ok")


def test_no_se_aprueba_una_recomendacion_bloqueada():
    reg = _registro("BLOQUEADA", [("Grounding", "block", "cifra sin respaldo")])
    assert "bloqueada" in _falla(dr.cambiar_estado, reg["decision_id"], "aprobada", "MG",
                                 "la quiero igual")
    dr.cambiar_estado(reg["decision_id"], "rechazada", "MG", "bloqueada por grounding")


def test_aprobar_con_avisos_exige_reconocerlos_y_los_guarda():
    reg = _registro("ENTREGAR_CON_AVISO", [("Extrapolacion", "warn", "horizonte no validado")])
    assert "reconocer" in _falla(dr.cambiar_estado, reg["decision_id"], "aprobada", "MG",
                                 "vale la pena")
    reg = dr.cambiar_estado(reg["decision_id"], "aprobada", "MG", "acepto el riesgo",
                            avisos_reconocidos=True)
    assert reg["historial"][-1]["avisos_reconocidos"] == ["horizonte no validado"]


def test_contenido_editado_despues_se_detecta():
    reg = _registro()
    ruta = os.path.join(dr.DIR, reg["decision_id"] + ".json")
    datos = json.load(open(ruta, encoding="utf-8"))
    datos["contenido"]["recomendacion"]["resultado_esperado"]["unidades_incrementales"] += 500
    json.dump(datos, open(ruta, "w", encoding="utf-8"))
    assert "huella" in _falla(dr.leer, reg["decision_id"])
    assert not next(r for r in dr.listar() if r["decision_id"] == reg["decision_id"])["integra"]


def test_decision_reproducible_con_los_mismos_datos():
    reg = _registro()
    rep = dr.reproducir(reg["decision_id"])
    assert rep["reproducible"] and rep["version_datos_igual"]


def test_sustituir_una_decision_rechazada():
    viejo = _registro()
    dr.cambiar_estado(viejo["decision_id"], "rechazada", "MG", "probar con otra financiacion")
    d = recommend_promo_decision(presupuesto_eur=1000, semanas=4, 
                                 objetivo="volumen")
    nuevo = dr.crear(d, {"decision": "ENTREGAR", "veredictos": [], "policy_version": "1.4.0"},
                     sustituye_a=viejo["decision_id"])
    assert nuevo["sustituye_a"] == viejo["decision_id"]


def test_solo_registra_recomendaciones_validas():
    assert "Solo" in _falla(dr.crear, {"ok": False}, {"decision": "BLOQUEADA", "veredictos": []})


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
    print("Pruebas del registro de decisiones correctas.")
