"""Pestana Surtido: cuantos fabricantes mantener en una subcategoria y cuanto se arriesga.

Idea: quitar los fabricantes que menos venden, ver cuanto se pierde y dar un rango,
porque no se sabe con seguridad cuantos compradores se pasarian a otra marca.
Pasa por el mismo circuito que el resto (agent.ejecutar): cifras verificadas,
politicas y auditoria.
"""
import altair as alt
import pandas as pd
import streamlit as st

from agent import ejecutar
from surtido import NOMBRE_SUB, curva
from ui_decision import AMBAR, AZUL, ETIQUETA_PROMO, ROJO, TINTA, VERDE, _n
from ui_prevision import _estilo, _titular

PESIMISTA = "Pesimista (nadie se cambia)"
NOMBRE_REGLA = {"Extrapolacion": "Extrapolación", "Recomendacion robusta": "Recomendación robusta"}
OPTIMISTA = "Optimista (se cambian)"


def _pct(x, d=1):
    return _n(x * 100, d) + " %"


def pestana_surtido():
    c1, c2 = st.columns([2, 1])
    sub = c1.selectbox("Subcategoría", list(NOMBRE_SUB), format_func=NOMBRE_SUB.get, key="su_sub")
    cobertura = c2.slider("Ventas a conservar (%)", 90.0, 99.5, 98.0, step=0.5, format="%.1f", key="su_cob") / 100

    r = ejecutar(f"[Surtido] {NOMBRE_SUB[sub]}, cobertura {cobertura:.1%}",
                 {"tool": "optimize_assortment",
                  "parametros": {"subcategoria": sub, "cobertura_objetivo": cobertura}},
                 "formulario")
    salida = next((s for s in r["evidencia"] if s.get("ok")), None)
    if not salida:
        st.error(r["conclusion"])
        return
    R = salida["resultado"]
    m = R["metricas"]
    bajo = R["sensibilidad"]["0%"]["recomendado"]["pct_conservado"]
    alto = m["pct_conservado"]

    _titular(f"Con {m['grupos_mantenidos']} de {m['grupos_total']} fabricantes conservas entre el "
             f"{_pct(bajo)} y el {_pct(alto)} de las ventas de {R['subcategoria_nombre'].lower()}",
             f"Los fabricantes retirados vendían {_n(m['ventas_retiradas_eur'])} € al año. "
             f"No se sabe cuántos de sus compradores se pasarían a otra marca, así que se da un rango.")

    if alto - bajo <= 0.05:
        st.success("Rango estrecho: la decisión es segura pase lo que pase con los compradores.")
    else:
        st.warning("Rango amplio: el resultado depende de si los compradores se cambian de marca. "
                   "Antes de decidir, conviene probarlo en unas pocas tiendas.")

    c = curva(sub, 1.0)
    largo = pd.concat([c.assign(serie=OPTIMISTA, valor=c["optimizado"]),
                       c.assign(serie=PESIMISTA, valor=c["sin_transferencia"])])
    lineas = alt.Chart(largo).mark_line(point=True, strokeWidth=2.4).encode(
        x=alt.X("grupos:Q", title="Fabricantes que se mantienen", axis=alt.Axis(tickMinStep=1)),
        y=alt.Y("valor:Q", title="Ventas conservadas", axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("serie:N", scale=alt.Scale(domain=[OPTIMISTA, PESIMISTA],
                                                   range=[AZUL, "#AFC0DD"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["grupos", "serie", alt.Tooltip("valor:Q", format=".1%")])
    obj = alt.Chart(pd.DataFrame({"y": [cobertura]})).mark_rule(
        color=ROJO, strokeDash=[4, 3]).encode(y="y:Q")
    elegido = alt.Chart(pd.DataFrame({"x": [m["grupos_mantenidos"]], "y": [alto]})).mark_point(
        filled=True, size=220, shape="diamond", color=ETIQUETA_PROMO, stroke=TINTA).encode(
        x="x:Q", y="y:Q")
    st.altair_chart(_estilo(lineas + obj + elegido, 300), width="stretch", theme=None)
    st.caption("La realidad está entre las dos líneas. Donde se juntan, quitar fabricantes es "
               "seguro; donde se separan, hay riesgo.")

    filas = [{"fabricante": f"Fabricante {g['fabricante']}" + (" (marca propia)" if g["marca_propia"] else ""),
              "decisión": "Mantener" if g["mantener"] else "Retirar",
              "ventas al año (€)": round(g["ventas_a1"]),
              "ventas de clientes que ya compran otra marca": f"{g['transferencia']:.0%}"}
             for g in R["grupos"]]
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
    st.caption("Se mantienen los que más venden, salvo que haga falta dejar al menos una marca "
               "propia del distribuidor: por eso puede quedarse una marca propia que vende menos "
               "que otra retirada.")

    color = {"pass": VERDE, "warn": AMBAR, "block": ROJO}
    chips = "".join(f"<span class='cp-chip' title='{msg}'><i style='background:{color[e]}'></i>"
                    f"{NOMBRE_REGLA.get(rg, rg)}</span>" for rg, e, msg in r["veredictos"])
    st.markdown(f"<div class='cp-gob'>{chips}</div><div class='cp-nota'>"
                f"{sum(c['verificado'] for c in r['claims'])} de {len(r['claims'])} cifras "
                f"verificadas · auditoría {r['audit_id']}</div>", unsafe_allow_html=True)
    with st.expander("Cómo funciona, en tres frases"):
        st.markdown(
            "1. Se ordenan los fabricantes por ventas y se quitan los pequeños hasta llegar a las "
            "ventas que quieres conservar, dejando siempre al menos una marca propia del "
            "distribuidor.\n"
            "2. Lo que vendían los retirados no se pierde del todo: parte de sus compradores ya "
            "compra otras marcas de la subcategoría y probablemente se pasaría.\n"
            "3. Como eso no está probado, el resultado es un rango entre «nadie se cambia» y "
            "«se cambian todos los que ya compran otra marca». Se conservan ventas, no beneficio: "
            "no hay márgenes por fabricante.")
