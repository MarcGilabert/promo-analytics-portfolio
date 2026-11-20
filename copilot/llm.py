"""Capa LLM opcional (Claude) para seleccion de tool y redaccion.

El LLM solo DECIDE que tool usar y REDACTA la recomendacion. No calcula: los
numeros salen de la tool, y el motor de politicas verifica despues que el texto
no contiene cifras sin respaldo.

Si no hay anthropic instalado o no hay ANTHROPIC_API_KEY, las funciones devuelven
None y el agente cae al enrutador determinista.
"""
import json
import os

MODELO = os.environ.get("COPILOT_MODELO", "claude-sonnet-5-5")


def disponible() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _cliente():
    import anthropic
    return anthropic.Anthropic()


def seleccionar_tool(pregunta: str, categorias: list) -> dict | None:
    """Pide a Claude que elija la tool y sus parametros (tool_use). Devuelve
    {'tool':..., 'parametros':...} o None si no decide / no hay LLM."""
    if not disponible():
        return None
    herramientas = [
        {
            "name": "get_category_forecast",
            "description": "Prevision de unidades (volumen) por categoria para las proximas "
                           "semanas. Usar para preguntas de cuanto se va a vender.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "categoria": {"type": "string", "enum": categorias},
                    "horizonte": {"type": "integer", "description": "semanas a prever"},
                },
                "required": ["categoria"],
            },
        },
        {
            "name": "evaluate_promo_roi",
            "description": "ROI de una promocion para una categoria, con supuestos declarados "
                           "(margen). Usar para preguntas economicas: ROI, "
                           "rentabilidad, euros, margen de una promocion o rebaja.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "categoria": {"type": "string", "enum": categorias},
                    "puntos_descuento_extra": {"type": "number",
                                               "description": "puntos de descuento sobre el nivel habitual"},
                },
                "required": ["categoria"],
            },
        },
        {
            "name": "optimize_promo_program",
            "description": "Programa promocional optimo: decide que categorias promocionar "
                           "cada semana con un presupuesto, maximizando beneficio, ventas "
                           "o volumen incremental. Usar cuando se pide un programa, un calendario, "
                           "que promocionar o como repartir un presupuesto.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "presupuesto_eur": {"type": "number", "description": "presupuesto promocional en euros"},
                    "semanas": {"type": "integer", "description": "horizonte del programa en semanas (1-12)"},
                    "objetivo": {"type": "string", "enum": ["ventas", "volumen", "beneficio"],
                                 "description": "que maximizar; por defecto ventas. El "
                                                "beneficio no se optimiza (no hay margenes "
                                                "reales): pasalo solo si el usuario lo pide, "
                                                "y el sistema lo explicara"},
                    "roi_minimo": {"type": ["number", "null"],
                                   "description": "ROI minimo por promocion, solo si el "
                                                  "usuario lo pide (usa un margen supuesto)"},
                    "max_descuento_total_eur": {"type": "number",
                                                "description": "tope de descuento total en euros"},
                },
                "required": [],
            },
        },
        {
            "name": "recommend_promo_decision",
            "description": "Recomienda que programa promocional ejecutar: compara el plan "
                           "actual, alternativas que cambian una palanca y el optimo, con el "
                           "mismo objetivo y restricciones, y explica compromisos, robustez y "
                           "supuestos criticos. Usar cuando se pide una recomendacion, una "
                           "decision o comparar escenarios ('y si...', 'frente a...').",
            "input_schema": {
                "type": "object",
                "properties": {
                    "presupuesto_eur": {"type": "number"},
                    "semanas": {"type": "integer", "description": "1-12"},
                    "objetivo": {"type": "string", "enum": ["ventas", "volumen", "beneficio"],
                                 "description": "por defecto ventas; beneficio no se optimiza"},
                    "alternativa": {
                        "type": "object",
                        "description": "palancas que cambia la alternativa",
                        "properties": {
                            "presupuesto_eur": {"type": "number"},
                            "mecanica": {"type": "string",
                                         "enum": ["folleto_y_display", "folleto", "display"]},
                            "max_promos_categoria": {"type": "integer"},
                            "max_promos_semana": {"type": "integer"},
                        },
                    },
                },
                "required": [],
            },
        },
        {
            "name": "optimize_assortment",
            "description": "Surtido: que fabricantes mantener en una subcategoria (solo refrescos "
                           "por formato y pretzels) para conservar el maximo de ventas, usando la "
                           "transferencia de demanda estimada. Usar para preguntas de surtido, "
                           "retirar referencias o cuantas marcas mantener.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "subcategoria": {"type": "string", "enum": [
                        "SOFT DRINKS 12/18&15PK CAN CAR", "SFT DRNK 2 LITER BTL CARB INCL",
                        "SFT DRNK MLT-PK BTL CARB (EXCP", "SOFT DRINKS 20PK&24PK CAN CARB",
                        "SOFT DRINKS 6PK/4PK CAN CARB (", "SFT DRNK SNGL SRV BTL CARB (EX",
                        "SOFT DRINKS CAN NON-CARB (EXCE", "PRETZELS"]},
                    "max_grupos": {"type": "integer", "description": "fabricantes a mantener"},
                    "cobertura_objetivo": {"type": "number",
                                           "description": "fraccion de ventas a conservar, p. ej. 0.98"},
                    "factor_transferencia": {"type": "number",
                                             "description": "0-1, sensibilidad sobre la transferencia"},
                },
                "required": ["subcategoria"],
            },
        },
    ]
    try:
        msg = _cliente().messages.create(
            model=MODELO, max_tokens=400, tools=herramientas,
            messages=[{"role": "user", "content": pregunta}],
        )
        for bloque in msg.content:
            if bloque.type == "tool_use":
                return {"tool": bloque.name, "parametros": bloque.input}
    except Exception:
        return None
    return None   # el LLM no pidio ninguna tool


def redactar(pregunta: str, salida: dict) -> str | None:
    """Pide a Claude una recomendacion breve basada SOLO en el resultado de la tool."""
    if not disponible():
        return None
    sistema = ("Eres un analista comercial. Redacta una recomendacion de 2-3 frases "
               "usando EXCLUSIVAMENTE los numeros del resultado proporcionado. No "
               "inventes ninguna cifra. Si el resultado no trae un dato, no lo afirmes.")
    try:
        msg = _cliente().messages.create(
            model=MODELO, max_tokens=300, system=sistema,
            messages=[{"role": "user", "content":
                       f"Pregunta: {pregunta}\n\nResultado de la tool:\n"
                       f"{json.dumps(salida, ensure_ascii=False)}"}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
    except Exception:
        return None
