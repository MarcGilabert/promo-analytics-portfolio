"""Orquestador del copiloto (modo doble: LLM si hay clave, reglas si no).

Flujo: pregunta -> seleccionar tool (LLM o reglas) -> ejecutar -> redactar
(LLM o plantilla) -> verificar que cada cifra del texto viene de la tool ->
motor de politicas -> entregar o bloquear -> registrar en auditoria.

Los numeros SIEMPRE salen de la tool. El grounding comprueba que el texto (lo
escriba el LLM o la plantilla) no contiene cifras sin respaldo.
"""
import re

import llm
from audit import registrar
from claims import construir_claims, render, verificar_todos
from policies import POLICY_VERSION, TERMINOS_ECONOMICOS, Contexto, evaluar
import decision_record
from decision_engine import recommend_promo_decision
from surtido import optimize_assortment
from tools import TOOLS, categorias_disponibles, valores_respaldados

# Registro completo de herramientas que puede invocar el agente.
HERRAMIENTAS = {
    **TOOLS,
    "recommend_promo_decision": {
        "fn": recommend_promo_decision,
        "descripcion": "Recomendacion de programa promocional: compara el plan actual, "
                       "alternativas y el optimo, y recomienda uno con compromisos, "
                       "robustez y supuestos criticos.",
        "devuelve": "recomendacion (propuesta), por que, compromisos, robustez y escenarios.",
    },
    "optimize_assortment": {
        "fn": optimize_assortment,
        "descripcion": "Surtido: que fabricantes mantener en una subcategoria de refrescos o "
                       "pretzels, conservando el maximo de ventas segun la transferencia estimada.",
        "devuelve": "grupos que se mantienen y retiran, ventas conservadas, sensibilidad y "
                    "validacion con el ano siguiente.",
    },
}

INTENCION_SURTIDO = ["surtido", "retirar", "deslist", "racionaliz", "cuántos fabricantes",
                     "cuantos fabricantes", "qué fabricantes", "que fabricantes", "qué marcas",
                     "que marcas", "cola larga", "referencias"]
SUBCAT_TEXTO = [
    (r"12/18|12 ?/ ?18", "SOFT DRINKS 12/18&15PK CAN CAR"),
    (r"20/24|20 ?/ ?24", "SOFT DRINKS 20PK&24PK CAN CARB"),
    (r"6/4|6 ?/ ?4|6 ?pk", "SOFT DRINKS 6PK/4PK CAN CARB ("),
    (r"2 ?l(itros?)?\b|2 litros", "SFT DRNK 2 LITER BTL CARB INCL"),
    (r"multipack|multi-pack", "SFT DRNK MLT-PK BTL CARB (EXCP"),
    (r"individual", "SFT DRNK SNGL SRV BTL CARB (EX"),
    (r"sin gas", "SOFT DRINKS CAN NON-CARB (EXCE"),
    (r"pretzel", "PRETZELS"),
]


def _ruta_surtido(p: str):
    sub = next((c for rx, c in SUBCAT_TEXTO if re.search(rx, p)), None)
    if sub is None:
        return {"tool": "optimize_assortment", "parametros": {"subcategoria": "(no indicada)"}}
    params = {"subcategoria": sub}
    m = re.search(r"(\d+)\s*(fabricantes|marcas|grupos)", p)
    if m:
        params["max_grupos"] = int(m.group(1))
    m = re.search(r"(\d{2}(?:[.,]\d)?)\s*%\s*(de las ventas|de ventas|de cobertura)", p)
    if m:
        params["cobertura_objetivo"] = float(m.group(1).replace(",", ".")) / 100
    m = re.search(r"(\d{1,3})\s*%\s*de\s*(la\s*)?transferencia|transferencia\s*(del?\s*)?(\d{1,3})\s*%", p)
    if m:
        params["factor_transferencia"] = int(m.group(1) or m.group(4)) / 100
    return {"tool": "optimize_assortment", "parametros": params}

SINONIMOS = {
    "leche": "FLUID MILK PRODUCTS", "lacteo": "FLUID MILK PRODUCTS",
    "queso": "CHEESE", "sopa": "SOUP",
    "pan": "BAKED BREAD/BUNS/ROLLS", "bolleria": "BAKED BREAD/BUNS/ROLLS",
    "refresco": "SOFT DRINKS", "bebida": "SOFT DRINKS",
    "snack": "BAG SNACKS", "aperitivo": "BAG SNACKS",
    "congelado": "FRZN MEAT/MEAT DINNERS", "carne": "FRZN MEAT/MEAT DINNERS",
    "verdura": "VEGETABLES - SHELF STABLE", "conserva": "VEGETABLES - SHELF STABLE",
}


# ---- Enrutador por reglas (fallback) ----

INTENCION_PROGRAMA = ["programa", "calendario", "planific", "optimiza", "maximiza",
                      "presupuesto",
                      "qué promociono", "que promociono", "qué categorías promociono",
                      "que categorias promociono"]


def _horizonte(p: str):
    m = re.search(r"(\d+)\s*semana", p)
    if m:
        return int(m.group(1))
    if re.search(r"(pr[oó]xima|siguiente|esta) semana|semana que viene", p):
        return 1
    return 4          # "el mes que viene", "proximo mes" o sin plazo


def _ruta_programa(p: str):
    params = {"semanas": _horizonte(p)}
    m = re.search(r"(\d[\d.]*)\s*(€|eur\b|euros)", p)
    if m:
        params["presupuesto_eur"] = float(m.group(1).replace(".", ""))
    # Objetivo: el primero que se nombre; por defecto, beneficio.
    # "beneficio" se reconoce para poder explicar por que no se optimiza.
    objetivos = {"ventas": r"ventas|facturaci|ingresos", "volumen": r"volumen|unidades",
                 "beneficio": r"maximi\w*\s+(el\s+)?(beneficio|margen)|"
                              r"(beneficio|margen)\s+m[aá]ximo|optimi\w*\s+(el\s+)?beneficio"}
    hallados = [(m.start(), o) for o, rx in objetivos.items() if (m := re.search(rx, p))]
    if hallados:
        params["objetivo"] = min(hallados)[1]
    if not re.search(r"sin (m[ií]nimo de )?roi|aunque pierda|aunque no sea rentable", p):
        m = re.search(r"roi\s+m[ií]nimo\s+(?:de\s+)?(-?\d+(?:[.,]\d+)?)", p)
        if m:
            params["roi_minimo"] = float(m.group(1).replace(",", "."))
    m = re.search(r"descuento\s+(?:total\s+)?m[aá]ximo\s+(?:de\s+)?(\d[\d.]*)\s*(€|eur\b|euros)", p)
    if m:
        params["max_descuento_total_eur"] = float(m.group(1).replace(".", ""))
        # el presupuesto no puede leerse de la cifra del descuento
        cifras = re.findall(r"(\d[\d.]*)\s*(?:€|eur\b|euros)", p)
        otras = [c for c in cifras if c != m.group(1)]
        if otras:
            params["presupuesto_eur"] = float(otras[0].replace(".", ""))
        else:
            params.pop("presupuesto_eur", None)
    return {"tool": "optimize_promo_program", "parametros": params}


INTENCION_DECISION = ["recomienda", "recomiénda", "recomendación", "recomendacion", "compara",
                      "escenario", "y si ", "qué pasa si", "que pasa si", "frente a",
                      "alternativa", "decisión", "decision"]
SEPARADOR_ALTERNATIVA = re.compile(r"\by si\b|qu[eé] pasa si|frente a|alternativa|comparad[oa] con")


def _alternativa(p: str):
    """Palancas que cambia la alternativa (texto posterior a "y si", "frente a"...)."""
    alt = {}
    m = re.search(r"(\d[\d.]*)\s*(€|eur\b|euros)", p)
    if m:
        alt["presupuesto_eur"] = float(m.group(1).replace(".", ""))
    if re.search(r"solo (\w+ ){0,2}folleto(?! y display)", p):
        alt["mecanica"] = "folleto"
    elif re.search(r"solo (\w+ ){0,2}display", p):
        alt["mecanica"] = "display"
    m = re.search(r"(\d+)\s*promociones? por categor", p)
    if m:
        alt["max_promos_categoria"] = int(m.group(1))
    m = re.search(r"(\d+)\s*huecos", p)
    if m:
        alt["max_promos_semana"] = int(m.group(1))
    return alt


def _ruta_decision(p: str):
    corte = SEPARADOR_ALTERNATIVA.search(p)
    base_txt, alt_txt = (p[:corte.start()], p[corte.end():]) if corte else (p, "")
    params = _ruta_programa(base_txt)["parametros"]
    alt = _alternativa(alt_txt) if alt_txt else {}
    if alt:
        params["alternativa"] = alt
    return {"tool": "recommend_promo_decision", "parametros": params}


def _ruta_reglas(pregunta: str):
    p = pregunta.lower()
    if any(t in p for t in INTENCION_SURTIDO):
        return _ruta_surtido(p)
    contexto_programa = re.search(r"\d\s*(€|eur\b|euros)|programa|calendario|promoci", p)
    if any(t in p for t in INTENCION_DECISION) and contexto_programa:
        return _ruta_decision(p)
    if any(t in p for t in INTENCION_PROGRAMA):
        return _ruta_programa(p)
    cat = None
    for c in categorias_disponibles():
        if c.lower() in p:
            cat = c
            break
    if cat is None:
        for clave, c in SINONIMOS.items():
            if clave in p:
                cat = c
                break
    if cat is None:
        return None
    if any(t in p for t in TERMINOS_ECONOMICOS):
        return {"tool": "evaluate_promo_roi",
                "parametros": {"categoria": cat, "puntos_descuento_extra": 15}}
    horizonte = _horizonte(p)
    return {"tool": "get_category_forecast", "parametros": {"categoria": cat, "horizonte": horizonte}}


def _seleccionar(pregunta: str):
    """Devuelve (ruta, modo). modo in {'llm','reglas'}."""
    ruta = llm.seleccionar_tool(pregunta, categorias_disponibles())
    if ruta:
        return ruta, "llm"
    return _ruta_reglas(pregunta), "reglas"


# ---- Grounding: cada numero del texto debe estar respaldado por la tool ----

def _numeros(texto: str):
    out = []
    for token in re.findall(r"\d[\d. ,]*", texto):
        limpio = token.replace(" ", "").replace(" ", "")
        # separador de miles (1.234 / 1,234) vs decimal
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", limpio):
            limpio = limpio.replace(".", "").replace(",", "")
        else:
            limpio = limpio.replace(",", ".")
        try:
            out.append(float(limpio.rstrip(".")))
        except ValueError:
            pass
    return out


def _cifras_citadas(texto: str, salidas: list):
    respaldados = set()
    for s in salidas:
        respaldados |= valores_respaldados(s)
    rid = next((s["run_id"] for s in salidas if s.get("ok")), None)
    citadas = []
    for n in _numeros(texto):
        ok = any(abs(n - v) < 0.5 or (v and abs(n - v) / v < 0.001) for v in respaldados)
        citadas.append((n, rid if ok else None))
    return citadas


# ---- Redaccion ----

def responder(pregunta: str) -> dict:
    ruta, modo = _seleccionar(pregunta)
    return ejecutar(pregunta, ruta, modo)


def ejecutar(pregunta: str, ruta: dict | None, modo: str = "formulario") -> dict:
    """Ejecuta una ruta (tool + parametros) con todo el circuito de gobierno.
    La usan el agente y el espacio de decision de la app."""
    salidas, borrador, verif, errores = [], "", [], []
    horizonte = 4
    supuestos_declarados = False

    if ruta:
        params = ruta["parametros"]
        horizonte = int(params.get("horizonte", params.get("semanas", 4)) or 4)
        try:
            out = HERRAMIENTAS[ruta["tool"]]["fn"](**params)
        except Exception as e:                      # fallo tecnico, no falta de datos
            out = {"tool": ruta["tool"], "parametros": params, "ok": False,
                   "tipo_error": "tecnico", "motivo": f"Error tecnico: {type(e).__name__}"}
            errores.append(f"{ruta['tool']}: {type(e).__name__}: {e}")
        salidas.append(out)
        if out.get("ok"):
            # El texto se construye a partir de claims verificados, no en texto libre.
            claims = construir_claims(out)
            verif = verificar_todos(claims, salidas)
            borrador = render(out, claims)
            supuestos_declarados = out["metadata"].get("supuestos_declarados", False)
        else:
            borrador = out["motivo"]
    else:
        borrador = ("No he identificado ninguna categoría conocida. Disponibles: "
                    f"{', '.join(categorias_disponibles())}.")

    # Solo se verifica el texto de una recomendacion; un mensaje de error de la tool
    # no es una afirmacion sobre los datos.
    cifras = _cifras_citadas(borrador, salidas) if any(s.get("ok") for s in salidas) else []

    ctx = Contexto(
        pregunta=pregunta, salidas_tools=salidas, borrador=borrador,
        supuestos_declarados=supuestos_declarados, horizonte=horizonte,
        cifras_citadas=cifras, claims_verificados=verif,
        ruta_identificada=ruta is not None,
    )
    decision, veredictos = evaluar(ctx)

    if decision == "BLOQUEADA":
        motivos = [v.mensaje for v in veredictos if v.estado == "block"]
        conclusion = "RECOMENDACIÓN BLOQUEADA. Motivo(s): " + " ".join(motivos)
    elif decision == "ENTREGAR_CON_AVISO":
        avisos = [v.mensaje for v in veredictos if v.estado == "warn"]
        conclusion = borrador + "  [Avisos: " + " ".join(avisos) + "]"
    else:
        conclusion = borrador

    claims_dump = [{"metrica": c.metrica, "categoria": c.categoria, "periodo": c.periodo,
                    "valor": c.valor, "unidad": c.unidad, "run_id": c.run_id,
                    "verificado": ok, "motivo": motivo} for c, ok, motivo in verif]
    registro = registrar(
        pregunta, salidas, veredictos, decision, conclusion, claims=claims_dump,
        modo=modo,
        modelo_llm=llm.MODELO if modo == "llm" else None,
        policy_version=POLICY_VERSION,
        solicitado=ruta,                                   # lo que se pidio ejecutar
        ejecutado=[{"tool": s.get("tool"), "ok": s.get("ok"),
                    "tipo_error": s.get("tipo_error")} for s in salidas],
        aprobado=decision != "BLOQUEADA",
        errores=errores,
    )

    # Una recomendacion valida se registra como decision "propuesta": la aprueba o
    # la rechaza una persona. Si las politicas la bloquean, solo se podra rechazar.
    decision_id = None
    dec_out = next((s for s in salidas if s.get("ok")
                    and s.get("tool") == "recommend_promo_decision"), None)
    if dec_out:
        reg = decision_record.crear(
            dec_out, {"decision": decision, "policy_version": POLICY_VERSION,
                      "veredictos": [(v.regla, v.estado, v.mensaje) for v in veredictos]},
            audit_id=registro["audit_id"], creado_por=f"copiloto ({modo})")
        decision_id = reg["decision_id"]

    return {
        "pregunta": pregunta,
        "modo": modo,
        "decision_id": decision_id,
        "decision": decision,
        "conclusion": conclusion,
        "borrador": borrador,
        "claims": claims_dump,
        "veredictos": [(v.regla, v.estado, v.mensaje) for v in veredictos],
        "evidencia": salidas,
        "audit_id": registro["audit_id"],
    }
