"""Pestana Preguntar al copiloto: chat con el agente (SDK de Anthropic, tool runner).

Cada respuesta muestra que herramientas uso el agente, si sus cifras se han
verificado y, si la redaccion del agente no paso los controles, que se ha
entregado en su lugar el texto verificado de las herramientas.
"""
import html

import streamlit as st

import llm
from agente import responder
from ui_decision import AMBAR, ROJO, VERDE

COLOR = {"ENTREGAR": VERDE, "ENTREGAR_CON_AVISO": AMBAR, "BLOQUEADA": ROJO,
         "pass": VERDE, "warn": AMBAR, "block": ROJO}
ESTADO = {"ENTREGAR": "Verificada", "ENTREGAR_CON_AVISO": "Verificada con avisos",
          "BLOQUEADA": "Bloqueada"}
NOMBRE = {"prevision_demanda": "Previsión", "evaluar_promocion": "Efecto de una promoción",
          "programa_promocional": "Programa promocional", "recomendar_decision": "Recomendación",
          "surtido": "Surtido", "decisiones_registradas": "Decisiones registradas"}
EJEMPLOS = [
    "¿Cuánto venderé de leche la próxima semana?",
    "¿Qué promociono el próximo mes con 1.000 € para vender más unidades?",
    "¿Cuántos fabricantes de pretzels necesito para conservar el 98 % de las ventas?",
    "¿Qué decisiones hay pendientes de aprobación?",
]


def _chip(texto, estado):
    return (f"<span class='cp-chip'><i style='background:{COLOR.get(estado, AMBAR)}'></i>"
            f"{html.escape(texto)}</span>")


def _mostrar(r):
    st.markdown(r["respuesta"])
    chips = [_chip(ESTADO[r["decision"]], r["decision"])]
    chips += [_chip(NOMBRE.get(c["herramienta"], c["herramienta"]), c["decision"] or "pass")
              for c in r["llamadas"]]
    st.markdown(f"<div class='cp-gob'>{''.join(chips)}</div>", unsafe_allow_html=True)
    if r.get("redaccion_original"):
        st.caption("La redacción del agente no pasó los controles; se muestra el texto "
                   "verificado de las herramientas.")
    with st.expander("Cómo se ha comprobado"):
        for c in r["llamadas"]:
            st.markdown(f"**{NOMBRE.get(c['herramienta'], c['herramienta'])}** · "
                        f"`{c['parametros']}` · auditoría `{c['audit_id'] or '-'}`")
            for regla, estado, msg in c["veredictos"]:
                st.markdown(f"<div class='cp-nota'>{_chip(regla, estado)} {html.escape(msg)}</div>",
                            unsafe_allow_html=True)
        st.markdown("**Respuesta final**")
        for regla, estado, msg in r["veredictos"]:
            st.markdown(f"<div class='cp-nota'>{_chip(regla, estado)} {html.escape(msg)}</div>",
                        unsafe_allow_html=True)
        if r.get("redaccion_original"):
            st.markdown(f"<div class='cp-nota'>Redacción descartada: "
                        f"{html.escape(r['redaccion_original'])}</div>", unsafe_allow_html=True)
        st.caption(f"Modo {r['modo']} · auditoría {r['audit_id']}")


def pestana_agente():
    if llm.disponible():
        st.caption("Un agente (SDK de Anthropic) elige y encadena las herramientas; Python "
                   "calcula y cada cifra de la respuesta se comprueba antes de mostrarla.")
    else:
        st.caption("Sin clave de API responde el enrutador por reglas: una herramienta por "
                   "pregunta, con los mismos controles. Con clave, responde el agente.")
    chat = st.session_state.setdefault("chat", [])

    cols = st.columns(len(EJEMPLOS))
    pulsado = None
    for col, ej in zip(cols, EJEMPLOS):
        if col.button(ej, key=f"ej_{ej}", width="stretch"):
            pulsado = ej

    for m in chat:
        with st.chat_message(m["rol"]):
            _mostrar(m["r"]) if m["rol"] == "assistant" else st.markdown(m["texto"])

    pregunta = st.chat_input("Pregunta sobre demanda, promociones, surtido o decisiones") or pulsado
    if pregunta:
        historial = [{"role": m["rol"], "content": m["r"]["respuesta"] if m["rol"] == "assistant"
                      else m["texto"]} for m in chat[-6:]]
        with st.chat_message("user"):
            st.markdown(pregunta)
        with st.spinner("Analizando…"):
            r = responder(pregunta, historial)
        chat += [{"rol": "user", "texto": pregunta}, {"rol": "assistant", "r": r}]
        st.rerun()
    if chat and st.button("Borrar conversación"):
        st.session_state.chat = []
        st.rerun()
