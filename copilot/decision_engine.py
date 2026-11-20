"""Motor de decision comercial (paso 4).

Toma la comparacion de escenarios y devuelve una recomendacion trazable:

  1. Recomendacion: el escenario viable con mejor valor del objetivo (ventas o
     volumen). A igualdad, el de menor coste y menos promociones.
  2. Por que gana: ventaja frente al segundo y frente al actual, en el objetivo.
  3. Compromisos: metricas en las que la recomendacion es peor que el actual.
  4. Robustez:
       - margen: beneficio ilustrativo con margen -5 pp, base y +5 pp
       - modelo: si el ganador se mantiene con el volumen promocional un WAPE
         por debajo y por encima de lo previsto, y si la mejora frente a no
         promocionar sigue siendo positiva con el volumen un WAPE por debajo
  5. Supuestos criticos: margen del distribuidor a partir del cual la
     recomendacion deja de perder dinero.

El motor no aprueba nada: la recomendacion sale con estado "propuesta" y la
aprueba o rechaza una persona (paso 5). El LLM no participa en ningun calculo.
"""
import uuid
from datetime import datetime

import pandas as pd

import roi_logic
from scenarios import METRICAS_COMPARADAS, compare_scenarios
from tools import DATA, OBJETIVOS, _load_roi, actividad, comprobar_restricciones

# Para estas metricas, mas es mejor; para coste y descuento, menos es mejor.
MAS_ES_MEJOR = {"unidades_incrementales": True, "ventas_incrementales_eur": True,
                "beneficio_eur": True, "roi": True, "coste_eur": False,
                "descuento_total_eur": False}
MARGEN_CRITICO_MAX_PP = 30      # tope de busqueda del margen critico


def _wape(categoria):
    store = pd.read_csv(f"{DATA}/forecast_store.csv").set_index("categoria")
    return float(store.loc[categoria, "wape_referencia"])


def _objetivo_con_error(calendario, palancas, objetivo, signo):
    """Valor del objetivo si el volumen en semana de promocion fuera un WAPE
    menor (signo -1) o mayor (signo +1) que lo previsto."""
    par_df = _load_roi()
    total = 0.0
    for r in calendario:
        par = par_df.loc[r["categoria"]].to_dict()
        f = 1 + signo * _wape(r["categoria"])
        ue = roi_logic.unidades_promo(par, *actividad(par, palancas["mecanica"])) * f
        ub, p, pb = par["unidades_base"], par["precio_lista"], par["pct_base"]
        if objetivo == "volumen":
            total += ue - ub
        else:
            total += ue * p * (1 - (pb + 0.15)) - ub * p * (1 - pb)
    return round(total)


def _margen_critico_pp(calendario, palancas):
    """Puntos de margen que habria que sumar al margen supuesto para que el calendario
    no pierda dinero. 0 si ya no pierde; None si ni con +30 puntos deja de perder."""
    if not calendario:
        return None
    par_df = _load_roi()
    for pp in range(MARGEN_CRITICO_MAX_PP + 1):
        ben = 0.0
        for r in calendario:
            par = par_df.loc[r["categoria"]].to_dict()
            pct = float(par["pct_base"]) + 0.15
            e = roi_logic.evaluar(par, *actividad(par, palancas["mecanica"]), pct,
                                  float(par["margen_defecto"]) + pp / 100)
            ben += e["beneficio_incremental_eur"]
        if ben >= 0:
            return pp
    return None


def recommend_promo_decision(**kw) -> dict:
    """Recomendacion sobre los escenarios de compare_scenarios (mismos argumentos)."""
    comp = compare_scenarios(**kw)
    run_id = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    base = {"run_id": run_id, "tool": "recommend_promo_decision",
            "parametros": {**comp["parametros"], "categoria": "DECISION"},
            "comparacion_run_id": comp["run_id"], "version_datos": comp["version_datos"],
            "generado": datetime.now().isoformat(timespec="seconds"), "economico": True}
    if not comp["ok"]:
        return {**base, "ok": False, "tipo_error": comp["tipo_error"], "motivo": comp["motivo"]}

    objetivo = comp["parametros"]["objetivo"]
    esc = {e["nombre"]: e for e in comp["resultado"]["escenarios"]}
    ranking = comp["resultado"]["ranking"]
    if comp["resultado"]["mejor"] is None:
        return {**base, "ok": False, "tipo_error": "datos",
                "motivo": "Ningun escenario cumple las restricciones."}

    rec = esc[ranking[0]]
    viables = [n for n in ranking if esc[n]["viable"]]
    segundo = esc[viables[1]] if len(viables) > 1 else None
    actual = esc["actual"]

    # Compromisos: en que es peor la recomendacion que el escenario actual.
    compromisos = []
    for k in METRICAS_COMPARADAS:
        a, b = actual["metricas"][k], rec["metricas"][k]
        if a is None or b is None or rec["nombre"] == "actual":
            continue
        peor = b < a if MAS_ES_MEJOR[k] else b > a
        if peor:
            compromisos.append({"metrica": k, "frente_a": "actual",
                                "diferencia": round(b - a, 2)})

    # Robustez al margen supuesto.
    ilu = rec["metricas"]["beneficio_ilustrativo_eur"]
    pierde_en = [m for m, v in ilu.items() if v < 0] if rec["calendario"] else []

    # Robustez al error del modelo de volumen.
    valores_error = {}
    for nombre, signo in (("menos_volumen", -1), ("mas_volumen", +1)):
        vals = {n: _objetivo_con_error(esc[n]["calendario"], esc[n]["palancas"], objetivo, signo)
                for n in viables}
        ganador = sorted(viables, key=lambda n: (-vals[n], esc[n]["metricas"]["coste_eur"],
                                                 esc[n]["metricas"]["n_promociones"]))[0]
        valores_error[nombre] = {"valores": vals, "ganador": ganador}
    estable = all(v["ganador"] == rec["nombre"] for v in valores_error.values())
    rango_rec = [valores_error["menos_volumen"]["valores"][rec["nombre"]],
                 valores_error["mas_volumen"]["valores"][rec["nombre"]]]
    ventaja_actual = rec["valor_objetivo"] - actual["valor_objetivo"] if actual["viable"] else None
    # La mejora frente a no promocionar es distinguible del error del modelo si
    # sigue siendo positiva con el volumen un WAPE por debajo de lo previsto.
    supera_error = (min(rango_rec) > 0) if rec["calendario"] else None

    # Supuesto critico: margen necesario para no perder dinero.
    margen_crit = _margen_critico_pp(rec["calendario"], rec["palancas"])
    criticos = []
    if rec["calendario"]:
        criticos.append({
            "supuesto": "margen", "valor": "por categoria (supuesto)",
            "umbral": margen_crit,
            "efecto": ("pierde dinero en los escenarios de margen: " + ", ".join(pierde_en))
                      if pierde_en else "no pierde dinero en ningun escenario de margen"})

    descartadas = []
    for n in ranking[1:]:
        e = esc[n]
        motivo = ("incumple: " + ", ".join(e["restricciones_incumplidas"])) if not e["viable"] \
            else f"{OBJETIVOS[objetivo]['texto']} menor ({e['valor_objetivo']} frente a " \
                 f"{rec['valor_objetivo']})"
        descartadas.append({"escenario": n, "motivo": motivo})

    return {
        **base, "ok": True,
        "resultado": {
            "estado": "propuesta",
            "recomendacion": {"escenario": rec["nombre"], "descripcion": rec["descripcion"],
                              "palancas": rec["palancas"], "calendario": rec["calendario"],
                              "metricas": rec["metricas"],
                              "valor_objetivo": rec["valor_objetivo"]},
            "por_que": {
                "objetivo": objetivo,
                "segundo": segundo["nombre"] if segundo else None,
                "ventaja_vs_segundo": rec["valor_objetivo"] - segundo["valor_objetivo"]
                if segundo else None,
                "ventaja_vs_actual": ventaja_actual,
                "restricciones_activas": esc["optimizada"].get("restricciones_activas", [])
                if rec["nombre"] == "optimizada" else None,
            },
            "compromisos": compromisos,
            "robustez": {
                "margen": {"beneficio_ilustrativo_eur": ilu, "pierde_en": pierde_en},
                "modelo": {"wape": {r["categoria"]: _wape(r["categoria"])
                                    for r in rec["calendario"]},
                           "rango_objetivo_recomendacion": rango_rec,
                           "rango_por_escenario": {
                               n: [valores_error["menos_volumen"]["valores"][n],
                                   valores_error["mas_volumen"]["valores"][n]]
                               for n in viables},
                           "ganador_con_menos_volumen": valores_error["menos_volumen"]["ganador"],
                           "ganador_con_mas_volumen": valores_error["mas_volumen"]["ganador"],
                           "ganador_estable": estable,
                           "mejora_supera_error": supera_error},
            },
            "supuestos_criticos": criticos,
            "margen_critico_pp": margen_crit if rec["calendario"] else None,
            "margen_critico_tope_pp": MARGEN_CRITICO_MAX_PP,
            "descartadas": descartadas,
            "escenarios": comp["resultado"]["escenarios"],
        },
        "metadata": {
            **{k: v for k, v in comp["metadata"].items() if k != "restricciones"},
            "modelo": "Motor de decision sobre comparacion de escenarios (PuLP + reglas)",
            "regla_decision": "maximo valor del objetivo entre escenarios viables; a igualdad, "
                              "menor coste y menos promociones",
            "requiere_aprobacion_humana": True,
        },
    }


def verificar_recomendacion(salida: dict):
    """Recalcula que la recomendacion cumple sus restricciones (para las politicas)."""
    rec = salida["resultado"]["recomendacion"]
    p = salida["parametros"]
    params = {"horizonte": p["horizonte"], **rec["palancas"]}
    falsa = {"parametros": params,
             "resultado": {"calendario": rec["calendario"], "candidatas": [], "excluidas": []}}
    return [r["nombre"] for r in comprobar_restricciones(falsa)
            if not r["cumple"] and r["nombre"] != "roi_minimo"]
