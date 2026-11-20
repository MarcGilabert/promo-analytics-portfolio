import streamlit as st

import llm
from audit import historial

st.set_page_config(page_title="Copiloto de promociones", page_icon="🏷️", layout="wide",
                   initial_sidebar_state="collapsed")

from ui_decision import estilos
estilos()
_modo = ("Agente con Claude (SDK de Anthropic)" if llm.disponible()
         else "Modo determinista: enrutador por reglas, sin clave de API")
st.markdown(
    "<div style='display:flex;align-items:flex-end;justify-content:space-between;gap:16px;"
    "flex-wrap:wrap;margin-bottom:8px'><div><h1 style='margin:0;font-size:2rem;font-weight:800'>"
    "Copiloto de promociones</h1><div style='color:#5B6B86;max-width:70ch'>Decide qué "
    "promocionar con datos de Dunnhumby: cada cifra está calculada y verificada, y ninguna "
    "recomendación se ejecuta sin tu aprobación.</div></div>"
    f"<span style='font-size:.8rem;font-weight:600;color:#5B6B86;background:white;"
    f"border:1px solid #DCE3EE;border-radius:999px;padding:5px 12px'>{_modo}</span></div>",
    unsafe_allow_html=True)

if "resultado" not in st.session_state:
    st.session_state.resultado = None
if "decision" not in st.session_state:
    st.session_state.decision = None

tab_dec, tab_prev, tab_sur, tab_preg, tab_reg = st.tabs(
    ["Espacio de decisión", "Previsión", "Surtido", "Preguntar al copiloto",
     "Decisiones registradas"])

with tab_preg:
    from ui_agente import pestana_agente
    pestana_agente()

with tab_dec:
    from ui_decision import espacio_decision
    espacio_decision()

with tab_prev:
    from ui_prevision import pestana_prevision
    pestana_prevision()

with tab_sur:
    from ui_surtido import pestana_surtido
    pestana_surtido()

with tab_reg:
    from ui_decision import decisiones_registradas
    decisiones_registradas()

st.divider()
with st.expander("Historial de ejecuciones (auditoría)"):
    for h in historial(20):
        st.markdown(f"**{h['audit_id']}** · {h['decision']} · _{h['pregunta']}_")
        st.caption("run_ids: " + ", ".join(h.get("run_ids") or ["-"])
                   + " · datos: " + ", ".join([v for v in h.get("version_datos", []) if v]))

with st.sidebar:
    st.header("Herramientas del agente")
    st.caption("El agente (SDK de Anthropic, tool runner) solo elige herramientas y redacta; "
               "los cálculos son Python y cada cifra se verifica.")
    from agente import DEFINICIONES
    for nombre, (_, desc, _) in DEFINICIONES.items():
        st.markdown(f"**{nombre}** — {desc}")
    st.markdown("**decisiones_registradas** — Lista las decisiones y su estado.")
