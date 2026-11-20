"""Espacio de decision de la app: plantear, comparar, entender y decidir.

Usa exactamente el mismo circuito que el agente (agent.ejecutar): motor de
decision, afirmaciones verificadas, siete politicas, auditoria y registro.
Las cifras de las tarjetas salen de las afirmaciones verificadas, no del texto.
"""
import html

import altair as alt
import pandas as pd
import streamlit as st

import decision_record
from agent import ejecutar
from claims import _palanca
from tools import MECANICAS, categorias_disponibles

# ---- Sistema visual ----------------------------------------------------------
TINTA, SUAVE, LINEA = "#172033", "#5B6B86", "#DCE3EE"
AZUL, ETIQUETA_PROMO = "#2B59C3", "#FFD23F"
VERDE, AMBAR, ROJO = "#12A37A", "#E8890C", "#D64545"

NOMBRE_CAT = {
    "BAG SNACKS": "Snacks", "BAKED BREAD/BUNS/ROLLS": "Pan y bollería", "CHEESE": "Queso",
    "FLUID MILK PRODUCTS": "Leche", "FRZN MEAT/MEAT DINNERS": "Carne congelada",
    "SOFT DRINKS": "Refrescos", "SOUP": "Sopa", "VEGETABLES - SHELF STABLE": "Verdura en conserva",
}
ESTADO_POLITICAS = {
    "ENTREGAR": ("Lista para aprobar", VERDE),
    "ENTREGAR_CON_AVISO": ("Lista para aprobar, con avisos", AMBAR),
    "BLOQUEADA": ("Bloqueada por las políticas", ROJO),
}
PALANCAS = {
    "presupuesto_eur": "Presupuesto",
    "mecanica": "Mecánica",
    "max_promos_categoria": "Promociones por categoría",
    "max_promos_semana": "Huecos de folleto por semana",
}
NOMBRE_MECANICA = {"folleto_y_display": "Folleto y display", "folleto": "Solo folleto",
                   "display": "Solo display"}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
html, body, .stApp, .stApp button, .stApp input, .stApp textarea, .stApp p, .stApp label,
.stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp div {{
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
}}
.stApp [data-testid="stIconMaterial"], .stApp .material-symbols-rounded {{
  font-family: 'Material Symbols Rounded' !important;
}}
.block-container {{ padding-top: 2.2rem; max-width: 1320px; }}
h1, h2, h3 {{ letter-spacing: -0.02em; color: {TINTA}; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 22px; border-bottom: 1px solid {LINEA};
  margin-bottom: 18px; }}
.stTabs button[role="tab"] {{ background: transparent !important; padding: 8px 0 !important;
  border-bottom: 3px solid transparent !important; }}
.stTabs button[role="tab"] p {{ font-weight: 600; color: {SUAVE}; font-size: .95rem; }}
.stTabs button[role="tab"][aria-selected="true"] {{ border-bottom-color: {AZUL} !important; }}
.stTabs button[role="tab"][aria-selected="true"] p {{ color: {TINTA}; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

.cp-veredicto {{ display: flex; gap: 18px; align-items: flex-start; margin: 4px 0 18px; }}
.cp-sello {{ flex: none; width: 54px; height: 54px; border-radius: 16px; display: grid;
  place-items: center; color: white; font-size: 26px; font-weight: 800; }}
.cp-titular {{ font-size: 1.55rem; font-weight: 800; line-height: 1.2; color: {TINTA};
  letter-spacing: -0.02em; margin: 0 0 4px; }}
.cp-estado {{ font-size: .92rem; font-weight: 600; }}

.cp-kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;
  margin-bottom: 18px; }}
.cp-kpi {{ background: white; border: 1px solid {LINEA}; border-radius: 14px; padding: 14px 16px; }}
.cp-kpi.principal {{ background: {TINTA}; border-color: {TINTA}; }}
.cp-kpi.principal .cp-kpi-n, .cp-kpi.principal .cp-kpi-t {{ color: white; }}
.cp-kpi.principal .cp-kpi-d {{ color: #C9D4EA; }}
.cp-kpi-t {{ font-size: .82rem; color: {SUAVE}; font-weight: 600; display: flex;
  justify-content: space-between; align-items: flex-start; gap: 8px; min-height: 2.3em; }}
.cp-kpi-n {{ font-size: 1.75rem; font-weight: 800; color: {TINTA}; letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums; margin: 2px 0; }}
.cp-kpi-d {{ font-size: .8rem; color: {SUAVE}; }}
.cp-ev {{ flex: none; font-size: .68rem; font-weight: 700; padding: 2px 8px;
  border-radius: 999px; white-space: nowrap; }}
.cp-ev.estimado {{ background: #E3ECFF; color: {AZUL}; }}
.cp-ev.supuesto {{ background: #FFF1D6; color: #9A5B00; }}

.cp-cal {{ background: white; border: 1px solid {LINEA}; border-radius: 14px; padding: 14px 16px 10px;
  margin-bottom: 18px; overflow-x: auto; }}
.cp-cal table {{ border-collapse: separate; border-spacing: 6px; width: 100%; border: none;
  margin: 0; }}
.cp-cal table tr, .cp-cal table th, .cp-cal table td {{ border: none !important;
  background: transparent !important; padding: 0; }}
.cp-cal th {{ padding-bottom: 2px !important; font-size: .78rem; color: {SUAVE}; font-weight: 600; text-align: center; }}
.cp-cal td.cat {{ font-size: .86rem; font-weight: 600; color: {TINTA}; white-space: nowrap;
  padding-right: 8px; }}
.cp-celda {{ height: 40px; border-radius: 10px; background: #F1F4F9; position: relative;
  display: grid; place-items: center; font-size: .78rem; font-weight: 700;
  font-variant-numeric: tabular-nums; }}
.cp-celda.promo {{ background: {ETIQUETA_PROMO}; color: {TINTA};
  clip-path: polygon(12px 0, 100% 0, 100% 100%, 12px 100%, 0 50%); padding-left: 8px; }}
.cp-celda.actual::after {{ content: ""; position: absolute; top: 6px; right: 7px; width: 8px;
  height: 8px; border-radius: 50%; border: 2px solid {TINTA}; }}
.cp-leyenda {{ display: flex; gap: 18px; font-size: .78rem; color: {SUAVE}; margin-top: 6px; }}
.cp-leyenda span::before {{ content: ""; display: inline-block; width: 12px; height: 12px;
  border-radius: 3px; margin-right: 6px; vertical-align: -1px; }}
.cp-leyenda .l-promo::before {{ background: {ETIQUETA_PROMO}; }}
.cp-leyenda .l-actual::before {{ border: 2px solid {TINTA}; border-radius: 50%;
  width: 8px; height: 8px; }}

.cp-razon {{ display: grid; grid-template-columns: 150px 1fr; gap: 0; background: white;
  border: 1px solid {LINEA}; border-radius: 14px; overflow: hidden; margin-bottom: 18px; }}
.cp-razon dt {{ padding: 12px 16px; font-weight: 700; font-size: .88rem; color: {TINTA};
  background: #F8FAFD; border-top: 1px solid {LINEA}; }}
.cp-razon dd {{ margin: 0; padding: 12px 16px; font-size: .92rem; color: #2B3850;
  border-top: 1px solid {LINEA}; line-height: 1.5; }}
.cp-razon dt:first-of-type, .cp-razon dd:first-of-type {{ border-top: none; }}
.cp-razon dd.riesgo {{ color: #8A4B00; }}

.cp-gob {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 6px; }}
.cp-chip {{ font-size: .8rem; font-weight: 600; padding: 5px 12px 5px 10px; border-radius: 999px;
  background: white; border: 1px solid {LINEA}; color: {TINTA}; }}
.cp-chip i {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  margin-right: 7px; vertical-align: 1px; }}
.cp-nota {{ font-size: .8rem; color: {SUAVE}; }}
.cp-vacio {{ border: 2px dashed {LINEA}; border-radius: 18px; padding: 40px 32px; text-align: left; }}
.cp-vacio h3 {{ margin: 0 0 6px; }}
.cp-vacio p {{ color: {SUAVE}; max-width: 56ch; margin: 0; }}
.stApp [class*="st-key-ej_"] button {{ justify-content: flex-start; border-radius: 10px;
  border: 1px dashed #B9C6DD; background: transparent; padding: 4px 12px; min-height: 0; }}
.stApp [class*="st-key-ej_"] button p {{ font-size: .86rem; color: {AZUL}; font-weight: 600; }}
.stApp [class*="st-key-ej_"] {{ margin-bottom: -6px; }}
.cp-seccion {{ font-size: 1.05rem; font-weight: 700; color: {TINTA}; margin: 6px 0 10px; }}
@media (max-width: 900px) {{
  .cp-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .cp-razon {{ grid-template-columns: 1fr; }}
}}
</style>
"""


def estilos():
    st.markdown(CSS, unsafe_allow_html=True)


def _n(x, dec=0):
    """Numero con separador de miles espanol y signo menos tipografico."""
    if x is None:
        return "—"
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if x < 0 else "") + s


def _pct(x, dec=1):
    return ("+" if x > 0 else "") + _n(x, dec)


def _delta(x, unidad=""):
    if x is None:
        return ""
    return ("+" if x > 0 else "") + _n(x) + (f" {unidad}" if unidad else "")


CORTO_PALANCA = {
    "presupuesto_eur": lambda v: f"presupuesto {_n(v)} €",
    "mecanica": lambda v: NOMBRE_MECANICA[v].lower(),
    "max_promos_categoria": lambda v: f"{v} promos/categoría",
    "max_promos_semana": lambda v: f"{v} huecos/semana",
    "roi_minimo": lambda v: f"ROI mín. {v}",
    "max_descuento_total_eur": lambda v: f"tope {_n(v)} €",
}


def _etiqueta_corta(e):
    if e["nombre"] in ("actual", "optimizada"):
        return _nombre_escenario(e)
    num = e["nombre"].split("_")[-1] if "_" in e["nombre"] else ""
    cambios = ", ".join(CORTO_PALANCA[k](v) for k, v in e.get("cambios", {}).items())
    return f"Alt.{(' ' + num) if num else ''}: {cambios}"


def _nombre_escenario(e):
    if e["nombre"] == "actual":
        return "Plan actual"
    if e["nombre"] == "optimizada":
        return "Óptimo"
    cambios = e.get("cambios", {})
    return "Alternativa: " + ", ".join(_palanca(k, v) for k, v in cambios.items())


# ---- A. Plantear la decision -----------------------------------------------------

FORM_DEFECTO = {"f_obj": "ventas", "f_pres": 1000, "f_sem": 4,
                "f_mec": "folleto_y_display", "f_huecos": 3, "f_porcat": 2, "f_tope": 0,
                "alt1_p": "(ninguna)", "alt2_p": "(ninguna)"}
EJEMPLOS = {
    "Ventas con el presupuesto base": {},
    "Volumen y dos alternativas": {"f_obj": "volumen", "alt1_p": "max_promos_categoria",
                                   "alt1_v": 4, "alt2_p": "mecanica", "alt2_v": "folleto"},
    "¿Y si duplico el presupuesto?": {"f_obj": "ventas", "alt1_p": "presupuesto_eur",
                                      "alt1_v": 2000},
}


def _cargar_ejemplo(nombre):
    for k in ("alt1_v", "alt2_v"):
        st.session_state.pop(k, None)
    valores = {**FORM_DEFECTO, **EJEMPLOS[nombre]}
    st.session_state.update(valores)
    for i in (1, 2):                      # la palanca del ejemplo ya trae su valor
        st.session_state[f"_alt{i}_ultima"] = valores[f"alt{i}_p"]


def _valor(key, defecto):
    """Valor por defecto solo si la clave no esta ya en la sesion (evita avisos)."""
    return {} if key in st.session_state else {"value": defecto}


def _alternativa(i):
    palanca = st.selectbox(f"Alternativa {i}", ["(ninguna)"] + list(PALANCAS),
                           format_func=lambda k: PALANCAS.get(k, "Sin alternativa"),
                           key=f"alt{i}_p")
    k = f"alt{i}_v"
    if palanca == "(ninguna)":
        st.session_state.pop(k, None)
        return None
    if st.session_state.get(f"_alt{i}_ultima") != palanca:     # cambia la palanca
        st.session_state.pop(k, None)
        st.session_state[f"_alt{i}_ultima"] = palanca
    if palanca == "presupuesto_eur":
        v = float(st.number_input("Nuevo presupuesto (€)", 1, 1_000_000, step=100, key=k,
                                  **_valor(k, st.session_state.f_pres * 2)))
    elif palanca == "mecanica":
        if k not in st.session_state:
            st.session_state[k] = "folleto"
        v = st.selectbox("Nueva mecánica", list(MECANICAS), format_func=NOMBRE_MECANICA.get,
                         key=k)
    else:
        v = int(st.number_input("Nuevo valor", 1, 12, key=k, **_valor(k, 4)))
    return {palanca: v}


def _formulario():
    for k, v in FORM_DEFECTO.items():
        st.session_state.setdefault(k, v)
    st.markdown("<div class='cp-nota' style='margin-bottom:6px'>Empieza por un ejemplo</div>",
                unsafe_allow_html=True)
    for nombre in EJEMPLOS:
        st.button(nombre, key=f"ej_{nombre}", on_click=_cargar_ejemplo, args=(nombre,),
                  width="stretch")
    with st.container(border=True):
        st.markdown("<div class='cp-seccion'>Plantea la decisión</div>", unsafe_allow_html=True)
        objetivo = st.segmented_control(
            "Qué quieres maximizar", ["ventas", "volumen"], key="f_obj",
            format_func={"ventas": "Ventas en €", "volumen": "Unidades"}.get,
            help="El beneficio no se optimiza: el dataset no tiene márgenes. Se muestra como "
                 "escenario ilustrativo.") or "ventas"
        c1, c2 = st.columns(2)
        presupuesto = float(c1.number_input("Presupuesto (€)", 1, 1_000_000, step=100,
                                            key="f_pres"))
        semanas = int(c2.number_input("Semanas", 1, 12, key="f_sem"))
        mecanica = st.selectbox("Mecánica", list(MECANICAS), format_func=NOMBRE_MECANICA.get,
                                key="f_mec")
        with st.expander("Restricciones"):
            huecos = int(st.number_input("Huecos de folleto por semana", 1, 8, key="f_huecos"))
            por_cat = int(st.number_input("Promociones por categoría", 1, 12, key="f_porcat"))
            tope = st.number_input("Tope de descuento total (€, 0 = sin tope)", 0, 1_000_000,
                                   step=100, key="f_tope")
        with st.expander("Plan actual del retailer"):
            st.caption("Déjalo vacío para comparar con la actividad promocional media.")
            plan = st.data_editor(
                pd.DataFrame({"semana": pd.Series(dtype="int"),
                              "categoria": pd.Series(dtype="str")}),
                num_rows="dynamic", width="stretch", key="plan_actual",
                column_config={
                    "semana": st.column_config.NumberColumn("Semana", min_value=1,
                                                            max_value=12, step=1),
                    "categoria": st.column_config.SelectboxColumn(
                        "Categoría", options=categorias_disponibles()),
                })
        with st.expander("Alternativas a comparar",
                         expanded=st.session_state.alt1_p != "(ninguna)"):
            alternativas = [a for a in (_alternativa(1), _alternativa(2)) if a]
        enviar = st.button("Evaluar decisión", type="primary", width="stretch")

    if enviar:
        actual = [{"semana": int(r.semana), "categoria": r.categoria}
                  for r in plan.dropna().itertuples()]
        params = {"presupuesto_eur": presupuesto, "semanas": semanas,
                  "objetivo": objetivo, "mecanica": mecanica, "max_promos_semana": huecos,
                  "max_promos_categoria": por_cat, "max_descuento_total_eur": tope or None,
                  "calendario_actual": actual or None, "alternativa": alternativas or None}
        pregunta = (f"[Espacio de decisión] {objetivo}, {presupuesto:.0f} €, {semanas} sem")
        st.session_state.decision = ejecutar(
            pregunta, {"tool": "recommend_promo_decision", "parametros": params}, "formulario")


# ---- B-D. Resultado ---------------------------------------------------------------

def _veredicto(r, salida):
    texto, color = ESTADO_POLITICAS[r["decision"]]
    sello = {"ENTREGAR": "✓", "ENTREGAR_CON_AVISO": "!", "BLOQUEADA": "×"}[r["decision"]]
    if salida:
        rec = salida["resultado"]["recomendacion"]
        esc = next(e for e in salida["resultado"]["escenarios"]
                   if e["nombre"] == rec["escenario"])
        n = rec["metricas"]["n_promociones"]
        titular = ("No promocionar" if n == 0 else
                   f"{_nombre_escenario(esc)}: {n} {'promoción' if n == 1 else 'promociones'} "
                   f"en {salida['parametros']['horizonte']} semanas")
    else:
        titular = "No hay recomendación que respalde"
    st.markdown(
        f"<div class='cp-veredicto'><div class='cp-sello' style='background:{color}'>{sello}"
        f"</div><div><p class='cp-titular'>{html.escape(titular)}</p>"
        f"<div class='cp-estado' style='color:{color}'>{texto} · propuesta pendiente de "
        f"aprobación</div></div></div>", unsafe_allow_html=True)


def _kpis(r, salida):
    v = {c["metrica"]: c for c in r["claims"] if c["verificado"]}
    esc = {e["nombre"]: e for e in salida["resultado"]["escenarios"]}
    rec = esc[salida["resultado"]["recomendacion"]["escenario"]]
    act = esc["actual"]["metricas"]
    m = rec["metricas"]
    principal = salida["parametros"]["objetivo"]

    def tarjeta(titulo, clave, valor, unidad, actual_v, evidencia, es_principal=False,
                pie=None):
        d = None if actual_v is None or valor is None else valor - actual_v
        pie = pie or (f"{_delta(d, unidad)} frente al plan actual" if d is not None else "")
        return (f"<div class='cp-kpi{' principal' if es_principal else ''}'>"
                f"<div class='cp-kpi-t'>{titulo}<span class='cp-ev {evidencia}'>{evidencia}"
                f"</span></div><div class='cp-kpi-n'"
                f"{' style=\'color:' + ROJO + '\'' if valor is not None and valor < 0 and not es_principal else ''}>"
                f"{_n(valor)}"
                f"{' ' + unidad if unidad else ''}</div><div class='cp-kpi-d'>{pie}</div></div>")

    ventas = v.get("decision_ventas", {}).get("valor")
    unidades = v.get("decision_unidades", {}).get("valor")
    coste = v.get("decision_coste", {}).get("valor")
    b = {k: v.get(f"decision_beneficio_{k}", {}).get("valor") for k in ("bajo", "base", "alto")}
    pie_b = (f"de {_n(b['bajo'])} a {_n(b['alto'])} € según el margen" if b["bajo"] is not None
             else "sin promociones")
    html_k = "<div class='cp-kpis'>" + "".join([
        tarjeta("Ventas incrementales", "ventas", ventas, "€",
                act["ventas_incrementales_eur"], "estimado", principal == "ventas"),
        tarjeta("Unidades incrementales", "unidades", unidades, "",
                act["unidades_incrementales"], "estimado", principal == "volumen"),
        tarjeta("Coste para el retailer", "coste", coste, "€", act["coste_eur"], "supuesto"),
        tarjeta("Beneficio ilustrativo", "beneficio", b["base"], "€", None, "supuesto",
                pie=pie_b),
    ]) + "</div>"
    st.markdown(html_k, unsafe_allow_html=True)


def _calendario(salida):
    rec = salida["resultado"]["recomendacion"]
    semanas = salida["parametros"]["horizonte"]
    actual = next(e for e in salida["resultado"]["escenarios"] if e["nombre"] == "actual")
    promo = {(r["semana"], r["categoria"]): r["unidades_inc"] for r in rec["calendario"]}
    en_actual = {(r["semana"], r["categoria"]) for r in actual["calendario"]}
    filas = []
    for cat in categorias_disponibles():
        celdas = []
        for w in range(1, semanas + 1):
            clases = ["cp-celda"]
            txt = ""
            if (w, cat) in promo:
                clases.append("promo")
                txt = f"+{_n(promo[(w, cat)])} ud"
            if (w, cat) in en_actual:
                clases.append("actual")
            celdas.append(f"<td><div class='{' '.join(clases)}' title='{html.escape(cat)}, "
                          f"semana {w}'>{txt}</div></td>")
        filas.append(f"<tr><td class='cat'>{NOMBRE_CAT.get(cat, cat)}</td>{''.join(celdas)}</tr>")
    cab = "".join(f"<th>Semana {w}</th>" for w in range(1, semanas + 1))
    st.markdown(
        f"<div class='cp-cal'><div class='cp-seccion'>Calendario recomendado</div>"
        f"<table><tr><th></th>{cab}</tr>{''.join(filas)}</table>"
        f"<div class='cp-leyenda'><span class='l-promo'>Promoción recomendada (unidades "
        f"incrementales estimadas)</span><span class='l-actual'>En el plan actual</span></div>"
        f"</div>", unsafe_allow_html=True)


def _razonamiento(r, salida):
    R = salida["resultado"]
    meta = salida["metadata"]
    v = {c["metrica"]: c["valor"] for c in r["claims"] if c["verificado"]}
    unidad = "€" if salida["parametros"]["objetivo"] == "ventas" else "unidades"
    filas = []
    pq = R["por_que"]
    porque = f"Es el escenario viable con más {meta['objetivo_descripcion']}"
    if pq["ventaja_vs_segundo"] is not None and pq["segundo"] and pq["segundo"] != "actual":
        seg = next(e for e in R["escenarios"] if e["nombre"] == pq["segundo"])
        porque += (f": supera a «{_nombre_escenario(seg)}» en "
                   f"{_n(pq['ventaja_vs_segundo'])} {unidad}")
    if "decision_ventaja_actual" in v:
        porque += f" y al plan actual en {_delta(v['decision_ventaja_actual'], unidad)}"
    filas.append(("Por qué gana", porque + ".", ""))
    if R["compromisos"]:
        nombres = {"unidades_incrementales": ("unidades", ""), "ventas_incrementales_eur":
                   ("ventas", "€"), "coste_eur": ("coste", "€"), "beneficio_eur":
                   ("beneficio ilustrativo", "€"), "roi": ("ROI ilustrativo", ""),
                   "descuento_total_eur": ("descuento total", "€")}
        partes = [f"{nombres[c['metrica']][0]} {_delta(c['diferencia'], nombres[c['metrica']][1])}"
                  for c in R["compromisos"]]
        filas.append(("A cambio de", "Frente al plan actual: " + ", ".join(partes) + ".", ""))
    avisos = [msg for _, est, msg in r["veredictos"] if est == "warn"]
    for clave, nombre in NOMBRE_CAT.items():
        avisos = [a.replace(clave, nombre) for a in avisos]
    if avisos:
        filas.append(("Riesgos", " ".join(avisos), "riesgo"))
    if "decision_margen_critico" in v:
        filas.append(("Supuesto crítico",
                      f"Con el margen supuesto el programa pierde dinero; necesitaría "
                      f"{v['decision_margen_critico']} puntos más de margen para no perder.", ""))
    filas.append(("Qué no sabemos",
                  "El beneficio y el ROI dependen de márgenes supuestos; la relación entre "
                  "promoción y ventas es asociación, no causalidad.", ""))
    cuerpo = "".join(f"<dt>{t}</dt><dd class='{c}'>{html.escape(d)}</dd>" for t, d, c in filas)
    st.markdown(f"<dl class='cp-razon'>{cuerpo}</dl>", unsafe_allow_html=True)


def _graficos(salida):
    R = salida["resultado"]
    rec_n = R["recomendacion"]["escenario"]
    rangos = R["robustez"]["modelo"].get("rango_por_escenario", {})
    unidad = "€" if salida["parametros"]["objetivo"] == "ventas" else "unidades"
    filas, margen = [], []
    for e in R["escenarios"]:
        nombre = _etiqueta_corta(e)
        lo, hi = rangos.get(e["nombre"], [None, None])
        filas.append({"escenario": nombre, "valor": e["valor_objetivo"], "lo": lo, "hi": hi,
                      "tipo": "Recomendado" if e["nombre"] == rec_n
                      else ("No viable" if not e["viable"] else "Otro escenario")})
        b = e["metricas"]["beneficio_ilustrativo_eur"]
        margen.append({"escenario": nombre, "bajo": b["bajo"], "base": b["base"],
                       "alto": b["alto"],
                       "tipo": "Recomendado" if e["nombre"] == rec_n else "Otro escenario"})
    df, dm = pd.DataFrame(filas), pd.DataFrame(margen)
    color = alt.Color("tipo:N", legend=None, scale=alt.Scale(
        domain=["Recomendado", "Otro escenario", "No viable"], range=[AZUL, "#AFC0DD", "#E3E7EF"]))
    eje_y = alt.Y("escenario:N", sort=None, title=None,
                  axis=alt.Axis(labelLimit=190, labelFontSize=12, labelColor=TINTA))
    miles = "replace(format(datum.value, ',.0f'), ',', '.')"
    barras = alt.Chart(df).mark_bar(cornerRadiusEnd=6, height=26).encode(
        x=alt.X("valor:Q", title=f"Objetivo ({unidad})", axis=alt.Axis(labelExpr=miles)),
        y=eje_y, color=color,
        tooltip=["escenario", "valor", "lo", "hi"])
    error = alt.Chart(df.dropna()).mark_rule(color=TINTA, strokeWidth=2).encode(
        x="lo:Q", x2="hi:Q", y=eje_y)
    cero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=SUAVE, strokeDash=[3, 3]).encode(x="x:Q")
    g1 = (barras + error + cero).properties(height=max(170, 62 * len(df)))

    rango = alt.Chart(dm).mark_rule(strokeWidth=6, strokeCap="round", opacity=.35).encode(
        x=alt.X("bajo:Q", title="Beneficio ilustrativo (€)", axis=alt.Axis(labelExpr=miles)),
        x2="alto:Q",
        y=eje_y, color=alt.Color("tipo:N", legend=None, scale=alt.Scale(
            domain=["Recomendado", "Otro escenario"], range=[AZUL, "#7F93B8"])))
    punto = alt.Chart(dm).mark_point(filled=True, size=110).encode(
        x="base:Q", y=eje_y, color=alt.Color("tipo:N", legend=None, scale=alt.Scale(
            domain=["Recomendado", "Otro escenario"], range=[AZUL, "#7F93B8"])),
        tooltip=["escenario", "bajo", "base", "alto"])
    cero_r = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=ROJO, strokeDash=[4, 3]).encode(x="x:Q")
    g2 = (rango + punto + cero_r).properties(height=max(170, 62 * len(dm)))

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("<div class='cp-seccion'>Escenarios en el objetivo</div>"
                    "<div class='cp-nota'>La línea marca el rango si el volumen promocional "
                    "fuera un WAPE menor o mayor de lo previsto.</div>", unsafe_allow_html=True)
        st.altair_chart(g1.configure(font="Plus Jakarta Sans").configure_view(stroke=None)
            .configure_axis(gridColor="#EEF2F7", domain=False, titleColor=SUAVE,
                            labelColor=SUAVE, titleFontWeight=600, labelFontSize=12,
                            titleFontSize=12), width="stretch", theme=None)
    with c2:
        st.markdown("<div class='cp-seccion'>Beneficio según el margen supuesto</div>"
                    "<div class='cp-nota'>Punto: margen base. A la izquierda de la línea roja, "
                    "el escenario pierde dinero.</div>", unsafe_allow_html=True)
        st.altair_chart(g2.configure(font="Plus Jakarta Sans").configure_view(stroke=None)
            .configure_axis(gridColor="#EEF2F7", domain=False, titleColor=SUAVE,
                            labelColor=SUAVE, titleFontWeight=600, labelFontSize=12,
                            titleFontSize=12), width="stretch", theme=None)


NOMBRE_REGLA = {"Extrapolacion": "Extrapolación", "Recomendacion robusta": "Recomendación robusta"}


def _gobierno(r):
    color = {"pass": VERDE, "warn": AMBAR, "block": ROJO}
    chips = "".join(f"<span class='cp-chip' title='{html.escape(msg)}'><i style='background:"
                    f"{color[est]}'></i>{html.escape(NOMBRE_REGLA.get(regla, regla))}</span>"
                    for regla, est, msg in r["veredictos"])
    n_ok = sum(1 for c in r["claims"] if c["verificado"])
    st.markdown(f"<div class='cp-seccion'>Controles de gobierno</div><div class='cp-gob'>{chips}"
                f"</div><div class='cp-nota'>{n_ok} de {len(r['claims'])} cifras verificadas "
                f"contra su ejecución · auditoría {r['audit_id']}</div>", unsafe_allow_html=True)
    with st.expander("Ver el detalle de cada control y las cifras verificadas"):
        for regla, est, msg in r["veredictos"]:
            st.markdown(f"**{regla}:** {msg}")
        if r["claims"]:
            st.dataframe([{"cifra": c["metrica"], "valor": str(c["valor"]), "unidad": c["unidad"],
                           "verificada": "sí" if c["verificado"] else "NO"}
                          for c in r["claims"]], hide_index=True, width="stretch")


def _decidir(decision_id, decision_politicas):
    reg = decision_record.leer(decision_id)
    with st.container(border=True):
        st.markdown("<div class='cp-seccion'>Tu decisión</div>", unsafe_allow_html=True)
        if reg["estado"] in ("aprobada", "rechazada"):
            ultimo = reg["historial"][-1]
            (st.success if reg["estado"] == "aprobada" else st.info)(
                f"Decisión {reg['estado']} por {ultimo['usuario']}: {ultimo['motivo']}")
            return
        if reg["estado"] == "en_revision":
            st.caption("Guardada para revisión. Puedes aprobarla o rechazarla.")
        c1, c2 = st.columns([1, 2])
        usuario = c1.text_input("Quién decide", key=f"u_{decision_id}")
        motivo = c2.text_input("Motivo", key=f"m_{decision_id}",
                               placeholder="Por ejemplo: margen confirmado por finanzas")
        reconocer = False
        if decision_politicas == "ENTREGAR_CON_AVISO":
            reconocer = st.checkbox("He leído los riesgos y los acepto", key=f"r_{decision_id}")
        b1, b2, b3 = st.columns(3)
        accion = None
        if b1.button("Aprobar", key=f"a_{decision_id}", type="primary", width="stretch",
                     disabled=decision_politicas == "BLOQUEADA"):
            accion = "aprobada"
        if b2.button("Guardar para revisión", key=f"v_{decision_id}", width="stretch",
                     disabled=reg["estado"] != "propuesta"):
            accion = "en_revision"
        if b3.button("Rechazar", key=f"x_{decision_id}", width="stretch"):
            accion = "rechazada"
        st.markdown(f"<div class='cp-nota'>Registro {decision_id} · sellado con huella "
                    f"{reg['huella'][:10]}</div>", unsafe_allow_html=True)
        if accion:
            try:
                decision_record.cambiar_estado(decision_id, accion, usuario, motivo,
                                               avisos_reconocidos=reconocer)
                st.rerun()
            except decision_record.ErrorRegistro as e:
                st.error(str(e))


def espacio_decision():
    izq, der = st.columns([1, 2.3], gap="large")
    with izq:
        _formulario()
    with der:
        r = st.session_state.get("decision")
        if not r:
            st.markdown(
                "<div class='cp-vacio'><h3>¿Qué programa promocional ejecutas?</h3>"
                "<p>Plantea la decisión a la izquierda: presupuesto, mecánica y, si "
                "quieres, tu plan actual y alternativas. El copiloto compara los escenarios "
                "con las mismas métricas, recomienda uno y te explica por qué, qué cuesta y "
                "qué riesgos tiene. Tú decides si se aprueba.</p></div>",
                unsafe_allow_html=True)
            return
        salida = next((s for s in r["evidencia"] if s.get("ok")), None)
        _veredicto(r, salida)
        if not salida or r["decision"] == "BLOQUEADA":
            st.error(r["conclusion"])
            _gobierno(r)
            if r.get("decision_id"):
                _decidir(r["decision_id"], r["decision"])
            return
        _kpis(r, salida)
        _calendario(salida)
        st.markdown("<div class='cp-nota' style='margin:-8px 0 16px'>La pestaña "
                    "<b>Previsión</b> muestra cómo afecta este programa a las ventas semanales "
                    "de cada categoría y cuánto cuesta cada unidad incremental.</div>",
                    unsafe_allow_html=True)
        _razonamiento(r, salida)
        _graficos(salida)
        _gobierno(r)
        if r.get("decision_id"):
            _decidir(r["decision_id"], r["decision"])


def decisiones_registradas():
    regs = decision_record.listar()
    if not regs:
        st.markdown("<div class='cp-vacio'><h3>Aún no hay decisiones</h3><p>Evalúa una "
                    "decisión en el espacio de decisión o pide una recomendación al copiloto; "
                    "quedará aquí como propuesta.</p></div>", unsafe_allow_html=True)
        return
    estados = pd.Series([r["estado"] for r in regs]).value_counts()
    c = st.columns(4)
    for col, (est, color) in zip(c, [("propuesta", AZUL), ("en_revision", AMBAR),
                                     ("aprobada", VERDE), ("rechazada", ROJO)]):
        col.markdown(f"<div class='cp-kpi'><div class='cp-kpi-t'>{est.replace('_', ' ').capitalize()}"
                     f"</div><div class='cp-kpi-n' style='color:{color}'>"
                     f"{int(estados.get(est, 0))}</div></div>", unsafe_allow_html=True)
    st.write("")
    st.dataframe(
        [{"decisión": r["decision_id"], "creada": r["creado"].replace("T", " "),
          "estado": r["estado"], "objetivo": r["contenido"]["objetivo"]["nombre"],
          "recomendación": r["contenido"]["recomendacion"]["escenario"],
          "políticas": r["contenido"]["politicas"]["decision"],
          "íntegra": "sí" if r["integra"] else "NO"} for r in regs],
        hide_index=True, width="stretch")
    elegido = st.selectbox("Ver una decisión", [r["decision_id"] for r in regs])
    reg = next(r for r in regs if r["decision_id"] == elegido)
    for h in reg["historial"]:
        st.markdown(f"- {h['fecha'].replace('T', ' ')}: {h['de'] or 'creada'} → **{h['a']}** "
                    f"({h['usuario']}: {h['motivo']})")
    if st.button("Comprobar que es reproducible"):
        rep = decision_record.reproducir(elegido)
        (st.success if rep["reproducible"] else st.warning)(
            "Reproducible: el motor devuelve la misma recomendación con los mismos datos."
            if rep["reproducible"] else rep["motivo"])
    with st.expander("Registro completo"):
        st.json(reg, expanded=False)
