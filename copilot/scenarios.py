"""Comparacion de escenarios promocionales (paso 3 del sistema de decision).

Tres escenarios evaluados con las MISMAS metricas, el MISMO objetivo y las
MISMAS restricciones, para que las diferencias se puedan atribuir a la decision:

  actual       el calendario que el retailer tiene previsto; si no se da, mantener
               la actividad promocional media observada (incremento cero).
  alternativa  el mejor programa si se cambia una palanca: presupuesto, mecanica,
               huecos o ROI minimo.
  optimizada   el programa optimo con las palancas actuales (PuLP).

La optimizada nunca puede quedar por debajo de una actual viable con las mismas
palancas: si ocurre, es un error del sistema y hay una prueba que lo vigila.
"""
import uuid
from datetime import datetime

import roi_logic
from tools import (DATA_VERSION, FECHA_SUPUESTOS, HORIZONTE_VALIDADO, LIMITES_COMUNES,
                   ESCENARIOS_MARGEN, MECANICAS, METRICAS, OBJETIVOS, _load_roi,
                   comprobar_restricciones, evidencia, evaluar_promocion,
                   optimize_promo_program)

PALANCAS_ALTERNATIVA = {"presupuesto_eur", "mecanica", "max_promos_semana",
                        "max_promos_categoria", "roi_minimo", "max_descuento_total_eur"}
METRICAS_COMPARADAS = ["unidades_incrementales", "ventas_incrementales_eur", "coste_eur",
                       "beneficio_eur", "roi", "descuento_total_eur"]


def _metricas_calendario(cal):
    coste = sum(r["coste_eur"] for r in cal)
    ben = sum(r["beneficio_eur"] for r in cal)
    ilustrativo = {esc: sum(r["beneficio_por_margen"][esc]["beneficio"] for r in cal)
                   for esc in ESCENARIOS_MARGEN}
    return {
        "unidades_incrementales": sum(r["unidades_inc"] for r in cal),
        "ventas_incrementales_eur": sum(r["ventas_inc_eur"] for r in cal),
        "coste_eur": coste,
        "beneficio_eur": ben,
        "roi": round(ben / coste, 2) if coste else None,
        "descuento_total_eur": sum(r["descuento_total_eur"] for r in cal),
        "n_promociones": len(cal),
        "beneficio_ilustrativo_eur": ilustrativo,
    }


def _escenario(nombre, descripcion, palancas, cal, params, objetivo, origen):
    """Empaqueta un escenario y comprueba sus restricciones con las mismas reglas
    que el optimizador."""
    m = _metricas_calendario(cal)
    falsa = {"parametros": params,
             "resultado": {"calendario": cal, "candidatas": [], "excluidas": []}}
    restr = comprobar_restricciones(falsa)
    duras = [r["nombre"] for r in restr if not r["cumple"] and r["nombre"] != "roi_minimo"]
    bajo_roi = any(r["nombre"] == "roi_minimo" and not r["cumple"] for r in restr)
    return {
        "nombre": nombre, "descripcion": descripcion, "origen": origen,
        "palancas": palancas, "calendario": cal, "metricas": m,
        "valor_objetivo": m[OBJETIVOS[objetivo]["metrica"]],
        "viable": not duras, "restricciones_incumplidas": duras,
        "promociones_bajo_roi_minimo": bajo_roi,
    }


def compare_scenarios(presupuesto_eur: float = 1000, semanas: int = 4,
                      objetivo: str = "ventas",
                      mecanica: str = "folleto_y_display",
                      calendario_actual: list | None = None,
                      alternativa: dict | list | None = None,
                      max_promos_semana: int = 3, max_promos_categoria: int = 2,
                      max_descuento_total_eur: float | None = None, **kw) -> dict:
    run_id = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    roi_minimo = kw.get("roi_minimo")
    palancas = {"presupuesto_eur": presupuesto_eur,
                "mecanica": mecanica, "max_promos_semana": max_promos_semana,
                "max_promos_categoria": min(max_promos_categoria, semanas)
                if isinstance(semanas, int) and semanas >= 1 else max_promos_categoria,
                "roi_minimo": roi_minimo, "max_descuento_total_eur": max_descuento_total_eur}
    base = {"run_id": run_id, "tool": "compare_scenarios",
            "parametros": {"categoria": "ESCENARIOS", "horizonte": semanas,
                           "objetivo": objetivo, **palancas,
                           "calendario_actual": calendario_actual,
                           "alternativa": alternativa},
            "version_datos": DATA_VERSION,
            "generado": datetime.now().isoformat(timespec="seconds"), "economico": True}

    def error(msg, tipo="argumento"):
        return {**base, "ok": False, "tipo_error": tipo, "motivo": msg}

    # Una o varias alternativas; con una sola se llama "alternativa".
    alternativas = [] if not alternativa else (
        [alternativa] if isinstance(alternativa, dict) else list(alternativa))
    if len(alternativas) > 5:
        return error("Como maximo 5 alternativas por comparacion.")
    for alt_d in alternativas:
        if not isinstance(alt_d, dict) or not alt_d:
            return error("Cada alternativa debe cambiar al menos una palanca.")
        if "objetivo" in alt_d:
            return error("La alternativa no puede cambiar el objetivo: los escenarios se "
                         "comparan con el mismo criterio.")
        ajenas = set(alt_d) - PALANCAS_ALTERNATIVA
        if ajenas:
            return error(f"Palancas no soportadas en la alternativa: {', '.join(sorted(ajenas))}. "
                         f"Validas: {', '.join(sorted(PALANCAS_ALTERNATIVA))}.")

    # Optimizada: valida tambien todos los argumentos comunes.
    opt = optimize_promo_program(presupuesto_eur, semanas, 15, max_promos_semana,
                                 max_promos_categoria, objetivo, roi_minimo,
                                 max_descuento_total_eur, mecanica)
    if not opt["ok"]:
        return {**base, "ok": False, "tipo_error": opt["tipo_error"], "motivo": opt["motivo"]}
    params_eval = {**opt["parametros"]}

    # Actual
    if calendario_actual:
        cats = set(_load_roi().index)
        cal_act = []
        for fila in calendario_actual:
            c, w = fila.get("categoria"), fila.get("semana")
            if c not in cats:
                return error(f"Categoria '{c}' del calendario actual no esta en los datos.",
                             "datos")
            if not isinstance(w, int) or not 1 <= w <= semanas:
                return error(f"Semana {w} del calendario actual fuera del horizonte (1 a {semanas}).")
            e = evaluar_promocion(c, 15, mecanica)
            cal_act.append({"semana": w, "categoria": c, "coste_eur": e["coste"],
                            "beneficio_eur": e["beneficio"], "roi": e["roi"]
                            if e["roi"] is not None else 0.0,
                            "unidades_inc": e["unidades_inc"], "ventas_inc_eur": e["ventas_inc"],
                            "descuento_total_eur": e["descuento"],
                            "beneficio_por_margen": e["beneficio_por_margen"]})
        cal_act.sort(key=lambda r: (r["semana"], r["categoria"]))
        actual = _escenario("actual", "Calendario previsto por el retailer", palancas,
                            cal_act, params_eval, objetivo, "calendario aportado por el usuario")
    else:
        actual = _escenario("actual", "Mantener la actividad promocional media observada",
                            palancas, [], params_eval, objetivo,
                            "referencia: las metricas se miden frente a la actividad media")

    escenarios = [actual]

    # Alternativas
    for i, alt_d in enumerate(alternativas, 1):
        nombre_alt = "alternativa" if len(alternativas) == 1 else f"alternativa_{i}"
        pal_alt = {**palancas, **alt_d}
        alt = optimize_promo_program(pal_alt["presupuesto_eur"], semanas,
                                     15, pal_alt["max_promos_semana"],
                                     pal_alt["max_promos_categoria"], objetivo,
                                     pal_alt["roi_minimo"], pal_alt["max_descuento_total_eur"],
                                     pal_alt["mecanica"])
        if not alt["ok"]:
            return {**base, "ok": False, "tipo_error": alt["tipo_error"],
                    "motivo": f"Alternativa {i}: " + alt["motivo"]}
        cambios = ", ".join(f"{k} {palancas[k]} -> {v}" for k, v in alt_d.items())
        esc_alt = _escenario(nombre_alt, f"Mejor programa cambiando: {cambios}", pal_alt,
                             alt["resultado"]["calendario"], alt["parametros"], objetivo,
                             "optimizador con palancas cambiadas")
        esc_alt["cambios"] = alt_d
        escenarios.append(esc_alt)

    esc_opt = _escenario("optimizada", "Programa optimo con las palancas actuales", palancas,
                         opt["resultado"]["calendario"], params_eval, objetivo,
                         "optimizador (PuLP)")
    esc_opt["restricciones_activas"] = [r["nombre"] for r in opt["metadata"]["restricciones"]
                                        if r["activa"]]
    escenarios.append(esc_opt)

    # Diferencias frente al actual, con las mismas metricas
    ref = actual["metricas"]
    for e in escenarios:
        e["diferencia_vs_actual"] = {
            k: None if e["metricas"][k] is None or ref[k] is None
            else round(e["metricas"][k] - ref[k], 2)
            for k in METRICAS_COMPARADAS}

    viables = [e for e in escenarios if e["viable"]]
    # Orden: objetivo de mayor a menor; a igualdad, menor coste y menos promociones
    # (no se recomienda gastar mas para obtener lo mismo).
    orden = sorted(viables, key=lambda e: (-e["valor_objetivo"], e["metricas"]["coste_eur"],
                                           e["metricas"]["n_promociones"]))
    ranking = [e["nombre"] for e in orden] + [e["nombre"] for e in escenarios if not e["viable"]]

    from tools import _fiab_roi
    baja = sorted({r["categoria"] for e in escenarios for r in e["calendario"]
                   if _fiab_roi(r["categoria"]) == "baja"})
    return {
        **base, "ok": True,
        "resultado": {
            "escenarios": escenarios,
            "ranking": ranking,
            "mejor": ranking[0] if viables else None,
        },
        "metadata": {
            "modelo": "Evaluacion comun de escenarios sobre ROI por categoria + PuLP",
            "objetivo": objetivo,
            "objetivo_descripcion": OBJETIVOS[objetivo]["texto"],
            "metricas_comparadas": METRICAS_COMPARADAS,
            "evidencia": evidencia({k: 1 for k in METRICAS_COMPARADAS}),
            "unidades": {k: METRICAS[k] for k in METRICAS_COMPARADAS},
            "horizonte_validado": HORIZONTE_VALIDADO,
            "categorias_baja_fiabilidad": baja,
            "restricciones": opt["metadata"]["restricciones"],
            "supuestos": opt["metadata"]["supuestos"] + [
                {"nombre": "escenario_actual", "valor": actual["origen"],
                 "origen": "definicion del escenario de referencia", "fecha": FECHA_SUPUESTOS}],
            "supuestos_declarados": True,
            "limites": LIMITES_COMUNES + [
                "Las mecanicas no incluyen el coste del espacio de folleto o display: solo "
                "cambian el aumento de ventas.",
                "El descuento es fijo en todos los escenarios: no se mide la respuesta de la "
                "demanda a su profundidad.",
                "Mejora simulada con el modelo, no un efecto causal demostrado.",
                "Beneficio y ROI dependen de margenes supuestos: se muestran como escenarios "
                "ilustrativos (-5 pp, base, +5 pp), nunca como criterio de optimizacion."],
            "mecanicas": MECANICAS,
        },
    }
