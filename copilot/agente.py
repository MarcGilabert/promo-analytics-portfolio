"""Agente de preguntas con el SDK de Anthropic (tool runner).

Un solo agente con herramientas. El agente entiende la pregunta, decide que
herramientas llamar (puede encadenar varias) y redacta la respuesta. No calcula:

  1. Cada herramienta pasa por el mismo circuito de gobierno que el resto de la
     app (agent.ejecutar): calculo en Python, cifras verificadas, siete politicas
     y auditoria. El agente recibe el texto ya verificado y los datos.
  2. La respuesta final del agente se vuelve a comprobar: toda cifra que cite debe
     venir de una herramienta no bloqueada (o de la propia pregunta) y no puede
     presentar nada como optimo en beneficio. Si falla, se entrega el texto
     verificado de las herramientas en lugar de la redaccion del agente.
  3. Sin clave de API, responde el enrutador por reglas (una herramienta por
     pregunta), con la misma salida.
"""
import json
import re

import decision_record
import llm
from agent import _numeros, _ruta_reglas, ejecutar
from audit import registrar
from policies import FRASES_PROHIBIDAS, POLICY_VERSION, Veredicto
from surtido import NOMBRE_SUB
from tools import categorias_disponibles

MAX_ITERACIONES = 6
SEVERIDAD = {"ENTREGAR": 0, "ENTREGAR_CON_AVISO": 1, "BLOQUEADA": 2}

SISTEMA = """Eres el copiloto analitico de un retailer (datos de Dunnhumby). Respondes \
preguntas comerciales sobre prevision de demanda, promociones, surtido y decisiones \
registradas, en castellano, en 2 a 5 frases.

Reglas:
- No calculas nada. Toda cifra sale de una herramienta. Si una herramienta no da un dato, \
no lo afirmes ni lo estimes.
- Usa el campo texto_verificado de cada herramienta como base: ya esta comprobado.
- Si una herramienta devuelve estado BLOQUEADA, explica el motivo sin dar cifras de ella.
- Si la herramienta avisa (ENTREGAR_CON_AVISO), menciona el aviso.
- El beneficio y el ROI dependen de margenes supuestos: nunca digas que algo es optimo en \
beneficio ni rentable sin decir que es un supuesto.
- Las promociones se asocian a mas ventas; no afirmes que las causan.
- Si la pregunta no es sobre estos datos, dilo y sugiere que puedes responder."""


# ---- Herramientas ---------------------------------------------------------------

def _esquema(props: dict, requeridos=()):
    return {"type": "object", "properties": props, "required": list(requeridos)}


CATEGORIA = {"type": "string", "description": "categoria en ingles, tal como esta en los datos"}
OBJETIVO = {"type": "string", "enum": ["ventas", "volumen", "beneficio"],
            "description": "que maximizar: ventas en euros o volumen en unidades. El "
                           "beneficio no se optimiza (no hay margenes reales): pasalo solo "
                           "si el usuario lo pide, y el sistema explicara por que"}
MECANICA = {"type": "string", "enum": ["folleto_y_display", "folleto", "display"]}

DEFINICIONES = {
    "prevision_demanda": (
        "get_category_forecast",
        "Prevision de unidades por categoria para las proximas semanas, con su intervalo "
        "y el error medido del modelo.",
        _esquema({"categoria": CATEGORIA,
                  "horizonte": {"type": "integer", "description": "semanas, 1-12"}},
                 ["categoria"])),
    "evaluar_promocion": (
        "evaluate_promo_roi",
        "Efecto y ROI ilustrativo de una promocion en una categoria (margen supuesto).",
        _esquema({"categoria": CATEGORIA,
                  "puntos_descuento_extra": {"type": "number",
                                             "description": "puntos de descuento sobre el habitual"},
                  "mecanica": MECANICA}, ["categoria"])),
    "programa_promocional": (
        "optimize_promo_program",
        "Que categorias promocionar cada semana con un presupuesto, maximizando ventas o "
        "volumen con restricciones (huecos por semana, promociones por categoria).",
        _esquema({"presupuesto_eur": {"type": "number"},
                  "semanas": {"type": "integer", "description": "1-12"},
                  "objetivo": OBJETIVO, "mecanica": MECANICA,
                  "max_promos_semana": {"type": "integer"},
                  "max_promos_categoria": {"type": "integer"},
                  "max_descuento_total_eur": {"type": "number"}})),
    "recomendar_decision": (
        "recommend_promo_decision",
        "Recomienda que programa ejecutar: compara el plan actual, una alternativa y el "
        "optimo con el mismo objetivo, y explica compromisos y riesgos. Queda como propuesta "
        "pendiente de aprobacion humana.",
        _esquema({"presupuesto_eur": {"type": "number"},
                  "semanas": {"type": "integer", "description": "1-12"},
                  "objetivo": OBJETIVO, "mecanica": MECANICA,
                  "alternativa": {"type": "object", "description": "palancas que cambia la "
                                  "alternativa a comparar",
                                  "properties": {"presupuesto_eur": {"type": "number"},
                                                 "mecanica": MECANICA,
                                                 "max_promos_categoria": {"type": "integer"},
                                                 "max_promos_semana": {"type": "integer"}}}})),
    "surtido": (
        "optimize_assortment",
        "Cuantos fabricantes mantener en una subcategoria (refrescos por formato o pretzels) "
        "y que parte de las ventas se conserva, como rango entre 'nadie se cambia de marca' "
        "y 'se cambian los que ya compran otra'.",
        _esquema({"subcategoria": {"type": "string", "enum": list(NOMBRE_SUB),
                                   "description": "; ".join(f"{k} = {v}" for k, v in NOMBRE_SUB.items())},
                  "cobertura_objetivo": {"type": "number",
                                         "description": "fraccion de ventas a conservar, p. ej. 0.98"},
                  "max_grupos": {"type": "integer", "description": "fabricantes a mantener"}},
                 ["subcategoria"])),
}


def _datos(out: dict) -> dict:
    """Datos compactos de una ejecucion para el agente (no todo el resultado)."""
    r, tool = out["resultado"], out["tool"]
    d = {"metricas": {k: v for k, v in r.get("metricas", {}).items() if v is not None}}
    if tool == "get_category_forecast":
        d.update(prediccion_semanal=r["prediccion_semanal"], intervalo_total=r["intervalo_total"])
    elif tool == "optimize_promo_program":
        d["calendario"] = [{k: x[k] for k in ("semana", "categoria", "unidades_inc",
                                               "ventas_inc_eur", "coste_eur")}
                           for x in r["calendario"]]
    elif tool == "optimize_assortment":
        d["grupos"] = [{"fabricante": g["fabricante"], "mantener": g["mantener"],
                        "ventas_a1": round(g["ventas_a1"])} for g in r["grupos"]]
    return d


class Sesion:
    """Guarda lo que el agente ha ejecutado en un turno."""

    def __init__(self, pregunta: str):
        self.pregunta = pregunta
        self.llamadas = []        # [{herramienta, tool, parametros, decision, audit_id, ...}]
        self.respaldo = set()     # cifras que el agente puede citar

    def _respaldar(self, objeto):
        for n in _numeros(json.dumps(objeto, ensure_ascii=False)):
            self.respaldo.add(n)
            if abs(n) <= 1:
                self.respaldo.add(round(n * 100, 1))      # 0.988 -> 98,8 %

    def ejecutar(self, nombre: str, parametros: dict) -> str:
        tool = DEFINICIONES[nombre][0]
        r = ejecutar(f"[Agente] {self.pregunta}", {"tool": tool, "parametros": parametros},
                     "agente")
        out = next((s for s in r["evidencia"] if s.get("ok")), None)
        respuesta = {"estado": r["decision"], "audit_id": r["audit_id"]}
        if r["decision"] == "BLOQUEADA" or out is None:
            respuesta["motivo"] = r["conclusion"]
        else:
            respuesta["texto_verificado"] = r["conclusion"]
            respuesta["datos"] = _datos(out)
            self._respaldar(respuesta)
        if r.get("decision_id"):
            respuesta["decision_id"] = r["decision_id"]
        self.llamadas.append({"herramienta": nombre, "tool": tool, "parametros": parametros,
                              "resultado": r})
        return json.dumps(respuesta, ensure_ascii=False, default=str)

    def decisiones(self, estado: str | None = None) -> str:
        regs = decision_record.listar(estado)[:10]
        lista = [{"decision_id": g["decision_id"], "estado": g["estado"], "creado": g["creado"],
                  "objetivo": g["contenido"]["objetivo"]["nombre"],
                  "escenario_recomendado": g["contenido"]["recomendacion"]["escenario"],
                  "integra": g["integra"]} for g in regs]
        respuesta = {"total": len(lista), "decisiones": lista}
        self._respaldar(respuesta)
        self.llamadas.append({"herramienta": "decisiones_registradas", "tool": None,
                              "parametros": {"estado": estado}, "resultado": None})
        return json.dumps(respuesta, ensure_ascii=False)


def herramientas(sesion: Sesion) -> list:
    """Herramientas del agente en formato del SDK (@beta_tool)."""
    from anthropic import beta_tool

    def crear(nombre, descripcion, esquema):
        def fn(**kw):
            return sesion.ejecutar(nombre, kw)
        return beta_tool(fn, name=nombre, description=descripcion, input_schema=esquema)

    out = [crear(n, d, e) for n, (_, d, e) in DEFINICIONES.items()]

    def decisiones_registradas(estado: str | None = None) -> str:
        return sesion.decisiones(estado)
    out.append(beta_tool(
        decisiones_registradas, name="decisiones_registradas",
        description="Lista las decisiones registradas (propuesta, aprobada, rechazada) "
                    "con su escenario recomendado e integridad.",
        input_schema=_esquema({"estado": {"type": "string",
                                          "enum": ["propuesta", "aprobada", "rechazada"]}})))
    return out


# ---- Gobierno de la respuesta final ------------------------------------------------

def _sin_respaldo(texto: str, sesion: Sesion) -> list:
    permitidas = sesion.respaldo | set(_numeros(sesion.pregunta))
    return [n for n in _numeros(texto)
            if not any(abs(n - v) < 0.5 or (v and abs(n - v) / abs(v) < 0.001)
                       for v in permitidas)]


def revisar(texto: str, sesion: Sesion):
    """Veredictos sobre la redaccion final del agente."""
    veredictos = []
    sueltas = _sin_respaldo(texto, sesion)
    if sueltas:
        veredictos.append(Veredicto(
            "Cifras de la respuesta", "block",
            "La redacción citaba cifras que no salen de ninguna herramienta: "
            + ", ".join(f"{n:g}" for n in sueltas[:5]) + "."))
    else:
        veredictos.append(Veredicto("Cifras de la respuesta", "pass",
                                    "Todas las cifras salen de herramientas verificadas."))
    if FRASES_PROHIBIDAS.search(texto.lower().replace("no es un óptimo en beneficio", "")):
        veredictos.append(Veredicto("Lenguaje controlado", "block",
                                    "La redacción presentaba algo como óptimo en beneficio."))
    else:
        veredictos.append(Veredicto("Lenguaje controlado", "pass", "Sin afirmaciones prohibidas."))
    return veredictos


def _texto_verificado(sesion: Sesion) -> str:
    partes = [c["resultado"]["conclusion"] for c in sesion.llamadas if c["resultado"]]
    return " ".join(partes) or "No he podido responder con los datos disponibles."


# ---- Punto de entrada -------------------------------------------------------------

def responder(pregunta: str, historial: list | None = None, cliente=None) -> dict:
    """Responde una pregunta. Con clave de API (o un cliente inyectado) usa el agente
    del SDK; sin ella, el enrutador por reglas."""
    sesion = Sesion(pregunta)
    if cliente is None and not llm.disponible():
        return _por_reglas(pregunta, sesion)
    cliente = cliente or llm._cliente()

    mensajes = list(historial or []) + [{"role": "user", "content": pregunta}]
    sistema = SISTEMA + "\nCategorias disponibles: " + ", ".join(categorias_disponibles()) + "."
    runner = cliente.beta.messages.tool_runner(
        model=llm.MODELO, max_tokens=1200, system=sistema, messages=mensajes,
        tools=herramientas(sesion), max_iterations=MAX_ITERACIONES)
    final = runner.until_done()
    redaccion = "".join(b.text for b in final.content if getattr(b, "type", "") == "text").strip()
    return _cerrar(pregunta, sesion, redaccion, "agente")


def _por_reglas(pregunta: str, sesion: Sesion) -> dict:
    p = pregunta.lower()
    if re.search(r"decisi\w* (registrad|pendiente|aprobad|rechazad)|pendientes de aprob", p):
        estado = next((e for e, rx in (("propuesta", "pendiente"), ("aprobada", "aprobad"),
                                       ("rechazada", "rechazad")) if rx in p), None)
        datos = json.loads(sesion.decisiones(estado))
        texto = (f"Hay {datos['total']} decisiones registradas"
                 + (f" en estado {estado}" if estado else "") + ". "
                 + " ".join(f"{d['decision_id']} ({d['estado']}): {d['escenario_recomendado']}."
                            for d in datos["decisiones"][:5]))
        return _cerrar(pregunta, sesion, texto.strip(), "reglas")
    ruta = _ruta_reglas(pregunta)
    if ruta:
        nombre = next(n for n, (t, _, _) in DEFINICIONES.items() if t == ruta["tool"])
        sesion.ejecutar(nombre, ruta["parametros"])
        return _cerrar(pregunta, sesion, _texto_verificado(sesion), "reglas")
    texto = ("No he identificado qué analizar. Puedo responder sobre previsión de demanda, "
             "promociones, surtido de refrescos y pretzels, y decisiones registradas.")
    return _cerrar(pregunta, sesion, texto, "reglas")


def _cerrar(pregunta: str, sesion: Sesion, redaccion: str, modo: str) -> dict:
    veredictos = revisar(redaccion, sesion)
    respuesta, sustituida = redaccion, False
    if any(v.estado == "block" for v in veredictos):
        respuesta, sustituida = _texto_verificado(sesion), True

    estados = [c["resultado"]["decision"] for c in sesion.llamadas if c["resultado"]]
    decision = max(estados, key=SEVERIDAD.get) if estados else "ENTREGAR"
    if sustituida and decision == "ENTREGAR":
        decision = "ENTREGAR_CON_AVISO"

    salidas = [s for c in sesion.llamadas if c["resultado"] for s in c["resultado"]["evidencia"]]
    reg = registrar(
        pregunta, salidas, veredictos, decision, respuesta, modo=modo,
        modelo_llm=llm.MODELO if modo == "agente" else None, policy_version=POLICY_VERSION,
        solicitado=[{"herramienta": c["herramienta"], "parametros": c["parametros"]}
                    for c in sesion.llamadas],
        ejecutado=[{"herramienta": c["herramienta"],
                    "audit_id": c["resultado"]["audit_id"] if c["resultado"] else None}
                   for c in sesion.llamadas],
        aprobado=decision != "BLOQUEADA")
    return {
        "pregunta": pregunta, "modo": modo, "respuesta": respuesta, "decision": decision,
        "redaccion_original": redaccion if sustituida else None,
        "veredictos": [(v.regla, v.estado, v.mensaje) for v in veredictos],
        "llamadas": [{"herramienta": c["herramienta"], "parametros": c["parametros"],
                      "decision": c["resultado"]["decision"] if c["resultado"] else None,
                      "audit_id": c["resultado"]["audit_id"] if c["resultado"] else None,
                      "decision_id": c["resultado"].get("decision_id") if c["resultado"] else None,
                      "veredictos": c["resultado"]["veredictos"] if c["resultado"] else []}
                     for c in sesion.llamadas],
        "audit_id": reg["audit_id"],
    }
