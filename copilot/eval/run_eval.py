"""Evaluacion del agente.

Mide por separado tres ejes: seleccion de tool, enrutado de categoria y decision
de politica. Corre dos conjuntos: casos normales (camino feliz + bloqueos conocidos)
y casos adversos (argumentos invalidos, ambiguedad, sin sentido, limites).

Uso:  python eval/run_eval.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile  # noqa: E402

import decision_record  # noqa: E402
from agent import responder  # noqa: E402

decision_record.DIR = tempfile.mkdtemp(prefix="eval_decisions_")   # no ensucia el repo

AQUI = os.path.dirname(os.path.abspath(__file__))


def _primera(resultado, clave):
    for s in resultado["evidencia"]:
        if s.get("ok"):
            return s.get("tool") if clave == "tool" else s.get("parametros", {}).get("categoria")
    return None


def evaluar_archivo(nombre):
    casos = json.load(open(os.path.join(AQUI, nombre), encoding="utf-8"))
    filas = []
    for c in casos:
        r = responder(c["pregunta"])
        tool = _primera(r, "tool")
        cat = _primera(r, "categoria")
        filas.append({
            **c, "tool_obtenida": tool, "categoria_detectada": cat,
            "decision_obtenida": r["decision"],
            "ok_tool": tool == c["tool_esperada"],
            "ok_ruta": cat == c["categoria_esperada"],
            "ok_decision": r["decision"] == c["decision_esperada"],
        })
    return filas


def _resumen(nombre, filas):
    n = len(filas)
    t = sum(f["ok_tool"] for f in filas)
    r = sum(f["ok_ruta"] for f in filas)
    d = sum(f["ok_decision"] for f in filas)
    todo = sum(f["ok_tool"] and f["ok_ruta"] and f["ok_decision"] for f in filas)
    print(f"\n{nombre}  (n={n})")
    print(f"  Seleccion de tool: {t}/{n} = {t/n:.0%}")
    print(f"  Enrutado:          {r}/{n} = {r/n:.0%}")
    print(f"  Decision:          {d}/{n} = {d/n:.0%}")
    print(f"  Todo correcto:     {todo}/{n} = {todo/n:.0%}")
    for f in filas:
        if not (f["ok_tool"] and f["ok_ruta"] and f["ok_decision"]):
            print(f"    FALLO {f['id']}: {f['pregunta']}")
            print(f"       tool {f['tool_esperada']}/{f['tool_obtenida']} · "
                  f"cat {f['categoria_esperada']}/{f['categoria_detectada']} · "
                  f"dec {f['decision_esperada']}/{f['decision_obtenida']}")
    return todo, n


def main():
    normales = evaluar_archivo("casos.json")
    adversos = evaluar_archivo("casos_adversos.json")
    ok1, n1 = _resumen("CASOS NORMALES", normales)
    ok2, n2 = _resumen("CASOS ADVERSOS", adversos)
    print(f"\nTOTAL todo-correcto: {ok1 + ok2}/{n1 + n2}")

    with open(os.path.join(AQUI, "resultados.json"), "w", encoding="utf-8") as fh:
        json.dump({"normales": normales, "adversos": adversos}, fh, ensure_ascii=False, indent=2)

    sys.exit(0 if (ok1 + ok2) == (n1 + n2) else 1)


if __name__ == "__main__":
    main()
