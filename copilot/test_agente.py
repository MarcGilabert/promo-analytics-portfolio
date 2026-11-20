"""Pruebas del agente (SDK de Anthropic, tool runner) sin red ni clave de API.

Se usa el cliente real del SDK con un transporte HTTP simulado: la API devuelve
respuestas guionizadas (pedir herramientas y luego redactar) y el tool runner del
SDK ejecuta de verdad las herramientas del copiloto.
"""
import json
import os
import shutil
import tempfile

import httpx2 as httpx
import anthropic

import agente
import decision_record
from tools import get_category_forecast

decision_record.DIR = tempfile.mkdtemp()


def _mensaje(contenido, stop):
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "test",
            "content": contenido, "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1}}


def _uso(nombre, entrada, i=0):
    return {"type": "tool_use", "id": f"toolu_{nombre}_{i}", "name": nombre, "input": entrada}


def cliente_guionizado(pasos):
    """pasos: lista de funciones(peticion_json) -> mensaje. Guarda las peticiones."""
    peticiones = []

    def manejar(req: httpx.Request):
        cuerpo = json.loads(req.content)
        peticiones.append(cuerpo)
        return httpx.Response(200, json=pasos[len(peticiones) - 1](cuerpo))

    c = anthropic.Anthropic(api_key="test", http_client=httpx.Client(
        transport=httpx.MockTransport(manejar)))
    return c, peticiones


def _resultados(cuerpo):
    """Resultados de herramientas que el SDK devolvio al modelo en la ultima peticion."""
    ultimo = cuerpo["messages"][-1]["content"]
    return [json.loads(b["content"] if isinstance(b["content"], str) else b["content"][0]["text"])
            for b in ultimo if b.get("type") == "tool_result"]


def test_agente_llama_herramienta_y_responde_con_cifras_verificadas():
    real = get_category_forecast("FLUID MILK PRODUCTS", 1)
    total = real["resultado"]["prediccion_total"]
    vistos = {}

    def paso2(cuerpo):
        vistos["res"] = _resultados(cuerpo)
        return _mensaje([{"type": "text", "text":
                          f"La próxima semana se prevén unas {total:.0f} unidades de leche."}],
                        "end_turn")

    c, pet = cliente_guionizado([
        lambda b: _mensaje([_uso("prevision_demanda",
                                 {"categoria": "FLUID MILK PRODUCTS", "horizonte": 1})], "tool_use"),
        paso2])
    r = agente.responder("¿Cuánto venderé de leche la próxima semana?", cliente=c)
    assert len(pet) == 2, "el tool runner hace dos llamadas: pedir herramienta y redactar"
    assert {t["name"] for t in pet[0]["tools"]} >= {"prevision_demanda", "surtido",
                                                    "decisiones_registradas"}
    assert vistos["res"][0]["estado"] in ("ENTREGAR", "ENTREGAR_CON_AVISO")
    assert "texto_verificado" in vistos["res"][0]
    assert r["modo"] == "agente" and r["redaccion_original"] is None
    assert str(round(total)) in r["respuesta"].replace(".", "")
    assert r["llamadas"][0]["herramienta"] == "prevision_demanda"
    assert all(e == "pass" for _, e, _ in r["veredictos"])
    print("OK test_agente_llama_herramienta_y_responde_con_cifras_verificadas")


def test_cifra_inventada_se_sustituye_por_texto_verificado():
    c, _ = cliente_guionizado([
        lambda b: _mensaje([_uso("prevision_demanda",
                                 {"categoria": "SOUP", "horizonte": 1})], "tool_use"),
        lambda b: _mensaje([{"type": "text", "text":
                             "Se venderán 987654 unidades de sopa."}], "end_turn")])
    r = agente.responder("¿Cuánto venderé de sopa la próxima semana?", cliente=c)
    assert r["redaccion_original"] == "Se venderán 987654 unidades de sopa."
    assert "987654" not in r["respuesta"]
    assert r["decision"] in ("ENTREGAR_CON_AVISO", "BLOQUEADA")
    assert any(rg == "Cifras de la respuesta" and e == "block" for rg, e, _ in r["veredictos"])
    print("OK test_cifra_inventada_se_sustituye_por_texto_verificado")


def test_encadena_varias_herramientas_en_un_turno():
    c, pet = cliente_guionizado([
        lambda b: _mensaje([_uso("prevision_demanda", {"categoria": "CHEESE", "horizonte": 1}, 1),
                            _uso("evaluar_promocion", {"categoria": "CHEESE"}, 2)], "tool_use"),
        lambda b: _mensaje([{"type": "text", "text":
                             "Tienes la previsión y el efecto de la promoción de queso."}],
                           "end_turn")])
    r = agente.responder("Previsión de queso y efecto de una promoción", cliente=c)
    assert [x["herramienta"] for x in r["llamadas"]] == ["prevision_demanda", "evaluar_promocion"]
    assert len(_resultados(pet[1])) == 2
    print("OK test_encadena_varias_herramientas_en_un_turno")


def test_herramienta_bloqueada_no_respalda_cifras():
    def paso2(cuerpo):
        res = _resultados(cuerpo)[0]
        assert res["estado"] == "BLOQUEADA" and "datos" not in res
        return _mensaje([{"type": "text", "text": "Serían 1500 unidades de cerveza."}], "end_turn")

    c, _ = cliente_guionizado([
        lambda b: _mensaje([_uso("prevision_demanda", {"categoria": "BEER", "horizonte": 4})],
                           "tool_use"), paso2])
    r = agente.responder("Previsión de cerveza para 4 semanas", cliente=c)
    assert r["decision"] == "BLOQUEADA"
    assert "1500" not in r["respuesta"]
    print("OK test_herramienta_bloqueada_no_respalda_cifras")


def test_lenguaje_prohibido_se_bloquea():
    c, _ = cliente_guionizado([
        lambda b: _mensaje([_uso("programa_promocional",
                                 {"presupuesto_eur": 1000, "semanas": 4})], "tool_use"),
        lambda b: _mensaje([{"type": "text", "text":
                             "Este programa es el óptimo en beneficio."}], "end_turn")])
    r = agente.responder("Programa de promociones con 1000 €", cliente=c)
    assert r["redaccion_original"] is not None
    assert r["respuesta"] != "Este programa es el óptimo en beneficio."
    assert any(rg == "Lenguaje controlado" and e == "block" for rg, e, _ in r["veredictos"])
    print("OK test_lenguaje_prohibido_se_bloquea")


def test_sin_clave_responde_por_reglas():
    os.environ.pop("ANTHROPIC_API_KEY", None)
    r = agente.responder("¿Cuánto venderé de leche la próxima semana?")
    assert r["modo"] == "reglas" and r["llamadas"][0]["herramienta"] == "prevision_demanda"
    assert all(e == "pass" for _, e, _ in r["veredictos"])
    r = agente.responder("¿Qué decisiones hay pendientes de aprobación?")
    assert r["llamadas"][0]["herramienta"] == "decisiones_registradas"
    r = agente.responder("¿Qué tiempo hará mañana?")
    assert r["llamadas"] == [] and "No he identificado" in r["respuesta"]
    print("OK test_sin_clave_responde_por_reglas")


if __name__ == "__main__":
    try:
        for nombre, fn in list(globals().items()):
            if nombre.startswith("test_"):
                fn()
        print("Pruebas del agente correctas.")
    finally:
        shutil.rmtree(decision_record.DIR, ignore_errors=True)
