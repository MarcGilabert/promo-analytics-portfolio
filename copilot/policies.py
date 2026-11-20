"""Motor de politicas: 7 reglas que avisan o bloquean una recomendacion.

Cada regla recibe el contexto de la ejecucion (la pregunta, lo que devolvieron
las tools, los claims verificados y el borrador) y devuelve un veredicto.

JERARQUIA DE DECISION
  block > warn > pass. Un incumplimiento critico (block) nunca queda
  neutralizado por reglas que pasan ni por avisos: si cualquier regla bloquea,
  la respuesta se bloquea aunque el resto este en verde. Ejemplo: una cifra
  economica sin respaldo se bloquea aunque el modelo de forecasting sea fiable.

DOS CONCEPTOS SEPARADOS
  - Fiabilidad del modelo (regla 5): si el modelo rinde bien EN GENERAL en esa
    categoria, medido en backtesting (cobertura y sesgo).
  - Suficiencia de datos y evidencia (regla 2): si ESTA conclusion concreta
    esta respaldada por resultados disponibles. Un modelo puede ser fiable y,
    aun asi, no haber evidencia para responder una pregunta determinada.
"""
import re
from dataclasses import dataclass, field

POLICY_VERSION = "1.4.0"

PASS, WARN, BLOCK = "pass", "warn", "block"
SEVERIDAD = {PASS: 0, WARN: 1, BLOCK: 2}

# Terminos que implican una afirmacion economica (euros / ROI / margen).
TERMINOS_ECONOMICOS = ["roi", "euro", "eur", "€", "margen", "beneficio", "rentab",
                       "ingreso", "dinero", "coste", "ganancia"]
SEMANAS_MINIMAS = 30


@dataclass
class Veredicto:
    regla: str
    estado: str          # pass | warn | block
    mensaje: str


@dataclass
class Contexto:
    pregunta: str
    salidas_tools: list           # lista de dicts devueltos por las tools
    borrador: str = ""            # texto de recomendacion propuesto
    supuestos_declarados: bool = False
    horizonte: int = 4
    cifras_citadas: list = field(default_factory=list)      # (valor, run_id|None)
    claims_verificados: list = field(default_factory=list)  # (claim, ok, motivo)
    ruta_identificada: bool = True


# ---- 1. Grounding ----

def r_grounding(ctx: Contexto) -> Veredicto:
    """Cada afirmacion debe verificarse contra su ejecucion (valor, categoria,
    metrica, periodo y unidad), y ninguna cifra del texto puede quedar sin respaldo."""
    fallos = [(c, motivo) for c, ok, motivo in ctx.claims_verificados if not ok]
    if fallos:
        detalle = "; ".join(f"{c.metrica}: {m}" for c, m in fallos[:3])
        return Veredicto("Grounding", BLOCK,
                         f"{len(fallos)} afirmacion(es) no coinciden con la evidencia ({detalle}).")
    sin_fuente = [c for c, rid in ctx.cifras_citadas if rid is None]
    if sin_fuente:
        return Veredicto("Grounding", BLOCK,
                         f"Hay {len(sin_fuente)} cifra(s) en el texto sin ejecucion que las respalde.")
    return Veredicto("Grounding", PASS,
                     "Afirmaciones verificadas (valor, categoria, periodo y unidad).")


# ---- 2. Suficiencia de datos y evidencia ----

def r_suficiencia(ctx: Contexto) -> Veredicto:
    """La conclusion concreta debe estar respaldada: tool con exito, datos
    suficientes y al menos una afirmacion verificada. Distingue la causa."""
    nombre = "Suficiencia de datos y evidencia"
    if not ctx.ruta_identificada:
        return Veredicto(nombre, BLOCK,
                         "No se ha identificado que analizar (ninguna categoria conocida).")
    exitosas = [s for s in ctx.salidas_tools if s.get("ok")]
    if not exitosas:
        tipos = {s.get("tipo_error") for s in ctx.salidas_tools}
        if "tecnico" in tipos:
            msg = "Fallo tecnico al ejecutar el analisis (no es falta de datos). Reintentar."
        elif "argumento" in tipos:
            motivo = next((s.get("motivo") for s in ctx.salidas_tools
                           if s.get("tipo_error") == "argumento"), "")
            msg = f"Peticion no valida; no se ha ejecutado el analisis. {motivo}".strip()
        else:
            motivo = next((s.get("motivo") for s in ctx.salidas_tools
                           if s.get("tipo_error") == "datos" and s.get("tool") == "optimize_assortment"), "")
            msg = ("No hay datos para esa categoria en el conjunto disponible. " + motivo).strip()
        return Veredicto(nombre, BLOCK, msg)
    for s in exitosas:
        meta = s.get("metadata", {})
        if meta.get("ramp_up"):
            return Veredicto(nombre, BLOCK,
                             "La serie esta en arranque de panel; datos no fiables.")
        semanas = meta.get("semanas_entrenamiento")
        if semanas is not None and semanas < SEMANAS_MINIMAS:
            return Veredicto(nombre, BLOCK,
                             f"La serie tiene {semanas} semanas; el minimo es {SEMANAS_MINIMAS}.")
    if not any(ok for _, ok, _ in ctx.claims_verificados):
        return Veredicto(nombre, BLOCK,
                         "La conclusion no tiene ninguna afirmacion verificada que la respalde.")
    return Veredicto(nombre, PASS, "Datos suficientes y conclusion respaldada por evidencia.")


# ---- 3. Extrapolacion ----

def r_extrapolacion(ctx: Contexto) -> Veredicto:
    """Compara el horizonte pedido con el horizonte VALIDADO en backtesting."""
    for s in ctx.salidas_tools:
        if s.get("ok") and "horizonte_validado" in s.get("metadata", {}):
            validado = s["metadata"]["horizonte_validado"]
            pedido = s["parametros"]["horizonte"]
            if pedido > validado:
                return Veredicto("Extrapolacion", WARN,
                                 f"Horizonte pedido ({pedido} sem) superior al validado en "
                                 f"backtesting ({validado} sem): el error a ese plazo no esta medido.")
    return Veredicto("Extrapolacion", PASS, "Horizonte dentro de lo validado.")


# ---- 4. Supuestos declarados ----

# Expresiones que presentarian un resultado como optimo o rentable en beneficio sin
# margenes reales. El dataset no los tiene: solo se admite con "margen supuesto".
FRASES_PROHIBIDAS = re.compile(
    r"(óptim\w*|optim\w*) (en|de|para el) beneficio|maximiz\w* (el )?beneficio"
    r"|beneficio (óptimo|maximo|máximo)|máximo beneficio")


def r_supuestos(ctx: Contexto) -> Veredicto:
    """Una afirmacion economica exige supuestos declarados con valor, origen y fecha,
    y nunca se presenta como optima en beneficio ni como rentable sin calificar."""
    borr = ctx.borrador.lower()
    if FRASES_PROHIBIDAS.search(borr.replace("no es un óptimo en beneficio", "")):
        return Veredicto("Supuestos declarados", BLOCK,
                         "El texto presenta un resultado como optimo en beneficio, pero el "
                         "beneficio depende de margenes supuestos.")
    if "rentab" in borr and "supuesto" not in borr:
        return Veredicto("Supuestos declarados", BLOCK,
                         "El texto habla de rentabilidad sin indicar que usa un margen supuesto.")
    texto = (ctx.pregunta + " " + ctx.borrador).lower()
    economico = any(t in texto for t in TERMINOS_ECONOMICOS)
    if not economico:
        return Veredicto("Supuestos declarados", PASS, "Sin afirmaciones economicas.")
    if ctx.salidas_tools and not any(s.get("ok") for s in ctx.salidas_tools):
        return Veredicto("Supuestos declarados", PASS,
                         "No hay resultado economico que evaluar (ver suficiencia).")
    if not ctx.supuestos_declarados:
        return Veredicto("Supuestos declarados", BLOCK,
                         "La pregunta implica euros o ROI, pero ninguna tool lo calcula con "
                         "supuestos declarados. No se puede dar una cifra economica verificable.")
    for s in ctx.salidas_tools:
        if s.get("ok") and s.get("metadata", {}).get("supuestos"):
            incompletos = [x["nombre"] for x in s["metadata"]["supuestos"]
                           if not x.get("origen") or not x.get("fecha")]
            if incompletos:
                return Veredicto("Supuestos declarados", BLOCK,
                                 f"Supuestos sin origen o fecha: {', '.join(incompletos)}.")
    return Veredicto("Supuestos declarados", PASS,
                     "Supuestos economicos declarados con valor, origen y fecha.")


# ---- 5. Fiabilidad del modelo ----

def r_fiabilidad(ctx: Contexto) -> Veredicto:
    """Avisa si alguna categoria tiene fiabilidad baja (medida: cobertura y sesgo)."""
    bajas = []
    for s in ctx.salidas_tools:
        if s.get("ok") and s.get("metadata", {}).get("fiabilidad_categoria") == "baja":
            m = s["metadata"]
            cov, sesgo = m.get("cobertura_intervalo"), m.get("sesgo_pct")
            detalle = s["parametros"]["categoria"]
            if cov is not None and sesgo is not None:
                detalle += f" (cobertura {cov:.0%}, sesgo {sesgo:+.1f}%)"
            bajas.append(detalle)
        if s.get("ok"):
            bajas.extend(s.get("metadata", {}).get("categorias_baja_fiabilidad", []))
    if bajas:
        return Veredicto("Fiabilidad del modelo", WARN,
                         f"Fiabilidad baja en: {'; '.join(bajas)}. "
                         "Baja la confianza de la recomendacion.")
    return Veredicto("Fiabilidad del modelo", PASS, "Fiabilidad del modelo aceptable.")


# ---- 6. Objetivo y restricciones ----

def r_objetivo(ctx: Contexto) -> Veredicto:
    """Un programa optimizado debe cumplir sus restricciones (recalculadas, no
    las que dice el solver) y declarar los compromisos de su objetivo."""
    nombre = "Objetivo y restricciones"
    avisos = []
    if not any(s.get("ok") and "restricciones" in s.get("metadata", {})
               for s in ctx.salidas_tools):
        return Veredicto(nombre, PASS, "No aplica: la respuesta no es un programa optimizado.")
    for s in ctx.salidas_tools:
        meta = s.get("metadata", {}) if s.get("ok") else {}
        if "restricciones" not in meta:
            continue
        from tools import comprobar_restricciones
        incumplidas = [r["nombre"] for r in comprobar_restricciones(s) if not r["cumple"]]
        if incumplidas:
            return Veredicto(nombre, BLOCK,
                             f"El programa incumple restricciones: {', '.join(incumplidas)}.")
        if meta.get("conflicto_objetivo"):
            avisos.append(meta["conflicto_objetivo"])
        if s["parametros"].get("roi_minimo") is not None:
            avisos.append("El ROI minimo filtra con un margen supuesto, no con margenes reales.")
    if avisos:
        return Veredicto(nombre, WARN, " ".join(avisos))
    return Veredicto(nombre, PASS, "Restricciones cumplidas y objetivo sin conflicto declarado.")


# ---- 7. Recomendacion robusta ----

def r_robustez(ctx: Contexto) -> Veredicto:
    """Una recomendacion debe cumplir sus restricciones (recalculadas) y se avisa
    si pierde dinero con algun margen supuesto, si el ganador cambia con el error
    del modelo o si su mejora no se distingue de ese error."""
    nombre = "Recomendacion robusta"
    decisiones = [s for s in ctx.salidas_tools
                  if s.get("ok") and s.get("tool") == "recommend_promo_decision"]
    if not decisiones:
        return Veredicto(nombre, PASS, "No aplica: la respuesta no es una recomendacion.")
    from decision_engine import verificar_recomendacion
    avisos = []
    for s in decisiones:
        incumplidas = verificar_recomendacion(s)
        if incumplidas:
            return Veredicto(nombre, BLOCK, "La recomendacion incumple restricciones: "
                             + ", ".join(incumplidas) + ".")
        rob = s["resultado"]["robustez"]
        rec = s["resultado"]["recomendacion"]
        if rob["margen"]["pierde_en"]:
            avisos.append("Pierde dinero con el margen supuesto "
                          + ", ".join(rob["margen"]["pierde_en"]) + ".")
        m = rob["modelo"]
        if not m["ganador_estable"]:
            avisos.append(f"El ganador cambia con el error del modelo (con menos volumen: "
                          f"{m['ganador_con_menos_volumen']}; con mas: "
                          f"{m['ganador_con_mas_volumen']}).")
        if m["mejora_supera_error"] is False:
            lo, hi = m["rango_objetivo_recomendacion"]
            avisos.append(f"La mejora estimada ({rec['valor_objetivo']}) queda dentro del "
                          f"error del modelo (de {lo} a {hi}).")
    if avisos:
        return Veredicto(nombre, WARN, " ".join(avisos))
    return Veredicto(nombre, PASS, "Recomendacion estable ante el error del modelo y sin "
                                   "perdidas en los escenarios de margen.")


REGLAS = [r_grounding, r_suficiencia, r_extrapolacion, r_supuestos, r_fiabilidad, r_objetivo,
          r_robustez]


def evaluar(ctx: Contexto):
    """Devuelve (decision, veredictos) aplicando la jerarquia block > warn > pass."""
    veredictos = [r(ctx) for r in REGLAS]
    peor = max(SEVERIDAD[v.estado] for v in veredictos)
    decision = {2: "BLOQUEADA", 1: "ENTREGAR_CON_AVISO", 0: "ENTREGAR"}[peor]
    return decision, veredictos
