"""Pestana Prevision: dos enfoques sobre las mismas ventas.

  Demanda                    cuanto voy a vender (planificacion y compras)
  Efecto de las promociones  cuanto de lo que vendo se asocia a las promociones y
                             cuanto cuesta cada unidad extra (RGM, fabricante CPG)

Cada grafico abre con un titular que dice su mensaje; los supuestos editables
quedan plegados en "¿Y si...?".
"""
import altair as alt
import pandas as pd
import streamlit as st

import vistas_prevision as vp
from proyeccion import ELASTICIDAD_REFERENCIA, FUENTE_ELASTICIDAD, historico, proyectar
from tools import categorias_disponibles
from ui_decision import (AMBAR, AZUL, ETIQUETA_PROMO, NOMBRE_CAT, NOMBRE_MECANICA, ROJO,
                         SUAVE, TINTA, VERDE, _n, _pct)

MILES = "replace(format(datum.value, ',.0f'), ',', '.')"
GRIS_HIST = "#9AA8BF"


def _estilo(graf, alto=300):
    return (graf.properties(height=alto).configure(font="Plus Jakarta Sans")
            .configure_view(stroke=None)
            .configure_axis(gridColor="#EEF2F7", domain=False, labelColor=SUAVE,
                            titleColor=SUAVE, labelFontSize=12, titleFontSize=12)
            .configure_legend(orient="top", labelFontSize=12))


def _titular(texto, detalle=""):
    st.markdown(f"<p class='cp-titular' style='font-size:1.3rem;margin:4px 0 2px'>{texto}</p>"
                f"<div class='cp-nota' style='margin-bottom:12px'>{detalle}</div>",
                unsafe_allow_html=True)


def _programa():
    """Calendario de la ultima recomendacion evaluada, si la hay."""
    r = st.session_state.get("decision")
    salida = next((s for s in (r or {}).get("evidencia", []) if s.get("ok")), None)
    if not salida:
        return [], None
    rec = salida["resultado"]["recomendacion"]
    return rec["calendario"], salida["parametros"]["horizonte"]


def _selector_categoria(clave, calendario):
    cats = categorias_disponibles()
    en_prog = [c for c in cats if any(r["categoria"] == c for r in calendario)]
    return st.selectbox("Categoría", cats, index=cats.index(en_prog[0]) if en_prog else 3,
                        format_func=lambda c: NOMBRE_CAT.get(c, c), key=clave)


# ---- Demanda -------------------------------------------------------------------

def _demanda(calendario, sem_prog):
    c1, c2 = st.columns([2, 1])
    with c1:
        cat = _selector_categoria("dm_cat", calendario)
    horizonte = c2.slider("Semanas vista", 1, 26, max(sem_prog or 1, 12), key="dm_h")
    with st.expander("¿Y si…? Supuestos de promoción y precio"):
        c1, c2, c3 = st.columns(3)
        efecto = c1.slider("Efecto de la promoción (% del estimado)", 0, 200, 100, step=10,
                           key="dm_ef")
        precio = c2.slider("Cambio de precio (%)", -10.0, 10.0, 0.0, step=0.5, key="dm_p")
        elast = c3.slider("Elasticidad precio", -4.0, 0.0, ELASTICIDAD_REFERENCIA, step=0.01,
                          key="dm_el", help=f"Supuesto, no medida en estos datos. "
                                            f"Referencia: {FUENTE_ELASTICIDAD}.")
    p = proyectar(cat, horizonte, calendario, efecto, precio, elast)
    res = p["resumen"]
    nombre = NOMBRE_CAT.get(cat, cat)
    bt = vp.backtest(cat)
    semanal = round(res["unidades_base"] / horizonte)
    extra = res["unidades_con_programa"] - res["unidades_base"]
    titular = f"{nombre}: unas {_n(semanal)} unidades por semana sin promociones"
    if extra:
        titular += f"; el programa añade {_n(extra)} en {horizonte} semanas"
    detalle = ("Error medido a 1 semana: " +
               (f"{_n(bt['wape'] * 100, 1)} % en {bt['semanas']} semanas de validación "
                f"(línea punteada)." if bt else "WAPE del 11 % en backtesting.") +
               " Más allá de la semana 1 el error no está medido y la banda se abre.")
    _titular(titular, detalle)

    df = pd.DataFrame(p["semanas"])
    series = []
    hist = historico(cat)
    largo = []
    if hist is not None:
        h0 = int(hist["semana"].max())
        largo.append(hist.assign(semana=hist["semana"] - h0, serie="Real")[
            ["semana", "serie", "unidades"]])
        series.append(("Real", GRIS_HIST, [1, 0]))
    if bt and hist is not None:
        t = bt["tabla"]
        t = t[t["semana"] > h0 - 26]
        if len(t):
            largo.append(t.assign(semana=t["semana"] - h0, serie="Predicho en validación",
                                  unidades=t["prediccion"])[["semana", "serie", "unidades"]])
            series.append(("Predicho en validación", AMBAR, [2, 3]))
    largo.append(df.assign(serie="Previsión base", unidades=df["base"])[
        ["semana", "serie", "unidades"]])
    series.append(("Previsión base", TINTA, [1, 0]))
    if calendario:
        largo.append(df.assign(serie="Con el programa", unidades=df["con_programa"])[
            ["semana", "serie", "unidades"]])
        series.append(("Con el programa", AZUL, [7, 5]))
    largo = pd.concat(largo)
    x = alt.X("semana:Q", title="Semanas (0 = última semana con datos)",
              axis=alt.Axis(tickMinStep=1))
    color = alt.Color("serie:N", scale=alt.Scale(domain=[s[0] for s in series],
                                                 range=[s[1] for s in series]),
                      legend=alt.Legend(orient="top", title=None, labelFontSize=12,
                                        symbolStrokeWidth=3))
    trazo = alt.StrokeDash("serie:N", legend=None, scale=alt.Scale(
        domain=[s[0] for s in series], range=[s[2] for s in series]))
    banda = alt.Chart(df).mark_area(opacity=.12, color=AZUL, interpolate="monotone").encode(
        x=x, y=alt.Y("banda_baja:Q", title="Unidades por semana",
                     axis=alt.Axis(labelExpr=MILES)), y2="banda_alta:Q")
    lineas = alt.Chart(largo).mark_line(interpolate="monotone", strokeWidth=2.4).encode(
        x=x, y="unidades:Q", color=color, strokeDash=trazo,
        tooltip=["semana", "serie", alt.Tooltip("unidades:Q", format=",.0f")])
    capas = banda + lineas
    if calendario and df["promocion"].any():
        capas += alt.Chart(df[df["promocion"]]).mark_point(
            filled=True, size=130, shape="diamond", color=ETIQUETA_PROMO, stroke=TINTA,
            strokeWidth=1).encode(x=x, y="con_programa:Q")
    capas += alt.Chart(pd.DataFrame({"x": [0.5]})).mark_rule(
        color=SUAVE, strokeDash=[2, 3]).encode(x="x:Q")
    st.altair_chart(_estilo(capas, 320), width="stretch", theme=None)

    puntos = []
    if not calendario:
        puntos.append("- Evalúa una decisión en el espacio de decisión para ver aquí la línea "
                      "con el programa recomendado.")
    if precio:
        puntos.append(
            f"- Con un {_pct(precio)} % de precio y elasticidad {_n(elast, 2)}, las unidades "
            f"base cambian un {_pct(res['efecto_precio_unidades_pct'])} % y los ingresos base "
            f"un {_pct(res['efecto_precio_ingresos_pct'])} % "
            f"({_n(res['ingresos_base_eur'] - res['ingresos_base_sin_cambio_eur'])} € en "
            f"{horizonte} semanas).")
    puntos.append("- La previsión base no tiene estacionalidad validada: es el nivel medio de "
                  "una semana sin promoción. Los picos del histórico son, sobre todo, semanas "
                  "de folleto.")
    etiquetas = {"efecto_promocion": "efecto de la promoción", "cambio_precio": "cambio de precio",
                 "elasticidad_precio": "elasticidad", "banda_error": "banda de error",
                 "nivel_base": "nivel base"}
    puntos.append("- Supuestos: " + "; ".join(
        f"{etiquetas[x['nombre']]} "
        f"{_n(x['valor'], 2) if isinstance(x['valor'], float) else str(x['valor']).replace('.', ',')}"
        f" ({x['nivel']})" for x in p["supuestos"]) + ".")
    st.markdown("\n".join(puntos))


# ---- Efecto de las promociones -------------------------------------------------------

def _efecto(calendario):
    cat = _selector_categoria("ef_cat", calendario)
    nombre = NOMBRE_CAT.get(cat, cat)

    # 1. Descomposicion historica
    dec = vp.descomposicion(cat)
    if dec:
        _titular(f"El {_n(dec['cuota_promocion'] * 100)} % de las unidades de "
                 f"{nombre.lower()} se asocia a folleto y display",
                 f"Últimas {dec['semanas']} semanas. Folleto {_n(dec['cuota_folleto'] * 100, 1)} % "
                 f"y display {_n(dec['cuota_display'] * 100, 1)} %, según el modelo lineal del "
                 f"estudio de forecasting. Es una asociación estimada, no un efecto causal.")
        t = dec["tabla"]
        h0 = int(t["semana"].max())
        capas_df = pd.concat([
            t.assign(capa="Base", valor=t["base"]),
            t.assign(capa="Folleto", valor=t["aporte_folleto"]),
            t.assign(capa="Display", valor=t["aporte_display"])])
        capas_df["semana"] = capas_df["semana"] - h0
        orden = ["Base", "Folleto", "Display"]
        area = alt.Chart(capas_df).mark_area(interpolate="monotone", opacity=.85).encode(
            x=alt.X("semana:Q", title="Semanas (0 = última semana con datos)"),
            y=alt.Y("valor:Q", stack="zero", title="Unidades por semana",
                    axis=alt.Axis(labelExpr=MILES)),
            color=alt.Color("capa:N", scale=alt.Scale(domain=orden + ["Real"],
                                                      range=["#C9D4EA", ETIQUETA_PROMO, AZUL,
                                                             TINTA])),
            order=alt.Order("orden:Q"),
            tooltip=["semana", "capa", alt.Tooltip("valor:Q", format=",.0f")]
        ).transform_calculate(orden=f"indexof({orden}, datum.capa)")
        real = alt.Chart(t.assign(semana=t["semana"] - h0, capa="Real")).mark_line(
            color=TINTA, strokeWidth=1.8, interpolate="monotone").encode(
            x="semana:Q", y="unidades:Q", color=alt.Color("capa:N"))
        st.altair_chart(_estilo(area + real, 300), width="stretch", theme=None)
    else:
        _titular(f"¿Cuánto de lo que vende {nombre.lower()} se debe a las promociones?",
                 "Falta la actividad semanal de folleto y display: añade "
                 "`data/actividad_semanal.csv` (semana, categoria, folleto, display) para ver "
                 "la descomposición histórica.")

    # 2. Eficiencia por mecanica
    ef = vp.eficiencia(cat)
    top = ef[ef["mecanica"] == "folleto_y_display"].iloc[0]
    if top["coste_por_unidad_inc"] is not None:
        _titular(f"Cada unidad extra de {nombre.lower()} cuesta {_n(top['coste_por_unidad_inc'], 2)} € "
                 f"de descuento, el {_n(top['coste_vs_precio'] * 100)} % de su precio",
                 f"Una semana de promoción con folleto y display y 15 puntos de descuento extra; "
                 f"el distribuidor asume todo el descuento.")
    filas = []
    for _, r in ef.iterrows():
        if r["coste_por_unidad_inc"] is None:
            continue
        etiqueta = NOMBRE_MECANICA[r["mecanica"]]
        filas.append({"mecánica": etiqueta,
                      "€ por unidad incremental": r["coste_por_unidad_inc"],
                      "unidades": r["unidades_inc"]})
    dfe = pd.DataFrame(filas)
    precio = float(ef["precio_eur"].iloc[0])
    # Escala legible: las mecanicas casi sin efecto (coste por unidad enorme) se recortan
    # y se indican aparte para que no aplasten al resto.
    tope = max(precio * 3, ef["coste_por_unidad_inc"].dropna().nsmallest(2).max() * 1.4)
    fuera = ef[ef["coste_por_unidad_inc"].fillna(0) > tope]
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("<div class='cp-seccion'>Coste por unidad incremental, por mecánica</div>"
                    f"<div class='cp-nota'>La línea roja es el precio habitual "
                    f"({_n(precio, 2)} €): a su derecha, cada unidad extra cuesta más "
                    f"descuento de lo que vale.</div>", unsafe_allow_html=True)
        barras = alt.Chart(dfe).mark_bar(height=24).encode(
            y=alt.Y("mecánica:N", title=None, sort=list(NOMBRE_MECANICA.values())),
            x=alt.X("€ por unidad incremental:Q", title="€ de descuento por unidad incremental",
                    scale=alt.Scale(domain=[0, tope], clamp=True)),
            color=alt.value(AZUL),
            tooltip=["mecánica", "€ por unidad incremental", "unidades"])
        linea = alt.Chart(pd.DataFrame({"x": [precio]})).mark_rule(
            color=ROJO, strokeDash=[4, 3]).encode(x="x:Q")
        st.altair_chart(_estilo(barras + linea, 170), width="stretch", theme=None)
        for _, r in fuera.iterrows():
            st.markdown(f"<div class='cp-nota'>{NOMBRE_MECANICA[r['mecanica']]}: "
                        f"apenas añade {_n(r['unidades_inc'])} unidades, así que cada una sale a "
                        f"{_n(r['coste_por_unidad_inc'], 2)} € de descuento; no cabe en el gráfico."
                        f"</div>",
                        unsafe_allow_html=True)
    with c2:
        rk = vp.ranking_eficiencia()
        rk["nombre"] = rk["categoria"].map(NOMBRE_CAT)
        rk["actual"] = rk["categoria"] == cat
        st.markdown("<div class='cp-seccion'>Dónde sale más barato vender una unidad extra</div>"
                    "<div class='cp-nota'>Descuento que cuesta cada unidad extra, en % de su "
                    "precio. Más allá de la línea roja (100 %), regalas más de lo que vale.</div>",
                    unsafe_allow_html=True)
        rk["pct_precio"] = rk["coste_vs_precio"] * 100
        rank = alt.Chart(rk.dropna(subset=["coste_vs_precio"])).mark_bar(
            height=16, cornerRadiusEnd=4).encode(
            y=alt.Y("nombre:N", sort="x", title=None),
            x=alt.X("pct_precio:Q", title="Descuento por unidad extra (% del precio)"),
            color=alt.condition("datum.actual", alt.value(AZUL), alt.value("#C9D4EA")),
            tooltip=["nombre", alt.Tooltip("pct_precio:Q", format=".0f", title="% del precio"),
                     alt.Tooltip("coste_por_unidad_inc:Q", format=".2f", title="€ por unidad extra")])
        uno = alt.Chart(pd.DataFrame({"x": [100]})).mark_rule(
            color=ROJO, strokeDash=[4, 3]).encode(x="x:Q")
        st.altair_chart(_estilo(rank + uno, 260), width="stretch", theme=None)
    st.markdown(
        "- **Para el retailer:** una promoción solo compensa si el margen de las unidades extra "
        "supera el descuento que regala; por eso la mayoría de las promociones restan beneficio.\n"
        "- **Para un fabricante CPG:** el coste por unidad incremental es el precio real de su "
        "trade spend; las categorías y mecánicas con la barra más corta son donde invertir "
        "primero.\n"
        "- **Límites:** el display apenas añade unidades en el modelo, así que su coste por "
        "unidad es muy alto; el aumento es una asociación estimada y la profundidad del "
        "descuento no se ha medido.")


@st.cache_data(show_spinner=False)
def _calidad(objetivo):
    import backtest_decision as bd
    n1 = bd.nivel_1()
    return n1, bd.nivel_2(objetivo)


def _calidad_decision():
    import backtest_decision as bd
    if not bd.disponible():
        _titular("¿Habrían funcionado las recomendaciones?",
                 "Falta `data/actividad_semanal.csv` para comprobarlo.")
        return
    objetivo = st.segmented_control("Objetivo", ["volumen", "ventas"], default="volumen",
                                    format_func={"ventas": "Ventas en €",
                                                 "volumen": "Unidades"}.get,
                                    key="cd_obj") or "volumen"
    n1, n2 = _calidad(objetivo)
    pc = n1["por_categoria"]
    t = n1["total"]

    # Nivel 1
    _titular(f"En 12 semanas que el modelo no vio, el error fue del "
             f"{_n(t['wape'] * 100, 1)} %; el aumento promocional se sobrestima",
             f"Semanas {n1['semanas'][0]}–{n1['semanas'][-1]}. En las categorías donde el aumento "
             f"es medible (supera el ruido), el aumento real fue el "
             f"{_n(t['calibracion_medibles'] * 100)} % del predicho. En el resto, el efecto de "
             f"la promoción no se distingue del ruido semanal.")
    d = pc.assign(nombre=pc["categoria"].map(NOMBRE_CAT),
                  estado=pc["aumento_medible"].map({True: "Medible", False: "Dentro del ruido"}))
    largo = pd.concat([d.assign(serie="Predicho", valor=d["aumento_predicho"]),
                       d.assign(serie="Real", valor=d["aumento_real"])])
    barras = alt.Chart(largo).mark_bar(height=10).encode(
        y=alt.Y("nombre:N", title=None, sort=alt.SortField("aumento_predicho", order="descending")),
        yOffset="serie:N",
        x=alt.X("valor:Q", title="Unidades incrementales en las semanas con folleto",
                axis=alt.Axis(labelExpr=MILES)),
        color=alt.Color("serie:N", scale=alt.Scale(domain=["Predicho", "Real"],
                                                   range=["#AFC0DD", AZUL])),
        opacity=alt.condition("datum.aumento_medible", alt.value(1), alt.value(.45)),
        tooltip=["nombre", "serie", "valor", "estado", "semanas_promo", "ruido_acumulado"])
    cero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=SUAVE).encode(x="x:Q")
    st.altair_chart(_estilo(barras + cero, 330), width="stretch", theme=None)
    st.caption("Atenuadas: categorías con pocas semanas de folleto en las que el aumento "
               "predicho no supera dos veces el ruido de las semanas sin promoción.")

    # Nivel 2
    if not n2.get("ok"):
        st.warning(n2.get("motivo"))
        return
    rc, real, rec, cal = (n2["restricciones_comunes"], n2["plan_real"],
                          n2["plan_recomendado"], n2["con_calibracion"])
    unidad = "€" if objetivo == "ventas" else "unidades"
    campo = "ventas_inc_eur" if objetivo == "ventas" else "unidades_inc"
    _titular(f"Con el mismo presupuesto, el plan recomendado mejora el objetivo en "
             f"{_n(n2['mejora_objetivo'])} {unidad} frente al plan real (simulado)",
             f"Mismas restricciones: {_n(rc['presupuesto_eur'])} € de coste, hasta "
             f"{rc['huecos_por_semana']} huecos por semana, {rc['semanas']} semanas. Corrigiendo el "
             f"aumento con la calibración medida, la mejora es de "
             f"{_n(cal['mejora_objetivo'])} {unidad}. Es una simulación con el mismo modelo, no "
             f"una medición de lo que habría vendido el retailer.")
    nombre = "ventas extra (€)" if objetivo == "ventas" else "unidades extra"
    st.dataframe(pd.DataFrame([
        {"plan": p, "promociones": d["n_promociones"], "coste (€)": round(d["coste_eur"]),
         nombre: round(d[campo]), f"{nombre}, corrigiendo el exceso de optimismo": round(c[campo])}
        for p, d, c in [("Real (retailer)", real, cal["plan_real"]),
                        ("Recomendado", rec, cal["plan_recomendado"])]]),
        hide_index=True, width="stretch")
    if objetivo == "ventas" and min(real[campo], rec[campo]) < 0:
        st.caption("Ventas extra negativas: el descuento resta más euros de los que suman las "
                   "unidades extra. Las promociones ganan volumen, pero en euros pierden.")
    st.markdown(
        "- **Nivel 1 (medido):** el modelo predice bien el volumen semanal, pero exagera el "
        "aumento de la leche, la categoría que más pesa en las recomendaciones.\n"
        "- **Nivel 2 (simulado):** con el mismo presupuesto, el plan recomendado supera al real "
        "incluso corrigiendo esa exageración.\n"
        "- **Nivel 3 (no demostrable con estos datos):** el efecto real de seguir la "
        "recomendación solo se mide con un experimento, por ejemplo tiendas piloto frente a "
        "tiendas de control.")


def pestana_prevision():
    calendario, sem_prog = _programa()
    if calendario:
        st.caption("Usando el programa de la última decisión evaluada en el espacio de decisión.")
    t1, t2, t3 = st.tabs(["Demanda", "Efecto de las promociones", "¿Funcionan las recomendaciones?"])
    with t1:
        _demanda(calendario, sem_prog)
    with t2:
        _efecto(calendario)
    with t3:
        _calidad_decision()
