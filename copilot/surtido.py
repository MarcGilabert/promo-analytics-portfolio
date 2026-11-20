"""Optimizador de surtido: que fabricantes mantener en una subcategoria.

Unidad de decision: fabricante dentro de subcategoria (la subcategoria ya fija el
formato). Datos: data/surtido_grupos.csv (preparar_surtido.py).

Modelo (programa lineal entero, PuLP + CBC)
  variables      x[g] = 1 si el grupo g se mantiene
  objetivo       maximizar ventas conservadas =
                   sum_g x[g] * ventas[g] + (1 - x[g]) * f * transf[g] * ventas[g]
                 (lo que se pierde al retirar un grupo es la parte de sus ventas que
                 no se transfiere a los que se quedan)
  restricciones  numero de grupos mantenidos <= max_grupos
                 al menos un grupo de marca propia, si existe
                 grupos obligatorios (opcional)
  f              factor sobre la transferencia estimada (sensibilidad 0 / 0,5 / 0,75 / 1)

La transferencia estimada es una COTA SUPERIOR: mide que el hogar ya compra otro
fabricante, no que aceptaria cambiar. Con f = 0 se obtiene la cota inferior (se
pierde todo lo retirado). La cifra defendible es el rango entre ambas.

Equivale a ordenar por "ventas no transferibles" = ventas * (1 - f * transf): un
grupo grande pero muy sustituible puede salir antes que uno pequeno y fiel. La
referencia sencilla es quedarse con los que mas venden.

Validacion: se decide con el ano 1 (semanas 20-60) y se evalua con las ventas del
ano 2 (61-101), comparando con la mejor decision posible en el ano 2 (arrepentimiento).

Niveles de evidencia: ventas medidas; transferencia estimada (que un hogar tenga
alternativa en su repertorio no prueba que cambiaria); el resultado es simulado.
"""
import os
import uuid
from datetime import datetime

import pandas as pd

from tools import DATA_VERSION, FECHA_SUPUESTOS

DATA = os.path.join(os.path.dirname(__file__), "data")
GRUPOS = os.path.join(DATA, "surtido_grupos.csv")
MIN_HOGARES = 30
FACTORES_SENSIBILIDAD = (0.0, 0.5, 0.75, 1.0)
NOMBRE_SUB = {
    "SOFT DRINKS 12/18&15PK CAN CAR": "Refrescos en lata 12/18",
    "SFT DRNK 2 LITER BTL CARB INCL": "Refrescos en botella de 2 l",
    "SFT DRNK MLT-PK BTL CARB (EXCP": "Refrescos multipack en botella",
    "SOFT DRINKS 20PK&24PK CAN CARB": "Refrescos en lata 20/24",
    "SOFT DRINKS 6PK/4PK CAN CARB (": "Refrescos en lata 6/4",
    "SFT DRNK SNGL SRV BTL CARB (EX": "Refrescos en botella individual",
    "SOFT DRINKS CAN NON-CARB (EXCE": "Bebidas sin gas en lata",
    "PRETZELS": "Pretzels",
}


def _grupos():
    return pd.read_csv(GRUPOS)


def subcategorias():
    return list(NOMBRE_SUB)


def grupos(subcategoria):
    g = _grupos()
    g = g[(g["subcategoria"] == subcategoria) & (g["ventas_a1"] > 0)].copy()
    return g.sort_values("ventas_a1", ascending=False).reset_index(drop=True)


def _resolver(g, max_grupos, f, col_ventas, obligatorios=(), min_privada=1):
    """Programa lineal entero. Devuelve el conjunto de fabricantes mantenidos."""
    import pulp
    prob = pulp.LpProblem("surtido", pulp.LpMaximize)
    x = {r.fabricante: pulp.LpVariable(f"x_{r.fabricante}", cat="Binary") for r in g.itertuples()}
    perdida = {r.fabricante: getattr(r, col_ventas) * (1 - f * r.transf) for r in g.itertuples()}
    prob += pulp.lpSum(perdida[k] * x[k] for k in x)             # ventas no transferibles conservadas
    prob += pulp.lpSum(x.values()) <= max_grupos
    priv = [r.fabricante for r in g.itertuples() if r.privada]
    if priv and min_privada:
        prob += pulp.lpSum(x[k] for k in priv) >= min(min_privada, len(priv))
    for k in obligatorios:
        if k in x:
            prob += x[k] == 1
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10))
    if pulp.LpStatus[prob.status] != "Optimal":
        return None
    return {k for k, v in x.items() if v.value() > 0.5}


def ventas_conservadas(g, mantenidos, f, col_ventas):
    """Ventas de los mantenidos + parte transferida de los retirados."""
    v = 0.0
    for r in g.itertuples():
        ven = getattr(r, col_ventas)
        v += ven if r.fabricante in mantenidos else f * r.transf * ven
    return v


def _top_k(g, max_grupos, col_ventas, min_privada=1):
    orden = g.sort_values(col_ventas, ascending=False)
    elegidos = list(orden["fabricante"][:max_grupos])
    priv = orden[orden["privada"]]["fabricante"].tolist()
    if min_privada and priv and not set(priv) & set(elegidos):
        elegidos[-1] = priv[0]                       # misma regla de marca propia
    return set(elegidos)


def curva(subcategoria, factor_transferencia=1.0, min_privada=1):
    """Ventas conservadas (ano 1) segun cuantos grupos se mantienen, optimizador y
    referencia. Responde: ¿cuantos fabricantes hacen falta para conservar el X %?"""
    g = grupos(subcategoria)
    total = float(g["ventas_a1"].sum())
    filas = []
    for k in range(1, len(g) + 1):
        mp = min_privada if k >= 2 else 0          # con un solo hueco no se fuerza la marca propia
        rec = _resolver(g, k, factor_transferencia, "ventas_a1", (), mp) if k < len(g) \
            else set(g["fabricante"])
        ref = _top_k(g, k, "ventas_a1", mp) if k < len(g) else set(g["fabricante"])
        filas.append({"grupos": k,
                      "optimizado": ventas_conservadas(g, rec, factor_transferencia, "ventas_a1") / total,
                      "sin_transferencia": ventas_conservadas(g, ref, 0.0, "ventas_a1") / total})
    return pd.DataFrame(filas)


def grupos_para_cobertura(subcategoria, objetivo=0.98, factor_transferencia=1.0, min_privada=1):
    c = curva(subcategoria, factor_transferencia, min_privada)
    ok = c[c["optimizado"] >= objetivo]
    return int(ok["grupos"].min()) if len(ok) else None


def optimize_assortment(subcategoria: str, max_grupos: int | None = None,
                        factor_transferencia: float = 1.0, min_privada: int = 1,
                        obligatorios: list | None = None,
                        cobertura_objetivo: float | None = 0.98) -> dict:
    run_id = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    base = {"run_id": run_id, "tool": "optimize_assortment",
            "parametros": {"categoria": subcategoria, "horizonte": 1,
                           "max_grupos": max_grupos, "factor_transferencia": factor_transferencia,
                           "min_privada": min_privada, "obligatorios": obligatorios or []},
            "version_datos": DATA_VERSION, "generado": datetime.now().isoformat(timespec="seconds")}
    if subcategoria not in NOMBRE_SUB:
        return {**base, "ok": False, "tipo_error": "datos",
                "motivo": f"La subcategoria '{subcategoria}' no tiene datos de surtido suficientes. "
                          f"Disponibles: {', '.join(NOMBRE_SUB.values())}."}
    g = grupos(subcategoria)
    if max_grupos is None:
        if cobertura_objetivo is None or not 0.5 <= cobertura_objetivo < 1:
            return {**base, "ok": False, "tipo_error": "argumento",
                    "motivo": "Indica cuantos grupos mantener o una cobertura objetivo (50 % a 99,9 %)."}
        max_grupos = grupos_para_cobertura(subcategoria, cobertura_objetivo, factor_transferencia,
                                           min_privada) or len(g) - 1
        max_grupos = min(max_grupos, len(g) - 1)
        base["parametros"]["max_grupos"] = max_grupos
        base["parametros"]["cobertura_objetivo"] = cobertura_objetivo
    if not 1 <= max_grupos < len(g):
        return {**base, "ok": False, "tipo_error": "argumento",
                "motivo": f"Numero de grupos a mantener fuera de rango (1 a {len(g) - 1}; la "
                          f"subcategoria tiene {len(g)})."}
    if not 0 <= factor_transferencia <= 1:
        return {**base, "ok": False, "tipo_error": "argumento",
                "motivo": "El factor de transferencia debe estar entre 0 y 1."}

    obl = list(obligatorios or [])
    rec = _resolver(g, max_grupos, factor_transferencia, "ventas_a1", obl, min_privada)
    if rec is None:
        return {**base, "ok": False, "tipo_error": "argumento",
                "motivo": "Restricciones incompatibles (obligatorios o marca propia superan el maximo)."}
    ref = _top_k(g, max_grupos, "ventas_a1", min_privada)
    total_a1 = float(g["ventas_a1"].sum())

    def resumen(mant, f, col):
        tot = float(g[col].sum())
        v = ventas_conservadas(g, mant, f, col)
        return {"ventas_conservadas_eur": round(v), "pct_conservado": round(v / tot, 4) if tot else None}

    # Sensibilidad: el mismo surtido recomendado con la transferencia al 50, 75 y 100 %
    sens = {f"{int(f * 100)}%": {"recomendado": resumen(rec, f, "ventas_a1"),
                                 "referencia": resumen(ref, f, "ventas_a1")}
            for f in FACTORES_SENSIBILIDAD}

    # Validacion: decidir con el ano 1, evaluar con el ano 2
    g2 = g.copy()
    optimo_a2 = _resolver(g2, max_grupos, factor_transferencia, "ventas_a2", obl, min_privada)
    val = {
        "recomendado": resumen(rec, factor_transferencia, "ventas_a2"),
        "referencia": resumen(ref, factor_transferencia, "ventas_a2"),
        "optimo_con_ano_2": resumen(optimo_a2 or rec, factor_transferencia, "ventas_a2"),
    }
    val["arrepentimiento_eur"] = (val["optimo_con_ano_2"]["ventas_conservadas_eur"]
                                  - val["recomendado"]["ventas_conservadas_eur"])

    filas = []
    for r in g.itertuples():
        filas.append({"fabricante": int(r.fabricante), "marca_propia": bool(r.privada),
                      "ventas_a1": round(r.ventas_a1), "hogares_a1": int(r.hogares_a1),
                      "transferencia": round(float(r.transf), 2),
                      "ventas_no_transferibles": round(r.ventas_a1 * (1 - factor_transferencia * r.transf)),
                      "mantener": r.fabricante in rec, "en_referencia": r.fabricante in ref})
    retirados = [f for f in filas if not f["mantener"]]
    pocos = [f"fabricante {f['fabricante']} ({f['hogares_a1']} hogares)" for f in filas
             if f["hogares_a1"] < MIN_HOGARES and (f["mantener"] or f["ventas_a1"] > 0.02 * total_a1)]
    v_rec = round(ventas_conservadas(g, rec, factor_transferencia, "ventas_a1"))
    v_ref = round(ventas_conservadas(g, ref, factor_transferencia, "ventas_a1"))
    metricas = {
        "grupos_total": len(g), "grupos_mantenidos": len(rec), "grupos_retirados": len(retirados),
        "ventas_a1_eur": round(total_a1),
        "ventas_retiradas_eur": round(sum(f["ventas_a1"] for f in retirados)),
        "ventas_conservadas_eur": v_rec,
        "pct_conservado": round(v_rec / total_a1, 4),
        "ventas_conservadas_referencia_eur": v_ref,
        "mejora_vs_referencia_eur": v_rec - v_ref,
    }
    return {
        **base, "ok": True,
        "resultado": {"subcategoria_nombre": NOMBRE_SUB[subcategoria], "grupos": filas,
                      "metricas": metricas, "sensibilidad": sens, "validacion": val,
                      "coincide_con_referencia": rec == ref},
        "metadata": {
            "modelo": "Programa lineal entero (PuLP + CBC) sobre ventas no transferibles",
            "unidad_decision": "fabricante dentro de subcategoria (marca x formato)",
            "evidencia": {
                "ventas": {"nivel": "medido", "depende_de": "tickets de 2.500 hogares, semanas 20-60"},
                "transferencia": {"nivel": "estimado",
                                  "depende_de": "hogares que compran otro fabricante de la subcategoria"},
                "ventas_conservadas": {"nivel": "estimado",
                                       "depende_de": "transferencia estimada y factor supuesto"},
            },
            "categorias_baja_fiabilidad": pocos,
            "supuestos": [
                {"nombre": "factor_transferencia", "valor": factor_transferencia,
                 "origen": "multiplica la transferencia estimada (cota superior); sensibilidad "
                           "0 / 0,5 / 0,75 / 1",
                 "fecha": FECHA_SUPUESTOS},
                {"nombre": "ajuste_grupos_pequenos", "valor": "Bayes empirico, peso de 30 hogares",
                 "origen": "los grupos con pocos compradores se acercan a la media de la subcategoria",
                 "fecha": FECHA_SUPUESTOS},
                {"nombre": "destino_de_la_demanda", "valor": "grupos mantenidos",
                 "origen": "la demanda transferida se reparte entre los que se quedan",
                 "fecha": FECHA_SUPUESTOS},
            ],
            "supuestos_declarados": True,
            "limites": [
                "Que un hogar compre otro fabricante indica que podria cambiar, no prueba que lo hiciera.",
                "Sin margenes por referencia ni espacio en lineal: se conservan ventas, no beneficio.",
                "Sin roturas de stock ni retiradas reales para medir la sustitucion.",
                "Muestra de 2.500 hogares; los grupos con menos de 30 compradores son inestables.",
            ],
        },
    }
