"""Registro de auditoria: un fichero JSON por ejecucion.

Permite reconstruir una ejecucion completa: que se pregunto, que se SOLICITO
ejecutar, que se EJECUTO realmente (con errores), que se APROBO, con que datos,
version de politicas y modelo, y que afirmaciones se verificaron.
Nunca registra claves ni secretos.
"""
import json
import os
import uuid
from datetime import datetime

RUNS = os.path.join(os.path.dirname(__file__), "runs")
os.makedirs(RUNS, exist_ok=True)


def registrar(pregunta, salidas_tools, veredictos, decision, conclusion, claims=None,
              modo=None, modelo_llm=None, policy_version=None, solicitado=None,
              ejecutado=None, aprobado=None, errores=None):
    ahora = datetime.now()
    registro = {
        "audit_id": "audit_" + ahora.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4],
        "fecha": ahora.isoformat(timespec="seconds"),
        "pregunta": pregunta,
        "modo": modo,                          # llm | reglas
        "modelo_llm": modelo_llm,              # None en modo determinista
        "policy_version": policy_version,
        "solicitado": solicitado,              # tool y argumentos pedidos
        "ejecutado": ejecutado or [],          # que corrio y si tuvo exito
        "aprobado": aprobado,                  # si la respuesta se entrego
        "run_ids": [s.get("run_id") for s in salidas_tools if s.get("run_id")],
        "version_datos": [s.get("version_datos") for s in salidas_tools],
        "resultados": [s.get("resultado") for s in salidas_tools],
        "metadatos": [s.get("metadata") for s in salidas_tools],
        "claims": claims or [],
        "checks": [{"regla": v.regla, "estado": v.estado, "mensaje": v.mensaje}
                   for v in veredictos],
        "decision": decision,
        "conclusion": conclusion,
        "errores": errores or [],
    }
    ruta = os.path.join(RUNS, registro["audit_id"] + ".json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(registro, fh, ensure_ascii=False, indent=2, default=str)
    registro["_ruta"] = ruta
    return registro


def historial(limite=50):
    files = sorted(os.listdir(RUNS), reverse=True)[:limite]
    out = []
    for f in files:
        if f.endswith(".json"):
            with open(os.path.join(RUNS, f), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out
