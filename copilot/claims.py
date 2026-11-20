"""Afirmaciones estructuradas (claims) y su verificación.

En lugar de dejar que el agente escriba texto libre con números, el flujo es:
  1) la tool devuelve un resultado estructurado,
  2) se construyen claims canónicos a partir de ese resultado,
  3) cada claim se re-verifica contra la ejecución que lo respalda,
  4) el texto final se RENDERIZA a partir de los claims verificados.

Así una cifra no puede atribuirse a otra categoría ni invertir su significado:
el claim ata (métrica, categoría, periodo, valor, unidad) a un campo concreto
de un run_id concreto, y la verificación vuelve a leer ese campo.
"""
from dataclasses import dataclass


@dataclass
class Claim:
    id: str
    metrica: str
    categoria: str
    periodo: str
    valor: object
    unidad: str
    run_id: str
    campo: str          # ruta al campo de origen; "meta:" = metadatos


def periodo(h: int) -> str:
    return "1 semana" if h == 1 else f"{h} semanas"


def _leer(salida: dict, campo: str):
    """Navega a un campo del resultado (o de metadata con prefijo 'meta:')."""
    if campo.startswith("meta:"):
        nodo = salida["metadata"]
        campo = campo[5:]
    else:
        nodo = salida["resultado"]
    for parte in campo.split("."):
        if isinstance(nodo, dict):
            nodo = nodo.get(parte)
        else:
            return None
    return nodo


def construir_claims(salida: dict):
    """Claims canónicos a partir de una ejecución con éxito."""
    if not salida.get("ok"):
        return []
    cat = salida["parametros"]["categoria"]
    rid = salida["run_id"]
    r = salida["resultado"]
    cl = []
    if salida["tool"] == "get_category_forecast":
        h = salida["parametros"]["horizonte"]
        per = periodo(h)
        cl += [
            Claim(f"{rid}-vol", "prevision_volumen", cat, per,
                  r["prediccion_total"], "unidades", rid, "prediccion_total"),
            Claim(f"{rid}-lo", "intervalo_bajo", cat, per,
                  r["intervalo_total"]["baja"], "unidades", rid, "intervalo_total.baja"),
            Claim(f"{rid}-hi", "intervalo_alto", cat, per,
                  r["intervalo_total"]["alta"], "unidades", rid, "intervalo_total.alta"),
            Claim(f"{rid}-wape", "wape_referencia", cat, "validacion",
                  salida["metadata"]["wape_referencia"], "fraccion", rid,
                  "meta:wape_referencia"),
        ]
    elif salida["tool"] == "evaluate_promo_roi":
        cl.append(Claim(f"{rid}-sem", "semaforo", cat, "promo tipica",
                        r["semaforo"], "", rid, "semaforo"))
        if r["roi"] is not None:
            cl.append(Claim(f"{rid}-roi", "roi", cat, "promo tipica",
                            r["roi"], "", rid, "roi"))
        cl += [
            Claim(f"{rid}-upl", "uplift", cat, "promo tipica",
                  r["uplift_pct"], "%", rid, "uplift_pct"),
            Claim(f"{rid}-cos", "coste", cat, "promo tipica",
                  r["coste_eur"], "EUR", rid, "coste_eur"),
            Claim(f"{rid}-ben", "beneficio_incremental", cat, "promo tipica",
                  r["beneficio_incremental_eur"], "EUR", rid, "beneficio_incremental_eur"),
        ]
        cl.append(Claim(f"{rid}-ven", "ventas_incrementales", cat, "promo tipica",
                        r["metricas"]["ventas_incrementales_eur"], "EUR", rid,
                        "metricas.ventas_incrementales_eur"))
    elif salida["tool"] == "optimize_promo_program":
        per = periodo(salida["parametros"]["horizonte"])
        t = r["totales"]
        cl += [
            Claim(f"{rid}-np", "programa_promociones", cat, per,
                  t["n_promociones"], "promociones", rid, "totales.n_promociones"),
            Claim(f"{rid}-pc", "programa_coste", cat, per,
                  t["coste_eur"], "EUR", rid, "totales.coste_eur"),
            Claim(f"{rid}-pb", "programa_beneficio", cat, per,
                  t["beneficio_eur"], "EUR", rid, "totales.beneficio_eur"),
        ]
        if t["n_promociones"]:
            ilu = r["beneficio_ilustrativo"]
            for esc in ("bajo", "alto"):
                cl.append(Claim(f"{rid}-pb{esc[0]}", f"programa_beneficio_{esc}", cat, per,
                                ilu[esc]["beneficio_eur"], "EUR", rid,
                                f"beneficio_ilustrativo.{esc}.beneficio_eur"))
            cl.append(Claim(f"{rid}-pu", "programa_unidades", cat, per,
                            r["metricas"]["unidades_incrementales"], "unidades", rid,
                            "metricas.unidades_incrementales"))
            cl.append(Claim(f"{rid}-pv", "programa_ventas", cat, per,
                            r["metricas"]["ventas_incrementales_eur"], "EUR", rid,
                            "metricas.ventas_incrementales_eur"))
        if t["roi"] is not None:
            cl.append(Claim(f"{rid}-pr", "programa_roi", cat, per,
                            t["roi"], "", rid, "totales.roi"))
    elif salida["tool"] == "optimize_assortment":
        m = r["metricas"]
        v = r["validacion"]
        cl += [
            Claim(f"{rid}-sm", "surtido_mantenidos", cat, "año 1", m["grupos_mantenidos"],
                  "grupos", rid, "metricas.grupos_mantenidos"),
            Claim(f"{rid}-st", "surtido_total", cat, "año 1", m["grupos_total"], "grupos", rid,
                  "metricas.grupos_total"),
            Claim(f"{rid}-sp", "surtido_pct_conservado", cat, "año 1", m["pct_conservado"],
                  "fraccion", rid, "metricas.pct_conservado"),
            Claim(f"{rid}-sv", "surtido_ventas_conservadas", cat, "año 1",
                  m["ventas_conservadas_eur"], "EUR", rid, "metricas.ventas_conservadas_eur"),
            Claim(f"{rid}-sr", "surtido_ventas_retiradas", cat, "año 1",
                  m["ventas_retiradas_eur"], "EUR", rid, "metricas.ventas_retiradas_eur"),
            Claim(f"{rid}-s50", "surtido_pct_mitad_transferencia", cat, "año 1",
                  r["sensibilidad"]["50%"]["recomendado"]["pct_conservado"], "fraccion", rid,
                  "sensibilidad.50%.recomendado.pct_conservado"),
            Claim(f"{rid}-s0", "surtido_pct_sin_transferencia", cat, "año 1",
                  r["sensibilidad"]["0%"]["recomendado"]["pct_conservado"], "fraccion", rid,
                  "sensibilidad.0%.recomendado.pct_conservado"),
            Claim(f"{rid}-sa2", "surtido_pct_validacion", cat, "año 2",
                  v["recomendado"]["pct_conservado"], "fraccion", rid,
                  "validacion.recomendado.pct_conservado"),
        ]
    elif salida["tool"] == "recommend_promo_decision":
        per = periodo(salida["parametros"]["horizonte"])
        rec = r["recomendacion"]
        m = rec["metricas"]
        cl += [
            Claim(f"{rid}-de", "decision_escenario", cat, per, rec["escenario"], "", rid,
                  "recomendacion.escenario"),
            Claim(f"{rid}-dst", "decision_estado", cat, per, r["estado"], "", rid, "estado"),
            Claim(f"{rid}-dn", "decision_promociones", cat, per, m["n_promociones"],
                  "promociones", rid, "recomendacion.metricas.n_promociones"),
            Claim(f"{rid}-dv", "decision_ventas", cat, per, m["ventas_incrementales_eur"],
                  "EUR", rid, "recomendacion.metricas.ventas_incrementales_eur"),
            Claim(f"{rid}-du", "decision_unidades", cat, per, m["unidades_incrementales"],
                  "unidades", rid, "recomendacion.metricas.unidades_incrementales"),
            Claim(f"{rid}-dc", "decision_coste", cat, per, m["coste_eur"], "EUR", rid,
                  "recomendacion.metricas.coste_eur"),
        ]
        if r["por_que"]["ventaja_vs_actual"] is not None:
            cl.append(Claim(f"{rid}-dva", "decision_ventaja_actual", cat, per,
                            r["por_que"]["ventaja_vs_actual"],
                            {"ventas": "EUR", "volumen": "unidades"}[
                                salida["parametros"]["objetivo"]], rid,
                            "por_que.ventaja_vs_actual"))
        if m["n_promociones"]:
            for esc in ("bajo", "base", "alto"):
                cl.append(Claim(f"{rid}-db{esc[:2]}", f"decision_beneficio_{esc}", cat, per,
                                m["beneficio_ilustrativo_eur"][esc], "EUR", rid,
                                f"recomendacion.metricas.beneficio_ilustrativo_eur.{esc}"))
        if r.get("margen_critico_pp"):
            cl.append(Claim(f"{rid}-dmc", "decision_margen_critico", cat, per,
                            r["margen_critico_pp"], "pp", rid, "margen_critico_pp"))
    return cl


# Especificacion esperada de cada metrica: unidad y periodo segun la ejecucion.
ESPEC = {
    "prevision_volumen":     ("unidades", "horizonte"),
    "intervalo_bajo":        ("unidades", "horizonte"),
    "intervalo_alto":        ("unidades", "horizonte"),
    "wape_referencia":       ("fraccion", "validacion"),
    "semaforo":              ("", "promo tipica"),
    "roi":                   ("", "promo tipica"),
    "uplift":                ("%", "promo tipica"),
    "coste":                 ("EUR", "promo tipica"),
    "beneficio_incremental": ("EUR", "promo tipica"),
    "ventas_incrementales":  ("EUR", "promo tipica"),
    "programa_ventas":       ("EUR", "horizonte"),
    "programa_unidades":     ("unidades", "horizonte"),
    "programa_beneficio_bajo": ("EUR", "horizonte"),
    "surtido_mantenidos":    ("grupos", "año 1"),
    "surtido_total":         ("grupos", "año 1"),
    "surtido_pct_conservado": ("fraccion", "año 1"),
    "surtido_ventas_conservadas": ("EUR", "año 1"),
    "surtido_ventas_retiradas": ("EUR", "año 1"),
    "surtido_pct_mitad_transferencia": ("fraccion", "año 1"),
    "surtido_pct_validacion": ("fraccion", "año 2"),
    "surtido_pct_sin_transferencia": ("fraccion", "año 1"),
    "decision_escenario":    ("", "horizonte"),
    "decision_estado":       ("", "horizonte"),
    "decision_promociones":  ("promociones", "horizonte"),
    "decision_ventas":       ("EUR", "horizonte"),
    "decision_unidades":     ("unidades", "horizonte"),
    "decision_coste":        ("EUR", "horizonte"),
    "decision_ventaja_actual": ("objetivo", "horizonte"),
    "decision_beneficio_bajo": ("EUR", "horizonte"),
    "decision_beneficio_base": ("EUR", "horizonte"),
    "decision_beneficio_alto": ("EUR", "horizonte"),
    "decision_margen_critico": ("pp", "horizonte"),
    "programa_beneficio_alto": ("EUR", "horizonte"),
    "programa_promociones":  ("promociones", "horizonte"),
    "programa_coste":        ("EUR", "horizonte"),
    "programa_beneficio":    ("EUR", "horizonte"),
    "programa_roi":          ("", "horizonte"),
}


def verificar_detalle(claim: Claim, salidas: list):
    """Re-lee el campo de origen y comprueba categoria, metrica, periodo, unidad
    y valor. Devuelve (ok, motivo)."""
    fuente = next((s for s in salidas if s.get("run_id") == claim.run_id and s.get("ok")), None)
    if fuente is None:
        return False, "sin ejecucion de origen"
    if fuente["parametros"].get("categoria") != claim.categoria:
        return False, "categoria distinta de la evaluada"
    if claim.metrica not in ESPEC:
        return False, "metrica desconocida"
    unidad_esp, periodo_esp = ESPEC[claim.metrica]
    if unidad_esp == "objetivo":           # la unidad depende del objetivo de la decision
        unidad_esp = {"ventas": "EUR", "volumen": "unidades"}[fuente["parametros"]["objetivo"]]
    if periodo_esp == "horizonte":
        periodo_esp = periodo(fuente["parametros"]["horizonte"])
    if claim.unidad != unidad_esp:
        return False, f"unidad '{claim.unidad}' (esperada '{unidad_esp}')"
    if claim.periodo != periodo_esp:
        return False, f"periodo '{claim.periodo}' (esperado '{periodo_esp}')"
    real = _leer(fuente, claim.campo)
    if real is None:
        return False, "campo inexistente en la evidencia"
    if isinstance(claim.valor, str) or isinstance(real, str):
        ok = str(real) == str(claim.valor)
    else:
        # Las fracciones (0-1) se comparan con tolerancia fina: 0,5 seria todo el rango.
        tol = 0.0005 if claim.unidad == "fraccion" else 0.5
        ok = abs(float(real) - float(claim.valor)) < tol or (
            claim.unidad != "fraccion" and real
            and abs(float(real) - float(claim.valor)) / abs(float(real)) < 0.01)
    return (True, "") if ok else (False, "valor distinto del de la evidencia")


def verificar(claim: Claim, salidas: list) -> bool:
    return verificar_detalle(claim, salidas)[0]


def verificar_todos(claims, salidas):
    """Lista de (claim, ok, motivo)."""
    return [(c, *verificar_detalle(c, salidas)) for c in claims]


def render(salida: dict, claims: list) -> str:
    """Construye el texto SOLO a partir de los claims (ya verificados)."""
    v = {c.metrica: c for c in claims}
    cat = salida["parametros"]["categoria"]
    if salida["tool"] == "get_category_forecast":
        vol, lo, hi, wape = (v["prevision_volumen"], v["intervalo_bajo"],
                             v["intervalo_alto"], v["wape_referencia"])
        return (f"Previsión de {cat} a {vol.periodo}: {vol.valor} unidades "
                f"(rango {lo.valor}–{hi.valor}). WAPE de referencia {round(wape.valor * 100)}%.")
    if salida["tool"] == "optimize_promo_program":
        return _render_programa(salida, v)
    if salida["tool"] == "recommend_promo_decision":
        return _render_decision(salida, v)
    if salida["tool"] == "optimize_assortment":
        return _render_surtido(salida, v)
    # evaluate_promo_roi
    sem = v["semaforo"].valor
    roi_txt = f"{v['roi'].valor}" if "roi" in v else "sin coste"
    margen = next(x["valor"] for x in salida["metadata"]["supuestos"] if x["nombre"] == "margen")
    txt = (f"Promoción típica en {cat}: uplift previsto {v['uplift'].valor}% y ventas "
           f"incrementales {v['ventas_incrementales'].valor} € a precio de cliente (estimado). "
           f"Con un margen supuesto del {round(margen * 100)}%: ROI {roi_txt} ({sem}), "
           f"coste {v['coste'].valor} €, beneficio incremental "
           f"{v['beneficio_incremental'].valor} €.")
    return txt


NOMBRE_RESTRICCION = {
    "presupuesto": "el presupuesto",
    "huecos_por_semana": "los huecos de folleto por semana",
    "promociones_por_categoria": "el máximo de promociones por categoría",
    "descuento_total_maximo": "el descuento total máximo",
    "roi_minimo": "el ROI mínimo exigido",
}


def _render_programa(salida, v):
    p = salida["parametros"]
    res = salida["resultado"]
    n = v["programa_promociones"].valor
    excl = ", ".join(e["categoria"] for e in res["excluidas"]
                     if e["motivo"] == "ROI por debajo del minimo") if p.get("roi_minimo") is not None else ""
    if n == 0 and res.get("candidatas"):
        return (f"Ninguna promoción mejora {salida['metadata']['objetivo_descripcion']} dentro "
                f"de las restricciones: el programa óptimo para "
                f"{v['programa_promociones'].periodo} es no promocionar.")
    if n == 0:
        return (f"Con {p['puntos_descuento_extra']} puntos de descuento, ninguna promoción "
                f"supera el ROI mínimo pedido ({p['roi_minimo']}, calculado con un margen "
                f"supuesto): el programa para {v['programa_promociones'].periodo} es no "
                f"promocionar.")
    semanas = {}
    for r in res["calendario"]:
        semanas.setdefault(r["semana"], []).append(r["categoria"])
    cal = " ".join(f"Semana {w}: {', '.join(cs)}." for w, cs in sorted(semanas.items()))
    roi = f", ROI {v['programa_roi'].valor}" if "programa_roi" in v else ""
    pres = f"{p['presupuesto_eur']:,.0f}".replace(",", ".")
    meta = salida["metadata"]
    txt = (f"Programa óptimo para {v['programa_promociones'].periodo} con un presupuesto de "
           f"{pres} €, maximizando "
           f"{meta['objetivo_descripcion']}: "
           f"{n} {'promoción' if n == 1 else 'promociones'}, ventas incrementales {v['programa_ventas'].valor} € y "
           f"{v['programa_unidades'].valor} unidades incrementales (estimado), coste "
           f"{v['programa_coste'].valor} € (descuento que asume el distribuidor). {cal} "
           f"Beneficio ilustrativo con márgenes supuestos: {v['programa_beneficio'].valor} € "
           f"con el margen base{roi}, entre {v['programa_beneficio_bajo'].valor} € (-5 pp) y "
           f"{v['programa_beneficio_alto'].valor} € (+5 pp); no es un óptimo en beneficio.")
    activas = [NOMBRE_RESTRICCION[r["nombre"]] for r in meta.get("restricciones", [])
               if r["activa"]]
    if activas:
        txt += f" Lo que limita el programa: {', '.join(activas)}."
    if excl:
        txt += (f" No entran por el ROI mínimo pedido, calculado con un margen supuesto: "
                f"{excl}.")
    return txt


NOMBRE_METRICA = {
    "unidades_incrementales": ("unidades incrementales", "unidades"),
    "ventas_incrementales_eur": ("ventas incrementales", "€"),
    "coste_eur": ("coste", "€"),
    "beneficio_eur": ("beneficio ilustrativo", "€"),
    "roi": ("ROI ilustrativo", ""),
    "descuento_total_eur": ("descuento total", "€"),
}


def _miles(x):
    return f"{x:,.0f}".replace(",", ".") if isinstance(x, (int, float)) and abs(x) >= 1000 \
        else str(x)


def _palanca(k, val):
    return {
        "presupuesto_eur": lambda x: f"presupuesto de {_miles(x)} €",
        "mecanica": lambda x: f"mecánica {x.replace('_', ' ')}",
        "max_promos_categoria": lambda x: f"hasta {x} promociones por categoría",
        "max_promos_semana": lambda x: f"{x} huecos de folleto por semana",
        "roi_minimo": lambda x: f"ROI mínimo {x} (margen supuesto)",
        "max_descuento_total_eur": lambda x: f"descuento total máximo de {_miles(x)} €",
    }[k](val)


def _describir_escenario(R, nombre):
    if nombre == "actual":
        return "mantener el plan actual"
    if nombre == "optimizada":
        return "el programa óptimo con las palancas actuales"
    e = next(x for x in R["escenarios"] if x["nombre"] == nombre)
    return "el programa óptimo con " + ", ".join(_palanca(k, x) for k, x in e["cambios"].items())


def _render_decision(salida, v):
    """Texto que empieza por la decision de negocio, no por el algoritmo."""
    R = salida["resultado"]
    meta = salida["metadata"]
    rec = R["recomendacion"]
    per = v["decision_escenario"].periodo
    n = v["decision_promociones"].valor
    unidad_obj = "€" if salida["parametros"]["objetivo"] == "ventas" else "unidades"
    if n == 0:
        txt = (f"Recomendación (propuesta, pendiente de aprobación): no promocionar en {per}. "
               f"Ningún escenario viable mejora {meta['objetivo_descripcion']}.")
    else:
        semanas = {}
        for r in rec["calendario"]:
            semanas.setdefault(r["semana"], []).append(r["categoria"])
        cal = " ".join(f"Semana {w}: {', '.join(cs)}." for w, cs in sorted(semanas.items()))
        txt = (f"Recomendación (propuesta, pendiente de aprobación): "
               f"{_describir_escenario(R, v['decision_escenario'].valor)}, {n} "
               f"{'promoción' if n == 1 else 'promociones'} en {per}. {cal} "
               f"Resultado esperado (estimado): ventas incrementales "
               f"{_miles(v['decision_ventas'].valor)} € y "
               f"{_miles(v['decision_unidades'].valor)} unidades incrementales; coste "
               f"{_miles(v['decision_coste'].valor)} € de descuento que asume el distribuidor.")
    if "decision_ventaja_actual" in v:
        va = v["decision_ventaja_actual"].valor
        txt += (f" Frente al plan actual: {'+' if va >= 0 else '−'}{_miles(abs(va))}"
                + (f" € de {meta['objetivo_descripcion']}." if unidad_obj == "€"
                   else f" {meta['objetivo_descripcion']}."))
    if R["descartadas"]:
        txt += (" Por qué: es el escenario viable con más " + meta["objetivo_descripcion"]
                + "; descarta " + ", ".join(d["escenario"] for d in R["descartadas"]) + ".")
    if R["compromisos"]:
        partes = []
        for c in R["compromisos"]:
            nombre, u = NOMBRE_METRICA.get(c["metrica"], (c["metrica"], ""))
            partes.append(f"{nombre} {'+' if c['diferencia'] > 0 else '−'}"
                          f"{_miles(abs(c['diferencia']))}{' ' + u if u else ''}")
        txt += " Compromiso frente al plan actual: " + ", ".join(partes) + "."
    if n:
        txt += (f" Beneficio ilustrativo con márgenes supuestos: "
                f"{_miles(v['decision_beneficio_base'].valor)} € con el margen base, entre "
                f"{_miles(v['decision_beneficio_bajo'].valor)} € (-5 pp) y "
                f"{_miles(v['decision_beneficio_alto'].valor)} € (+5 pp); no es un óptimo en "
                f"beneficio.")
    if "decision_margen_critico" in v:
        txt += (f" Supuesto crítico: con el margen supuesto pierde dinero; necesitaría "
                f"{v['decision_margen_critico'].valor} puntos más de margen para no perder.")
    elif n and R.get("margen_critico_pp") is None:
        txt += (f" Supuesto crítico: ni con {R['margen_critico_tope_pp']} puntos más de margen "
                f"deja de perder dinero.")
    return txt


def _pct_txt(x):
    return f"{x * 100:.1f}".replace(".", ",") + " %"


def _render_surtido(salida, v):
    R = salida["resultado"]
    mant = [str(g["fabricante"]) + (" (marca propia)" if g["marca_propia"] else "")
            for g in R["grupos"] if g["mantener"]]
    f = salida["parametros"]["factor_transferencia"]
    txt = (f"Surtido recomendado para {R['subcategoria_nombre'].lower()}: mantener "
           f"{v['surtido_mantenidos'].valor} de {v['surtido_total'].valor} fabricantes "
           f"({', '.join(mant)}). Ventas que se conservarían (estimado): entre el "
           f"{_pct_txt(v['surtido_pct_sin_transferencia'].valor)}, si nadie cambiara de fabricante, y el "
           f"{_pct_txt(v['surtido_pct_conservado'].valor)} ({_miles(v['surtido_ventas_conservadas'].valor)} €), "
           f"si la demanda de los retirados se pasara a los que quedan en la proporción estimada")
    txt += "." if f == 1 else f" al {round(f * 100)} %."
    txt += (f" Esa transferencia es una cota superior. Con la mitad: "
            f"{_pct_txt(v['surtido_pct_mitad_transferencia'].valor)}. Los retirados vendían "
            f"{_miles(v['surtido_ventas_retiradas'].valor)} €. Comprobado con el año siguiente: "
            f"{_pct_txt(v['surtido_pct_validacion'].valor)}.")
    if R["coincide_con_referencia"]:
        txt += " Coincide con quedarse con los que más venden."
    return txt
