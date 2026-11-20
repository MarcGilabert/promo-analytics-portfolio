"""Registro de decisiones comerciales (paso 5).

La auditoria (audit.py) registra cada EJECUCION del copiloto. Este modulo registra
cada DECISION de negocio y su ciclo de vida:

    propuesta ──► aprobada
        │    └──► rechazada
        └──► en_revision ──► aprobada | rechazada

Cada registro guarda lo necesario para reconstruir y defender la decision:
periodo y version de los datos, modelo y version de las politicas, objetivo y
restricciones, escenarios evaluados, recomendacion, resultados esperados con su
nivel de evidencia, supuestos, limites, robustez y veredictos de las politicas.

Reglas de gobierno:
  - Nadie aprueba una recomendacion bloqueada por las politicas.
  - Aprobar una recomendacion con avisos exige reconocerlos expresamente.
  - Aprobar o rechazar exige usuario y motivo. Los estados finales no cambian:
    para reconsiderar, se crea una decision nueva que sustituye a la anterior.
  - El contenido se sella con una huella SHA-256: si alguien lo edita despues,
    la verificacion lo detecta. El historial de estados es solo de anadir.
  - Nunca se registran claves ni secretos.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime

DIR = os.path.join(os.path.dirname(__file__), "decisions")
PERIODO_DATOS = "Dunnhumby The Complete Journey: 711 dias, 2.500 hogares"

TRANSICIONES = {
    "propuesta": {"aprobada", "rechazada", "en_revision"},
    "en_revision": {"aprobada", "rechazada"},
    "aprobada": set(),
    "rechazada": set(),
}


class ErrorRegistro(Exception):
    """Operacion no permitida sobre una decision."""


def _ruta(decision_id):
    return os.path.join(DIR, decision_id + ".json")


def _huella(contenido: dict) -> str:
    canon = json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _guardar(reg):
    os.makedirs(DIR, exist_ok=True)
    with open(_ruta(reg["decision_id"]), "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2, default=str)


def _resumen_escenario(e):
    return {"nombre": e["nombre"], "descripcion": e["descripcion"], "viable": e["viable"],
            "restricciones_incumplidas": e["restricciones_incumplidas"],
            "valor_objetivo": e["valor_objetivo"], "metricas": e["metricas"],
            "calendario": [{"semana": r["semana"], "categoria": r["categoria"]}
                           for r in e["calendario"]]}


def crear(salida_decision: dict, politica: dict, audit_id: str | None = None,
          creado_por: str = "copiloto", sustituye_a: str | None = None) -> dict:
    """Crea el registro de una recomendacion del motor de decision.

    politica = {"decision": "ENTREGAR" | "ENTREGAR_CON_AVISO" | "BLOQUEADA",
                "veredictos": [(regla, estado, mensaje), ...], "policy_version": "x.y.z"}
    """
    if not salida_decision.get("ok") or salida_decision.get("tool") != "recommend_promo_decision":
        raise ErrorRegistro("Solo se registran recomendaciones validas del motor de decision.")
    R, M, P = salida_decision["resultado"], salida_decision["metadata"], salida_decision["parametros"]
    if sustituye_a:
        anterior = leer(sustituye_a)
        if anterior["estado"] not in ("rechazada", "en_revision", "propuesta"):
            raise ErrorRegistro("Solo se sustituye una decision no aprobada.")

    contenido = {
        "datos": {"version": salida_decision["version_datos"], "periodo": PERIODO_DATOS},
        "modelo": M["modelo"],
        "politicas": {"version": politica.get("policy_version"),
                      "decision": politica["decision"],
                      "veredictos": [{"regla": r, "estado": e, "mensaje": m}
                                     for r, e, m in politica["veredictos"]]},
        "objetivo": {"nombre": P["objetivo"], "descripcion": M["objetivo_descripcion"]},
        "parametros": {k: v for k, v in P.items() if k != "categoria"},
        "escenarios": [_resumen_escenario(e) for e in R["escenarios"]],
        "recomendacion": {"escenario": R["recomendacion"]["escenario"],
                          "descripcion": R["recomendacion"]["descripcion"],
                          "palancas": R["recomendacion"]["palancas"],
                          "calendario": [{"semana": r["semana"], "categoria": r["categoria"]}
                                         for r in R["recomendacion"]["calendario"]],
                          "resultado_esperado": R["recomendacion"]["metricas"],
                          "evidencia": M.get("evidencia", {})},
        "por_que": R["por_que"],
        "compromisos": R["compromisos"],
        "descartadas": R["descartadas"],
        "robustez": R["robustez"],
        "supuestos": M["supuestos"],
        "supuestos_criticos": R["supuestos_criticos"],
        "limites": M["limites"],
        "run_ids": {"decision": salida_decision["run_id"],
                    "comparacion": salida_decision.get("comparacion_run_id")},
        "audit_id": audit_id,
    }
    ahora = datetime.now().isoformat(timespec="seconds")
    reg = {
        "decision_id": "dec_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6],
        "creado": ahora,
        "creado_por": creado_por,
        "sustituye_a": sustituye_a,
        "estado": "propuesta",
        "contenido": contenido,
        "huella": _huella(contenido),
        "historial": [{"fecha": ahora, "de": None, "a": "propuesta", "usuario": creado_por,
                       "motivo": "recomendacion generada por el motor de decision"}],
    }
    _guardar(reg)
    return reg


def leer(decision_id: str, verificar: bool = True) -> dict:
    ruta = _ruta(decision_id)
    if not os.path.exists(ruta):
        raise ErrorRegistro(f"No existe la decision {decision_id}.")
    with open(ruta, encoding="utf-8") as fh:
        reg = json.load(fh)
    if verificar and _huella(reg["contenido"]) != reg["huella"]:
        raise ErrorRegistro(f"La decision {decision_id} se ha modificado despues de crearse "
                            "(la huella no coincide).")
    return reg


def cambiar_estado(decision_id: str, nuevo: str, usuario: str, motivo: str,
                   avisos_reconocidos: bool = False) -> dict:
    reg = leer(decision_id)
    actual = reg["estado"]
    if nuevo not in TRANSICIONES.get(actual, set()):
        raise ErrorRegistro(f"Transicion no permitida: {actual} -> {nuevo}.")
    if not usuario or not usuario.strip():
        raise ErrorRegistro("Hace falta identificar quien decide.")
    if nuevo in ("aprobada", "rechazada") and (not motivo or len(motivo.strip()) < 5):
        raise ErrorRegistro("Aprobar o rechazar exige un motivo.")
    pol = reg["contenido"]["politicas"]
    if nuevo == "aprobada":
        if pol["decision"] == "BLOQUEADA":
            raise ErrorRegistro("No se puede aprobar una recomendacion bloqueada por las "
                                "politicas.")
        if pol["decision"] == "ENTREGAR_CON_AVISO" and not avisos_reconocidos:
            raise ErrorRegistro("La recomendacion tiene avisos: hay que reconocerlos para "
                                "aprobarla.")
    evento = {"fecha": datetime.now().isoformat(timespec="seconds"), "de": actual, "a": nuevo,
              "usuario": usuario.strip(), "motivo": (motivo or "").strip()}
    if nuevo == "aprobada" and pol["decision"] == "ENTREGAR_CON_AVISO":
        evento["avisos_reconocidos"] = [v["mensaje"] for v in pol["veredictos"]
                                        if v["estado"] == "warn"]
    reg["historial"].append(evento)
    reg["estado"] = nuevo
    _guardar(reg)
    return reg


def listar(estado: str | None = None) -> list:
    if not os.path.isdir(DIR):
        return []
    out = []
    for f in sorted(os.listdir(DIR), reverse=True):
        if f.endswith(".json"):
            reg = leer(f[:-5], verificar=False)
            reg["integra"] = _huella(reg["contenido"]) == reg["huella"]
            if estado is None or reg["estado"] == estado:
                out.append(reg)
    return out


def reproducir(decision_id: str) -> dict:
    """Vuelve a ejecutar el motor con los parametros guardados y compara la
    recomendacion y el resultado esperado. Sirve para demostrar que la decision
    es reproducible con la misma version de datos."""
    from decision_engine import recommend_promo_decision
    reg = leer(decision_id)
    c = reg["contenido"]
    p = dict(c["parametros"])
    horizonte = p.pop("horizonte")
    nueva = recommend_promo_decision(semanas=horizonte, **p)
    if not nueva.get("ok"):
        return {"reproducible": False, "motivo": nueva.get("motivo")}
    rec_n = nueva["resultado"]["recomendacion"]
    misma = (rec_n["escenario"] == c["recomendacion"]["escenario"] and
             [(r["semana"], r["categoria"]) for r in rec_n["calendario"]] ==
             [(r["semana"], r["categoria"]) for r in c["recomendacion"]["calendario"]] and
             rec_n["metricas"] == c["recomendacion"]["resultado_esperado"])
    return {"reproducible": misma,
            "version_datos_igual": nueva["version_datos"] == c["datos"]["version"],
            "motivo": "" if misma else "la recomendacion o sus metricas han cambiado"}
