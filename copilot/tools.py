"""Capa analitica reutilizable del copiloto.

Cada tool devuelve un resultado estructurado con metadatos verificables. El LLM
nunca calcula: redacta a partir de lo que devuelven estas funciones.
"""
import os
import uuid
from datetime import datetime

import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")
_store = None

# Version de los datos de respaldo (de donde salen los parametros del modelo).
DATA_VERSION = "dunnhumby_complete_journey_v1"

# Regla documentada de fiabilidad a partir de metricas medidas en validacion:
#   - cobertura del intervalo de prediccion (objetivo 80 %)
#   - sesgo porcentual del modelo
REGLA_FIABILIDAD = ("baja si cobertura < 0.60 o |sesgo| > 5 %; "
                    "alta si cobertura >= 0.85 y |sesgo| <= 2 %; media en el resto")


# El estudio de forecasting valido previsiones a 1 semana (rolling-origin, 3 ventanas).
HORIZONTE_VALIDADO = 1
BACKTESTING = "rolling-origin, 3 ventanas de 12 semanas, horizonte 1 semana"
FECHA_SUPUESTOS = "2026-10-09"


# Formato comun de resultados (paso 1 del sistema de decision): toda tool devuelve
# las mismas metricas, con None y un motivo cuando una metrica no aplica.
METRICAS = {
    "unidades_previstas": "unidades",
    "unidades_incrementales": "unidades",
    "ventas_incrementales_eur": "EUR",
    "coste_eur": "EUR",
    "beneficio_eur": "EUR",
    "roi": "",
    "descuento_total_eur": "EUR",
}

DEFINICIONES = {
    "unidades_previstas": "unidades esperadas en el escenario",
    "unidades_incrementales": "unidades del escenario menos unidades con actividad media",
    "ventas_incrementales_eur": "ventas a precio de cliente del escenario menos las de base",
    "coste_eur": "parte del descuento promocional que paga el distribuidor",
    "beneficio_eur": "margen incremental del distribuidor, neto del coste (margen supuesto)",
    "roi": "beneficio / coste",
    "descuento_total_eur": "descuento promocional total concedido, lo pague quien lo pague",
}

# Tres niveles de evidencia: lo medido en los datos, lo estimado por el modelo y
# lo que requiere supuestos economicos que el dataset no incluye (margenes,
# costes promocionales). Ninguna cifra del tercer nivel se presenta como optima.
NIVELES_EVIDENCIA = {
    "medido": "observado en los datos historicos",
    "estimado": "estimado por el modelo; depende de su validez",
    "supuesto": "requiere supuestos economicos que el dataset no incluye",
}
EVIDENCIA = {
    "unidades_previstas": ("estimado", "modelo de volumen"),
    "unidades_incrementales": ("estimado", "modelo de volumen (efecto de folleto y display)"),
    "ventas_incrementales_eur": ("estimado", "unidades estimadas x precio y descuento medidos"),
    "descuento_total_eur": ("estimado", "unidades estimadas x descuento del escenario"),
    "coste_eur": ("estimado", "unidades estimadas x descuento del escenario (el distribuidor asume todo el descuento)"),
    "beneficio_eur": ("supuesto", "margen del distribuidor (no esta en los datos)"),
    "roi": ("supuesto", "margen del distribuidor (no esta en los datos)"),
}
DATOS_MEDIDOS = ["precio de lista por categoria", "descuento estructural habitual",
                 "actividad de folleto y display", "ventas historicas por semana",
                 "error de prevision en backtesting (WAPE, cobertura, sesgo)"]


def evidencia(metricas: dict):
    """Nivel de evidencia de cada metrica presente."""
    return {k: {"nivel": EVIDENCIA[k][0], "depende_de": EVIDENCIA[k][1]}
            for k, v in metricas.items() if v is not None and k in EVIDENCIA}


# Escenarios ilustrativos de margen: el beneficio no se optimiza, se ilustra.
ESCENARIOS_MARGEN = {"bajo": -0.05, "base": 0.0, "alto": 0.05}


def beneficio_por_margen(par, n_mailer, n_display, pct, roi_logic):
    """Beneficio y ROI de una promocion con el margen supuesto -5 pp, base y +5 pp."""
    out = {}
    for esc, delta in ESCENARIOS_MARGEN.items():
        mg = max(float(par["margen_defecto"]) + delta, 0.01)
        e = roi_logic.evaluar(par, n_mailer, n_display, pct, mg)
        roi = e["roi"]
        out[esc] = {"margen": round(mg, 2), "beneficio": round(e["beneficio_incremental_eur"]),
                    "roi": None if roi is None or roi != roi else round(roi, 2)}
    return out


LIMITES_COMUNES = [
    "Asociacion estadistica entre actividad promocional y ventas, no efecto causal.",
    "Muestra de 2.500 hogares y 8 categorias (Dunnhumby Complete Journey).",
]


def _metricas(valores: dict, no_aplica: dict):
    """Bloque estandar de metricas y motivos de las que no aplican."""
    m = {k: valores.get(k) for k in METRICAS}
    motivos = {k: no_aplica.get(k, "no calculada por esta herramienta")
               for k, v in m.items() if v is None}
    return m, motivos


# Mecanicas promocionales que el modelo de volumen respalda: el aumento de ventas
# depende de la actividad de folleto (mailer) y de display, medidas por separado.
# La palanca activa se lleva al percentil 90 observado; la otra queda en su media.
MECANICAS = {
    "folleto_y_display": "folleto y display en el percentil 90 observado",
    "folleto": "folleto en el percentil 90; display en su nivel medio",
    "display": "display en el percentil 90; folleto en su nivel medio",
}


def actividad(par, mecanica="folleto_y_display"):
    """Niveles (folleto, display) de la mecanica pedida."""
    m = float(par["mailer_p90"]) if mecanica in ("folleto_y_display", "folleto") \
        else float(par["mailer_medio"])
    d = float(par["display_p90"]) if mecanica in ("folleto_y_display", "display") \
        else float(par["display_medio"])
    return m, d


def evaluar_promocion(categoria, puntos_descuento_extra=15,
                      mecanica="folleto_y_display"):
    """Metricas (redondeadas) de una semana de promocion de una categoria."""
    import roi_logic
    par = _load_roi().loc[categoria].to_dict()
    pct = float(par["pct_base"]) + puntos_descuento_extra / 100
    e = roi_logic.evaluar(par, *actividad(par, mecanica), pct, float(par["margen_defecto"]))
    roi = e["roi"]
    return {"categoria": categoria, "coste": round(e["coste_eur"]),
            "beneficio_por_margen": beneficio_por_margen(par, *actividad(par, mecanica), pct,
                                                         roi_logic),
            "beneficio": round(e["beneficio_incremental_eur"]),
            "roi": None if roi is None or roi != roi else round(roi, 2),
            "unidades_inc": round(e["unidades_promo"] - e["unidades_base"]),
            "ventas_inc": round(e["ventas_incrementales_eur"]),
            "descuento": round(e["descuento_total_eur"])}


def _sensibilidad(par, pct_desc, margen, roi_logic, mecanica="folleto_y_display"):
    """ROI ante cambios en el margen supuesto (sin tocar el resto)."""
    def roi(mg):
        r = roi_logic.evaluar(par, *actividad(par, mecanica), pct_desc, mg)
        v = r["roi"]
        return None if v is None or v != v else round(v, 2)
    return {"roi_por_margen": {"-5pp": roi(max(margen - 0.05, 0.01)),
                               "base": roi(margen), "+5pp": roi(margen + 0.05)}}


def fiabilidad(cobertura: float, sesgo_pct: float) -> str:
    if cobertura < 0.60 or abs(sesgo_pct) > 5:
        return "baja"
    if cobertura >= 0.85 and abs(sesgo_pct) <= 2:
        return "alta"
    return "media"


def _load():
    global _store
    if _store is None:
        _store = pd.read_csv(os.path.join(DATA, "forecast_store.csv")).set_index("categoria")
    return _store


def categorias_disponibles():
    return list(_load().index)


def get_category_forecast(categoria: str, horizonte: int = 4) -> dict:
    """Prevision de unidades por categoria para las proximas `horizonte` semanas.

    Devuelve un dict con el resultado y los metadatos que el motor de politicas
    necesita para verificar la respuesta. Si la categoria no existe en los datos,
    lo indica explicitamente en vez de inventar una cifra.
    """
    store = _load()
    run_id = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    base = {
        "run_id": run_id,
        "tool": "get_category_forecast",
        "parametros": {"categoria": categoria, "horizonte": horizonte},
        "version_datos": DATA_VERSION,
        "generado": datetime.now().isoformat(timespec="seconds"),
    }

    if not isinstance(horizonte, int) or not 1 <= horizonte <= 52:
        return {**base, "ok": False,
                "tipo_error": "argumento",
                "motivo": f"Horizonte invalido ({horizonte}): debe estar entre 1 y 52 semanas."}
    if categoria not in store.index:
        return {**base, "ok": False, "tipo_error": "datos",
                "motivo": f"La categoria '{categoria}' no esta en los datos disponibles.",
                "categorias_validas": list(store.index)}

    f = store.loc[categoria]
    nivel = float(f["nivel_semanal"])
    wape = float(f["wape_referencia"])
    semanas = [round(nivel) for _ in range(horizonte)]
    total = round(nivel * horizonte)
    banda = {"baja": round(total * (1 - wape)), "alta": round(total * (1 + wape))}

    metricas, no_disp = _metricas(
        {"unidades_previstas": total},
        {k: "prevision de volumen sin escenario promocional" for k in METRICAS})
    return {
        **base,
        "ok": True,
        "resultado": {
            "metricas": metricas,
            "prediccion_semanal": semanas,
            "prediccion_total": total,
            "intervalo_total": banda,
        },
        "metadata": {
            "modelo": f["modelo"],
            "wape_referencia": wape,
            "cobertura_intervalo": float(f["cobertura_intervalo"]),
            "sesgo_pct": float(f["sesgo_pct"]),
            "fiabilidad_categoria": fiabilidad(float(f["cobertura_intervalo"]),
                                               float(f["sesgo_pct"])),
            "regla_fiabilidad": REGLA_FIABILIDAD,
            "horizonte_validado": HORIZONTE_VALIDADO,
            "backtesting": BACKTESTING,
            "semanas_entrenamiento": int(f["semanas_entrenamiento"]),
            "ramp_up": bool(f["ramp_up"]),
            "actividad_observada": [float(f["actividad_min"]), float(f["actividad_max"])],
            "metricas_no_disponibles": no_disp,
            "evidencia": evidencia(metricas),
            "datos_medidos": DATOS_MEDIDOS,
            "limites": LIMITES_COMUNES + [
                f"Error medido solo a {HORIZONTE_VALIDADO} semana vista."],
        },
    }


_roi_par = None


def _load_roi():
    global _roi_par
    if _roi_par is None:
        _roi_par = pd.read_csv(os.path.join(DATA, "parametros_validador.csv")).set_index("categoria")
    return _roi_par


def evaluate_promo_roi(categoria: str, puntos_descuento_extra: float = 15,
                       mecanica: str = "folleto_y_display") -> dict:
    """ROI de una promoción típica para una categoría.

    Escenario: actividad de folleto/display en el percentil 90 observado y un
    descuento de `puntos_descuento_extra` puntos por encima del nivel estructural.
    El distribuidor asume todo el descuento. Declara sus supuestos (margen) en los metadatos.
    """
    import roi_logic
    par_df = _load_roi()
    run_id = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    base = {
        "run_id": run_id, "tool": "evaluate_promo_roi",
        "parametros": {"categoria": categoria,
                       "puntos_descuento_extra": puntos_descuento_extra,
                       "mecanica": mecanica},
        "version_datos": DATA_VERSION,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "economico": True,
    }
    if mecanica not in MECANICAS:
        return {**base, "ok": False, "tipo_error": "argumento",
                "motivo": f"Mecanica '{mecanica}' desconocida ({', '.join(MECANICAS)})."}
    if not 0 <= puntos_descuento_extra <= 60:
        return {**base, "ok": False,
                "tipo_error": "argumento",
                "motivo": f"Descuento invalido ({puntos_descuento_extra}): 0 a 60 puntos."}
    if categoria not in par_df.index:
        return {**base, "ok": False, "tipo_error": "datos",
                "motivo": f"La categoria '{categoria}' no esta en los datos disponibles.",
                "categorias_validas": list(par_df.index)}

    par = par_df.loc[categoria].to_dict()
    margen = float(par["margen_defecto"])
    pct_desc = float(par["pct_base"]) + puntos_descuento_extra / 100
    r = roi_logic.evaluar(par, *actividad(par, mecanica), pct_desc, margen)
    roi_v = None if r["roi"] is None or r["roi"] != r["roi"] else round(r["roi"], 2)
    metricas, no_disp = _metricas({
        "unidades_previstas": round(r["unidades_promo"]),
        "unidades_incrementales": round(r["unidades_promo"] - r["unidades_base"]),
        "ventas_incrementales_eur": round(r["ventas_incrementales_eur"]),
        "coste_eur": round(r["coste_eur"]),
        "beneficio_eur": round(r["beneficio_incremental_eur"]),
        "roi": roi_v,
        "descuento_total_eur": round(r["descuento_total_eur"]),
    }, {"roi": "sin coste para el distribuidor (descuento nulo)"})
    return {
        **base, "ok": True,
        "resultado": {
            "metricas": metricas,
            "roi": None if r["roi"] is None or r["roi"] != r["roi"] else round(r["roi"], 2),
            "semaforo": r["semaforo"],
            "uplift_pct": round(r["uplift"] * 100, 1),
            "coste_eur": round(r["coste_eur"]),
            "beneficio_incremental_eur": round(r["beneficio_incremental_eur"]),
        },
        "metadata": {
            "modelo": "Ridge + calendario (uplift) sobre escenario P90 de la mecanica",
            "fiabilidad_categoria": _fiab_roi(categoria),
            "supuestos": [
                {"nombre": "margen", "valor": margen,
                 "origen": "supuesto de trabajo por categoria (el dataset no incluye costes)",
                 "fecha": FECHA_SUPUESTOS},
                {"nombre": "halo_valor_cesta", "valor": 0.0,
                 "origen": "supuesto conservador: no se valora el trafico inducido",
                 "fecha": FECHA_SUPUESTOS},
            ],
            "sensibilidad": _sensibilidad(par, pct_desc, margen, roi_logic, mecanica),
            "mecanica": MECANICAS[mecanica],
            "supuestos_declarados": True,
            "definiciones": DEFINICIONES,
            "metricas_no_disponibles": no_disp,
            "evidencia": evidencia(metricas),
            "datos_medidos": DATOS_MEDIDOS,
            "limites": LIMITES_COMUNES + [
                "El aumento de ventas depende del folleto y el display; la profundidad del "
                "descuento solo cambia el coste (no se mide la respuesta de la demanda).",
                "Beneficio calculado con un margen supuesto: el dataset no incluye costes."],
        },
    }


# Objetivos que el optimizador sabe maximizar (paso 2). Cada uno apunta a la
# metrica estandar que maximiza y a la columna del candidato.
OBJETIVOS = {
    "ventas": {"metrica": "ventas_incrementales_eur", "campo": "ventas_inc",
               "texto": "ventas incrementales a precio de cliente"},
    "volumen": {"metrica": "unidades_incrementales", "campo": "unidades_inc",
                "texto": "unidades incrementales"},
}
# El beneficio no es un objetivo de optimizacion: exige margenes y costes
# promocionales que el dataset no tiene. Se muestra en escenarios ilustrativos.
NO_OPTIMIZABLE = {
    "beneficio": ("El beneficio no se optimiza: requiere margenes y costes promocionales "
                  "que el dataset no incluye. Optimiza ventas o volumen; el beneficio se "
                  "muestra en escenarios ilustrativos de margen."),
}


def comprobar_restricciones(salida: dict):
    """Recalcula el uso de cada restriccion a partir del calendario devuelto.

    No se fia de lo que dijo el solver: vuelve a sumar. Devuelve la lista de
    restricciones con limite, uso, holgura y si es activa (limita la solucion).
    """
    p = salida["parametros"]
    cal = salida["resultado"]["calendario"]
    cand = salida["resultado"].get("candidatas", [])
    usadas = {}
    for r in cal:
        usadas[r["categoria"]] = usadas.get(r["categoria"], 0) + 1
    coste = sum(r["coste_eur"] for r in cal)
    desc = sum(r["descuento_total_eur"] for r in cal)
    por_semana = [sum(1 for r in cal if r["semana"] == w) for w in range(1, p["horizonte"] + 1)]
    # Una restriccion es activa si queda alguna candidata que mejoraria el
    # objetivo y no cabe por esa restriccion.
    libres = [c for c in cand if usadas.get(c["categoria"], 0) < p["max_promos_categoria"]
              and c["valor_objetivo"] > 0]
    coste_min = min((c["coste"] for c in libres), default=None)
    desc_min = min((c["descuento"] for c in libres), default=None)
    out = [
        {"nombre": "presupuesto", "limite": p["presupuesto_eur"], "uso": coste,
         "cumple": coste <= p["presupuesto_eur"] + 1e-6,
         "activa": coste_min is not None and p["presupuesto_eur"] - coste < coste_min},
        {"nombre": "huecos_por_semana", "limite": p["max_promos_semana"],
         "uso": max(por_semana, default=0),
         "cumple": all(n <= p["max_promos_semana"] for n in por_semana),
         "activa": bool(libres) and any(n == p["max_promos_semana"] for n in por_semana)},
        {"nombre": "promociones_por_categoria", "limite": p["max_promos_categoria"],
         "uso": max(usadas.values(), default=0),
         "cumple": all(n <= p["max_promos_categoria"] for n in usadas.values()),
         "activa": any(n == p["max_promos_categoria"] and
                       any(c["categoria"] == k and c["valor_objetivo"] > 0 for c in cand)
                       for k, n in usadas.items())},
    ]
    if p.get("max_descuento_total_eur") is not None:
        out.append({"nombre": "descuento_total_maximo", "limite": p["max_descuento_total_eur"],
                    "uso": desc, "cumple": desc <= p["max_descuento_total_eur"] + 1e-6,
                    "activa": desc_min is not None
                              and p["max_descuento_total_eur"] - desc < desc_min})
    out.append({"nombre": "roi_minimo", "limite": p["roi_minimo"],
                "uso": min((r["roi"] for r in cal), default=None),
                "cumple": p["roi_minimo"] is None or all(r["roi"] >= p["roi_minimo"] - 1e-9
                                                         for r in cal),
                "activa": any(e.get("valor_objetivo", 0) > 0
                              for e in salida["resultado"]["excluidas"])})
    return out


def optimize_promo_program(presupuesto_eur: float = 1000, semanas: int = 4,
                           puntos_descuento_extra: float = 15,
                           max_promos_semana: int = 3, max_promos_categoria: int = 2,
                           objetivo: str = "ventas", roi_minimo: float | None = None,
                           max_descuento_total_eur: float | None = None,
                           mecanica: str = "folleto_y_display") -> dict:
    """Programa promocional optimo: que categoria promocionar cada semana.

    Programa lineal entero (PuLP + CBC):
      variables      x[c, w] = 1 si la categoria c se promociona la semana w
      objetivo       maximizar ventas o volumen incremental (`objetivo`); el beneficio
                     no se optimiza: se ilustra con escenarios de margen
      restricciones  coste total <= presupuesto
                     promociones por semana <= huecos de folleto
                     promociones por categoria <= limite (fatiga promocional)
                     descuento total <= maximo (opcional)
    `roi_minimo` es opcional: filtra con un margen supuesto, y la respuesta lo avisa.
    """
    import pulp
    import roi_logic

    if isinstance(semanas, int) and semanas >= 1:
        max_promos_categoria = min(max_promos_categoria, semanas)   # no puede superar el horizonte
    run_id = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    params = {"categoria": "PROGRAMA", "horizonte": semanas,
              "presupuesto_eur": presupuesto_eur,
              "puntos_descuento_extra": puntos_descuento_extra,
              "max_promos_semana": max_promos_semana,
              "max_promos_categoria": max_promos_categoria,
              "objetivo": objetivo, "roi_minimo": roi_minimo,
              "max_descuento_total_eur": max_descuento_total_eur, "mecanica": mecanica}
    base = {"run_id": run_id, "tool": "optimize_promo_program", "parametros": params,
            "version_datos": DATA_VERSION,
            "generado": datetime.now().isoformat(timespec="seconds"), "economico": True}

    errores = []
    if not 0 < presupuesto_eur <= 1_000_000:
        errores.append(f"presupuesto {presupuesto_eur} € fuera de rango (0 a 1.000.000)")
    if not isinstance(semanas, int) or not 1 <= semanas <= 12:
        errores.append(f"horizonte {semanas} semanas fuera de rango (1 a 12)")
    if not 0 <= puntos_descuento_extra <= 60:
        errores.append(f"descuento {puntos_descuento_extra} puntos fuera de rango (0 a 60)")
    if not 1 <= max_promos_semana <= 8:
        errores.append("huecos por semana fuera de rango (1 a 8)")
    if not 1 <= max_promos_categoria:
        errores.append("promociones por categoria fuera de rango (minimo 1)")
    if mecanica not in MECANICAS:
        errores.append(f"mecanica '{mecanica}' desconocida ({', '.join(MECANICAS)})")
    if objetivo in NO_OPTIMIZABLE:
        return {**base, "ok": False, "tipo_error": "argumento",
                "motivo": NO_OPTIMIZABLE[objetivo]}
    if objetivo not in OBJETIVOS:
        errores.append(f"objetivo '{objetivo}' desconocido (ventas o volumen)")
    if roi_minimo is not None and not -1 <= roi_minimo <= 5:
        errores.append(f"ROI minimo {roi_minimo} fuera de rango (-1 a 5)")
    if max_descuento_total_eur is not None and not 0 < max_descuento_total_eur <= 1_000_000:
        errores.append(f"descuento maximo {max_descuento_total_eur} € fuera de rango")
    if errores:
        return {**base, "ok": False, "tipo_error": "argumento",
                "motivo": "Argumentos invalidos: " + "; ".join(errores) + "."}

    par_df = _load_roi()
    store = _load()
    candidatos, excluidas = [], []
    for cat, fila in par_df.iterrows():
        par = fila.to_dict()
        pct = float(par["pct_base"]) + puntos_descuento_extra / 100
        margen = float(par["margen_defecto"])
        e = roi_logic.evaluar(par, *actividad(par, mecanica), pct, margen)
        roi = e["roi"]
        hay_coste = roi == roi and roi is not None
        if hay_coste and (roi_minimo is None or roi >= roi_minimo):
            candidatos.append({"categoria": cat, "coste": round(e["coste_eur"]),
                               "beneficio": round(e["beneficio_incremental_eur"]),
                               "roi": round(roi, 2),
                               "unidades_inc": round(e["unidades_promo"] - e["unidades_base"]),
                               "ventas_inc": round(e["ventas_incrementales_eur"]),
                               "descuento": round(e["descuento_total_eur"]),
                               "margenes": beneficio_por_margen(
                                   par, *actividad(par, mecanica), pct, roi_logic)})
        else:
            valores_obj = {"ventas": e["ventas_incrementales_eur"],
                           "volumen": e["unidades_promo"] - e["unidades_base"]}
            excluidas.append({"categoria": cat, "motivo": "ROI por debajo del minimo"
                              if hay_coste else "sin coste para el distribuidor",
                              "valor_objetivo": round(valores_obj.get(objetivo, 0)),
                              "roi": None if roi != roi else round(roi, 2)})

    calendario, estado = [], "sin candidatas"
    if candidatos:
        prob = pulp.LpProblem("programa_promocional", pulp.LpMaximize)
        x = {(c["categoria"], w): pulp.LpVariable(f"x_{i}_{w}", cat="Binary")
             for i, c in enumerate(candidatos) for w in range(1, semanas + 1)}
        campo = OBJETIVOS[objetivo]["campo"]
        prob += pulp.lpSum(c[campo] * x[(c["categoria"], w)]
                           for c in candidatos for w in range(1, semanas + 1))
        prob += pulp.lpSum(c["coste"] * x[(c["categoria"], w)]
                           for c in candidatos for w in range(1, semanas + 1)) <= presupuesto_eur
        if max_descuento_total_eur is not None:
            prob += pulp.lpSum(c["descuento"] * x[(c["categoria"], w)]
                               for c in candidatos
                               for w in range(1, semanas + 1)) <= max_descuento_total_eur
        for w in range(1, semanas + 1):
            prob += pulp.lpSum(x[(c["categoria"], w)] for c in candidatos) <= max_promos_semana
        for c in candidatos:
            prob += pulp.lpSum(x[(c["categoria"], w)]
                               for w in range(1, semanas + 1)) <= max_promos_categoria
        prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=20))
        estado = pulp.LpStatus[prob.status]
        if estado != "Optimal":
            return {**base, "ok": False, "tipo_error": "tecnico",
                    "motivo": f"El optimizador no encontro solucion optima ({estado})."}
        for c in candidatos:
            for w in range(1, semanas + 1):
                if x[(c["categoria"], w)].value() > 0.5:
                    calendario.append({"semana": w, "categoria": c["categoria"],
                                       "coste_eur": c["coste"], "beneficio_eur": c["beneficio"],
                                       "roi": c["roi"], "unidades_inc": c["unidades_inc"],
                                       "ventas_inc_eur": c["ventas_inc"],
                                       "descuento_total_eur": c["descuento"],
                                       "beneficio_por_margen": c["margenes"]})
        campo_obj = {"ventas": "ventas_inc_eur", "volumen": "unidades_inc"}[objetivo]
        calendario.sort(key=lambda r: (r["semana"], -r[campo_obj]))

    coste_total = sum(r["coste_eur"] for r in calendario)
    beneficio_total = sum(r["beneficio_eur"] for r in calendario)
    seleccionadas = sorted({r["categoria"] for r in calendario})
    roi_prog = round(beneficio_total / coste_total, 2) if coste_total else None
    metricas, no_disp = _metricas({
        "unidades_incrementales": sum(r["unidades_inc"] for r in calendario),
        "ventas_incrementales_eur": sum(r["ventas_inc_eur"] for r in calendario),
        "coste_eur": coste_total,
        "beneficio_eur": beneficio_total,
        "roi": roi_prog,
        "descuento_total_eur": sum(r["descuento_total_eur"] for r in calendario),
    }, {"unidades_previstas": "el programa mide el efecto incremental; el volumen total "
                              "por categoria lo da la prevision",
        "roi": "programa vacio: sin coste"})
    ilustrativo = {}
    for esc in ESCENARIOS_MARGEN:
        ben = sum(r["beneficio_por_margen"][esc]["beneficio"] for r in calendario)
        ilustrativo[esc] = {
            "delta_margen_pp": round(ESCENARIOS_MARGEN[esc] * 100),
            "beneficio_eur": ben,
            "roi": round(ben / coste_total, 2) if coste_total else None,
            "promociones_no_rentables": sum(
                1 for r in calendario
                if (r["beneficio_por_margen"][esc]["roi"] or 0) < roi_logic.UMBRAL_VERDE)}
    baja = [c for c in seleccionadas
            if c in store.index and fiabilidad(float(store.loc[c, "cobertura_intervalo"]),
                                               float(store.loc[c, "sesgo_pct"])) == "baja"]
    salida = {
        **base, "ok": True,
        "resultado": {
            "metricas": metricas,
            "calendario": calendario,
            "totales": {
                "n_promociones": len(calendario),
                "coste_eur": coste_total,
                "beneficio_eur": beneficio_total,
                "roi": roi_prog,
                "unidades_incrementales": sum(r["unidades_inc"] for r in calendario),
                "presupuesto_usado_pct": round(coste_total / presupuesto_eur * 100),
            },
            "beneficio_ilustrativo": ilustrativo,
            "candidatas": [{"categoria": c["categoria"], "coste": c["coste"],
                            "descuento": c["descuento"], "roi": c["roi"],
                            "valor_objetivo": c[OBJETIVOS[objetivo]["campo"]]}
                           for c in candidatos],
            "excluidas": sorted(excluidas, key=lambda r: -r["valor_objetivo"]),
        },
        "metadata": {
            "modelo": "Programa lineal entero (PuLP + CBC) sobre ROI por categoria",
            "objetivo": objetivo,
            "objetivo_descripcion": OBJETIVOS[objetivo]["texto"],
            "valor_objetivo": metricas[OBJETIVOS[objetivo]["metrica"]],
            "roi_minimo": roi_minimo,
            "estado_solver": estado,
            "umbral_rentabilidad_roi": roi_logic.UMBRAL_VERDE,
            "horizonte_validado": HORIZONTE_VALIDADO,
            "backtesting": BACKTESTING,
            "categorias_baja_fiabilidad": baja,
            "supuestos": [
                {"nombre": "margen", "valor": "por categoria (20 % a 35 %)",
                 "origen": "supuesto de trabajo por categoria (el dataset no incluye costes)",
                 "fecha": FECHA_SUPUESTOS},
                {"nombre": "mecanica", "valor": mecanica,
                 "origen": MECANICAS[mecanica], "fecha": FECHA_SUPUESTOS},
                {"nombre": "profundidad_descuento", "valor": puntos_descuento_extra,
                 "origen": "fija: el modelo no mide la respuesta de la demanda a la profundidad",
                 "fecha": FECHA_SUPUESTOS},
                {"nombre": "beneficio_semanal", "valor": "constante en el horizonte",
                 "origen": "el modelo no tiene estacionalidad semanal validada",
                 "fecha": FECHA_SUPUESTOS},
            ],
            "supuestos_declarados": True,
            "definiciones": DEFINICIONES,
            "metricas_no_disponibles": no_disp,
            "evidencia": evidencia(metricas),
            "datos_medidos": DATOS_MEDIDOS,
            "limites": LIMITES_COMUNES + [
                "El beneficio no se optimiza: se ilustra con margenes supuestos (-5 pp, base, "
                "+5 pp). No es un programa optimo en beneficio.",
                "La profundidad del descuento es fija.",
                "Mismo beneficio cada semana: no hay estacionalidad semanal validada."],
        },
    }
    salida["metadata"]["restricciones"] = comprobar_restricciones(salida)
    if calendario and ilustrativo["base"]["beneficio_eur"] < 0:
        salida["metadata"]["conflicto_objetivo"] = (
            f"El programa maximiza {OBJETIVOS[objetivo]['texto']} pero, con el margen supuesto "
            f"base, pierde {-ilustrativo['base']['beneficio_eur']} € "
            f"(margen alto: {ilustrativo['alto']['beneficio_eur']} €).")
    return salida


def _fiab_roi(categoria):
    store = _load()
    if categoria not in store.index:
        return "media"
    f = store.loc[categoria]
    return fiabilidad(float(f["cobertura_intervalo"]), float(f["sesgo_pct"]))


def valores_respaldados(salida: dict):
    """Conjunto de numeros que una ejecucion respalda (para verificar grounding).

    Cualquier cifra del texto del agente que no este aqui se considera inventada.
    """
    vals = set()
    if not salida.get("ok"):
        return vals
    res = salida["resultado"]
    vals.update(v for v in res.get("metricas", {}).values() if v is not None)
    if salida["tool"] == "get_category_forecast":
        meta = salida["metadata"]
        vals.update(res["prediccion_semanal"])
        vals.add(res["prediccion_total"])
        vals.add(res["intervalo_total"]["baja"])
        vals.add(res["intervalo_total"]["alta"])
        vals.add(salida["parametros"]["horizonte"])
        vals.add(round(meta["wape_referencia"] * 100))     # "11%"
        vals.add(meta["wape_referencia"])
        vals.add(meta["semanas_entrenamiento"])
    elif salida["tool"] == "evaluate_promo_roi":
        for k in ("roi", "uplift_pct", "coste_eur", "beneficio_incremental_eur"):
            if res.get(k) is not None:
                vals.add(res[k])
        for x in salida["metadata"]["supuestos"]:
            vals.add(x["valor"] * 100)                              # "20%"
        vals.add(salida["parametros"]["puntos_descuento_extra"])
    elif salida["tool"] == "optimize_promo_program":
        p = salida["parametros"]
        vals.update(range(1, p["horizonte"] + 1))                   # "semana 1"
        vals.update([p["horizonte"], p["presupuesto_eur"],
                     p["puntos_descuento_extra"], p["max_promos_semana"],
                     p["max_promos_categoria"]])
        vals.add(salida["metadata"]["umbral_rentabilidad_roi"])
        for k in ("roi_minimo", "max_descuento_total_eur"):
            if p.get(k) is not None:
                vals.add(p[k])
        for r in salida["metadata"].get("restricciones", []):
            vals.update(v for v in (r["limite"], r["uso"]) if isinstance(v, (int, float)))
        for esc in res.get("beneficio_ilustrativo", {}).values():
            vals.update(v for v in (esc["beneficio_eur"], esc["roi"], esc["delta_margen_pp"],
                                    -esc["beneficio_eur"], esc["promociones_no_rentables"])
                        if v is not None)
        for v in res["totales"].values():
            if v is not None:
                vals.add(v)
        for r in res["calendario"]:
            vals.update([r["coste_eur"], r["beneficio_eur"], r["roi"], r["unidades_inc"]])
        for r in res["excluidas"]:
            vals.update(v for v in (r["roi"], r["valor_objetivo"]) if v is not None)
    if salida["tool"] in ("recommend_promo_decision", "optimize_assortment"):
        _numeros_anidados(res, vals)
        _numeros_anidados(salida["parametros"], vals)
    if salida["tool"] == "optimize_assortment":
        import re
        # cifras que forman parte del nombre de la subcategoria ("lata 12/18", "2 l")
        vals.update(float(n) for n in re.findall(r"\d+", res.get("subcategoria_nombre", "")))
    return {float(v) for v in vals}


def _numeros_anidados(nodo, vals):
    """Todas las cifras de una estructura anidada, con su valor absoluto y, si son
    fracciones, su porcentaje (para respaldar "90 %" a partir de 0.9)."""
    if isinstance(nodo, bool) or nodo is None:
        return
    if isinstance(nodo, (int, float)):
        vals.update({nodo, abs(nodo)})
        if 0 < abs(nodo) <= 1:
            vals.add(round(abs(nodo) * 100, 2))
    elif isinstance(nodo, dict):
        for v in nodo.values():
            _numeros_anidados(v, vals)
    elif isinstance(nodo, (list, tuple)):
        for v in nodo:
            _numeros_anidados(v, vals)


# Registro de tools que el agente puede invocar.
TOOLS = {
    "get_category_forecast": {
        "fn": get_category_forecast,
        "descripcion": "Prevision de unidades por categoria para las proximas semanas.",
        "devuelve": "unidades (volumen). No devuelve euros, ROI ni margen.",
    },
    "optimize_promo_program": {
        "fn": optimize_promo_program,
        "descripcion": "Programa promocional optimo: que categoria promocionar cada semana "
                       "con un presupuesto, maximizando ventas o volumen; beneficio ilustrativo.",
        "devuelve": "calendario, coste, beneficio, ROI del programa y categorias que no entran.",
    },
    "evaluate_promo_roi": {
        "fn": evaluate_promo_roi,
        "descripcion": "ROI de una promocion tipica para una categoria, con supuestos declarados.",
        "devuelve": "ROI, semaforo, coste y beneficio en euros.",
    },
}
