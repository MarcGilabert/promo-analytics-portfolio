# Copiloto de decisiones comerciales con gobernanza

Un asistente que recibe una pregunta comercial, ejecuta análisis reales, respalda cada conclusión con evidencia verificable y **bloquea una recomendación cuando incumple los controles**. No es un chatbot sobre datos: los números salen de funciones Python, no del modelo de lenguaje.

Caso de uso de demostración: analítica promocional para un retailer sobre el dataset Dunnhumby Complete Journey. El agente elige entre cuatro análisis según la pregunta: prever, evaluar una promoción, construir un programa promocional optimizado o **recomendar una decisión** comparando escenarios. Una recomendación nunca se ejecuta sola: queda registrada como propuesta y la aprueba o rechaza una persona.

## Las cinco tools

| Tool | Responde a | Devuelve |
|---|---|---|
| `get_category_forecast` | ¿Cuánto venderé? | Unidades (volumen) + intervalo |
| `evaluate_promo_roi` | ¿Es rentable una promo? | Uplift y ventas incrementales (estimados); ROI y semáforo con un margen supuesto, y su sensibilidad al margen |
| `optimize_promo_program` | ¿Qué promociono y cuándo, con este presupuesto? | Calendario semanal que maximiza ventas o volumen, coste, y beneficio ilustrativo con tres márgenes supuestos |
| `recommend_promo_decision` | ¿Qué programa ejecuto, en qué condiciones y por qué? ¿Y si cambio una palanca? | Recomendación (propuesta) frente al plan actual y las alternativas, con compromisos, robustez y supuesto crítico; se registra para su aprobación |
| `optimize_assortment` | ¿Qué fabricantes mantengo en esta subcategoría? | Cuántos fabricantes mantener y cuánto se arriesga: ventas conservadas como rango entre «nadie se cambia de marca» y «se cambian los que ya compran otra» |

### Tres niveles de evidencia

El dataset no incluye márgenes ni costes promocionales, así que cada métrica declara de dónde sale:

| Nivel | Qué incluye |
|---|---|
| **Medido** | Precio de lista, descuento estructural, actividad de folleto y display, ventas históricas y error de previsión en backtesting |
| **Estimado** | Unidades base e incrementales, ventas incrementales en euros y coste (el descuento total que asume el distribuidor): dependen de la validez del modelo |
| **Supuesto** | Beneficio y ROI (dependen de un margen que no está en los datos) |

Por eso **el beneficio no se optimiza**: se optimizan ventas o volumen y el beneficio se muestra en tres escenarios ilustrativos de margen (−5 pp, base, +5 pp). Pedir «maximiza el beneficio» se bloquea con esa explicación, y una política bloquea cualquier texto que presente un resultado como óptimo en beneficio o como rentable sin decir que usa un margen supuesto.

### El optimizador de programa

Es un programa lineal entero resuelto con PuLP (solver CBC):

- **Variables:** promocionar o no cada categoría cada semana.
- **Objetivo elegible:** ventas incrementales a precio de cliente (por defecto) o unidades incrementales. El beneficio no es un objetivo: se ilustra con márgenes supuestos.
- **Restricciones:** presupuesto, huecos de folleto por semana, un máximo de promociones por categoría para evitar la fatiga promocional y, opcionalmente, un tope de descuento total.
- **ROI mínimo por promoción:** opcional. Como se calcula con un margen supuesto, no filtra por defecto; si se pide, se aplica y la respuesta avisa de que usa un margen supuesto.
- **Restricciones recalculadas:** tras resolver, se vuelve a sumar el uso de cada restricción a partir del calendario y se indica cuáles limitan el programa. Si alguna no se cumple, la respuesta se bloquea.

**El hallazgo principal:** el distribuidor asume todo el descuento, y con 15 puntos de descuento extra casi ninguna promoción compensa ese coste: el volumen sube, pero el cliente paga menos en caja y el beneficio ilustrativo es negativo en los tres escenarios de margen. Con 1.000 €:

| Objetivo | Promociones | Unidades | Ventas | Coste (descuento) | Beneficio ilustrativo (−5 pp / base / +5 pp) |
| --- | --- | --- | --- | --- | --- |
| Ventas | 1 (leche) | +263 | +18 € | 533 € | −446 / −418 / −389 € |
| Volumen | 3 (2 de sopa, 1 de leche) | +603 | −50 € | 979 € | −792 / −744 / −693 € |

Maximizar ventas o volumen no es lo mismo que ganar dinero, y la respuesta lo avisa siempre. Si se pide un ROI mínimo, ninguna categoría lo supera y el programa queda vacío, con la lista de las categorías excluidas.

Las pruebas comparan la solución del solver con una búsqueda por fuerza bruta para cada objetivo, comprueban que cada objetivo gana en su propia métrica y verifican que se respetan todas las restricciones.

### Comparación de escenarios

`scenarios.py` evalúa tres escenarios con las **mismas métricas, el mismo objetivo y las mismas restricciones**, para que la diferencia se pueda atribuir a la decisión:

- **Actual:** el calendario que el retailer tiene previsto. Si no se da, mantener la actividad promocional media observada (incremento cero).
- **Alternativa:** el mejor programa si se cambia una palanca: presupuesto, mecánica (folleto, display o ambos), huecos, ROI mínimo o tope de descuento. No puede cambiar el objetivo.
- **Optimizada:** el programa óptimo con las palancas actuales.

Cada escenario muestra la diferencia frente al actual, si cumple las restricciones y si incluye promociones por debajo del ROI mínimo. Un calendario actual que incumple una restricción no es viable y queda al final del ranking.

| Escenario (1.000 €, objetivo volumen) | Promociones | Unidades | Ventas | Beneficio | ROI |
| --- | --- | --- | --- | --- | --- |
| Actual: queso, refrescos y snacks dos semanas | 6 | +692 | −1.482 € | −2.554 € | −0,85 |
| Alternativa: solo folleto | 3 | +392 | −259 € | −779 € | −0,83 |
| Optimizada | 3 | +603 | −50 € | −744 € | −0,76 |

Una prueba de propiedades genera 45 calendarios actuales aleatorios y comprueba que la optimizada nunca queda por debajo de un actual viable en ninguno de los tres objetivos.

### Motor de decisión

`decision_engine.py` convierte la comparación de escenarios en una recomendación trazable, con estado **propuesta**: la aprueba o la rechaza una persona.

- **Recomendación:** el escenario viable con mejor valor del objetivo; a igualdad, el de menor coste y menos promociones.
- **Por qué gana:** ventaja frente al segundo y frente al actual, y las restricciones que lo limitan.
- **Compromisos:** las métricas en las que es peor que el escenario actual (por ejemplo, gana volumen pero resta ventas).
- **Robustez:** beneficio ilustrativo con los tres márgenes; si el ganador cambia cuando el volumen promocional es un WAPE menor o mayor de lo previsto; y si la mejora sigue siendo positiva con un WAPE menos de volumen.
- **Supuesto crítico:** los puntos de margen adicionales que necesitaría la recomendación para no perder dinero (si ni con 30 puntos más deja de perder, lo dice).

Una séptima política, **Recomendación robusta**, recalcula que la recomendación cumple sus restricciones (si no, bloquea) y avisa si pierde dinero con algún margen, si el ganador cambia con el error del modelo o si la mejora no se distingue de ese error.

Con 1.000 € y dos alternativas (solo folleto, o permitir 4 promociones por categoría), en ambos objetivos gana la segunda:

| Objetivo | Recomendación | Mejora | Robustez |
| --- | --- | --- | --- |
| Ventas | 1 promoción de leche | +18 € de ventas | **Aviso:** pierde dinero con los tres márgenes (−418 € con el base), la mejora queda dentro del error del modelo (de −298 a +334 €) y el ganador cambia con ese error |
| Volumen | 4 promociones | +680 unidades | **Aviso:** pierde dinero con los tres márgenes (−652 € con el base); la mejora supera el error del modelo |

Es la conclusión más útil del proyecto: el modelo permite decidir sobre volumen, pero **comprar volumen con descuento que paga el distribuidor destruye valor con cualquier margen razonable**, y el copiloto lo dice en vez de esconderlo.

### Registro de decisiones

La auditoría registra cada **ejecución** del copiloto; `decision_record.py` registra cada **decisión de negocio** y su ciclo de vida: `propuesta → aprobada | rechazada`, con un paso intermedio opcional `en_revision`.

Cada registro (`decisions/<decision_id>.json`) guarda la versión y el periodo de los datos, el modelo, la versión y los veredictos de las políticas, el objetivo y las restricciones, todos los escenarios evaluados, la recomendación con su resultado esperado y nivel de evidencia, compromisos, robustez, supuestos, supuestos críticos, límites y los `run_id` de origen.

Reglas de gobierno, todas con prueba:

- Nadie aprueba una recomendación **bloqueada** por las políticas.
- Aprobar una recomendación **con avisos** exige reconocerlos; los avisos reconocidos quedan en el historial.
- Aprobar o rechazar exige **usuario y motivo**. Los estados finales no cambian: para reconsiderar se crea una decisión nueva que **sustituye** a la anterior.
- El contenido se sella con una **huella SHA-256**: si alguien edita el resultado esperado después, la lectura lo detecta.
- **Reproducible:** `reproducir(decision_id)` vuelve a ejecutar el motor con los parámetros guardados y comprueba que sale la misma recomendación con las mismas métricas.

### Espacio de decisión (app)

La app tiene tres pestañas: **Preguntar** (lenguaje natural), **Espacio de decisión** y **Decisiones registradas**. El espacio de decisión sigue el flujo de una decisión comercial:

1. **Definir:** objetivo (ventas o volumen), presupuesto, semanas, mecánica, huecos, límite por categoría, tope de descuento, el plan actual del retailer y hasta dos alternativas.
2. **Comparar:** todos los escenarios con las mismas métricas y el beneficio ilustrativo con tres márgenes.
3. **Entender:** el texto de la recomendación empieza por la decisión de negocio (qué ejecutar, resultado esperado, frente al plan actual, por qué, compromiso, supuesto crítico) y muestra las siete políticas y las afirmaciones verificadas.
4. **Decidir:** aprobar, guardar para revisión o rechazar, con usuario y motivo. Aprobar está desactivado si las políticas bloquean, y exige reconocer los avisos si los hay.

El formulario y las preguntas en lenguaje natural usan exactamente el mismo circuito (`agent.ejecutar`): motor, afirmaciones verificadas, políticas, auditoría y registro.

### Pestaña Previsión: demanda y efecto de las promociones

La pestaña **Previsión** responde dos preguntas con las mismas ventas:

- **Demanda** (planificación y compras): «¿cuánto venderé?». Histórico real, predicción del backtesting si se exporta (`data/backtest_semanal.csv`) y proyección hasta 26 semanas.
- **Efecto de las promociones** (RGM y fabricante CPG): «¿cuánto de lo que vendo se asocia a las promociones y cuánto cuesta cada unidad extra?». Descomposición del histórico en base, folleto y display (con `data/actividad_semanal.csv`) y coste del descuento por unidad incremental, repartido entre retailer y fabricante. Ejemplo: cada unidad extra de leche cuesta 2,03 € de descuento, el 97 % de su precio.

En la vista de demanda, el gráfico proyecta las ventas semanales de una categoría: la **base** en línea continua y el escenario **con el programa** en guiones, con una banda de error que se abre fuera de la semana validada. Es una simulación para explorar y declara sus supuestos:

- **Efecto de la promoción:** qué parte del aumento estimado por el modelo se cree (100 % = el del modelo).
- **Cambio de precio y elasticidad:** las unidades cambian según (1 + cambio) ^ elasticidad. La elasticidad **no está medida en estos datos**; la referencia por defecto es −1,76, media de 367 elasticidades de marca (Tellis, 1988). Con +3 % de precio, la base de leche baja un 5,1 % en unidades y un 2,2 % en ingresos.
- **Banda de error:** WAPE medido a una semana, abierto con la raíz del horizonte (regla ilustrativa).

El histórico (últimas 26 semanas completas) sale de `data/ventas_semanales.csv`, exportado desde Dunnhumby; la semana 102 se descarta por incompleta. Para regenerarlo, guarda en ese fichero las columnas `semana`, `categoria` y `unidades` desde el notebook de forecasting:

```python
df_semanal[["semana", "categoria", "unidades"]].to_csv("copilot/data/ventas_semanales.csv", index=False)
```

### Calidad de la decisión (paso 7)

`backtest_decision.py` comprueba en las 12 semanas que el modelo no vio (90 a 101) si las recomendaciones se sostienen. Detalle y cifras en [`docs/calidad_decision.md`](../docs/calidad_decision.md).

- **Nivel 1 (medido):** error semanal del 10,8 %; el aumento promocional real fue el 80 % del predicho. La leche se sobrestima (0,56) y los refrescos aciertan (1,03); en el resto el efecto no supera el ruido.
- **Nivel 2 (simulado):** con el mismo presupuesto, el plan recomendado supera al que ejecutó el retailer (+866 unidades, +16 %), también con el aumento corregido por esa calibración (+842).
- **Nivel 3:** el efecto real solo se mide con un piloto con tiendas de control.

`reconstruir_backtest.py` reconstruye el backtest de la previsión con el mismo esquema del estudio (WAPE 11,4 %) para la línea de «Predicho en validación».

### Surtido

`surtido.py` elige qué fabricantes mantener en una subcategoría de refrescos o en pretzels (programa lineal entero), conservando el máximo de ventas. La transferencia de demanda se estima con los hogares que ya compran varios fabricantes y se trata como cota superior, así que el resultado es un rango. `preparar_surtido.py` genera `data/surtido_grupos.csv` desde la exportación de Colab. Detalle en [`docs/viabilidad_surtido.md`](../docs/viabilidad_surtido.md).

**Lo que no optimiza, a propósito:** la profundidad del descuento queda fija, porque el modelo de volumen no mide cómo responde la demanda a un descuento mayor; optimizarla daría resultados sin respaldo. Tampoco hay estacionalidad semanal validada, así que un programa de más de una semana sale con aviso de extrapolación.

El agente selecciona la tool según la intención de la pregunta. Una pregunta económica ya no se bloquea: se responde con la tool de ROI, que **declara sus supuestos** (margen). El bloqueo económico solo se mantiene cuando ninguna tool puede respaldar la respuesta (p. ej. una categoría sin datos).

## Qué lo hace distinto

Un LLM conectado a unas tools lo monta cualquiera. Lo que no es genérico es la **capa de gobernanza**: cada respuesta pasa por un motor de políticas antes de entregarse, y queda registrada para poder reconstruirla.

## Arquitectura

```
Pregunta
   │
   ▼
Agente (SDK de Anthropic) ──elige──► Herramienta(s)   ← el cálculo real (Python)
   │                                    │
   │                     claims verificados + 7 políticas + auditoría
   │                                    │
   │◄──────── texto verificado y datos ─┘
   ▼
Redacción del agente
   │
   ▼
Control final: cifras con respaldo y lenguaje controlado
   │
   ├─ pasa    → entrega la redacción
   └─ no pasa → entrega el texto verificado de las herramientas, con aviso
   │
   ▼
Registro de auditoría (un JSON por ejecución)
```

El LLM, cuando se usa, solo selecciona las herramientas y redacta. **Nunca calcula los números.** El enrutador funciona sin LLM (por reglas), para que la demo corra sin claves.

### El agente (pestaña «Preguntar al copiloto»)

Un solo agente construido con el **SDK de Anthropic (tool runner)** (`agente.py`). Tiene seis herramientas: previsión de demanda, efecto de una promoción, programa promocional, recomendación, surtido y decisiones registradas. Puede encadenar varias en una misma pregunta («previsión de queso y efecto de una promoción»).

Reparto de papeles:

- **El agente** entiende la pregunta, elige las herramientas y redacta la respuesta.
- **Python** calcula. Cada llamada del agente pasa por el mismo circuito que el resto de la app: afirmaciones verificadas, 7 políticas y auditoría. El agente recibe el texto ya verificado y los datos; si una herramienta queda bloqueada, solo recibe el motivo.
- **La respuesta final se vuelve a comprobar:** toda cifra que cite debe salir de una herramienta no bloqueada (o de la propia pregunta) y no puede presentar nada como óptimo en beneficio. Si falla, se descarta la redacción del agente y se entrega el texto verificado de las herramientas, con aviso.

Sin `ANTHROPIC_API_KEY`, la misma pestaña responde con el **enrutador por reglas** (una herramienta por pregunta) y la misma salida, para que la app publicada funcione sin claves. El modo solo cambia **quién decide y redacta**, nunca **quién calcula** (siempre Python) ni **quién valida** (siempre las políticas).

Las pruebas (`test_agente.py`) usan el cliente real del SDK con un transporte HTTP simulado: la «API» devuelve respuestas guionizadas y el tool runner ejecuta de verdad las herramientas, sin red ni clave.

### Grounding por afirmaciones estructuradas

El texto final no se escribe en lenguaje libre: se **renderiza a partir de afirmaciones (claims) verificadas**. Cada claim ata una métrica, una categoría, un periodo, un valor y una unidad a un campo concreto de una ejecución (`run_id`). Antes de redactar, cada claim se **re-verifica** leyendo de nuevo ese campo:

- si el valor no coincide con el de la tool → se rechaza;
- si el valor es correcto pero se atribuye a **otra categoría** → se rechaza.

Así el grounding valida **significado**, no solo que el número exista: no se puede colgar el ROI de la leche al queso ni invertir un porcentaje. Si algún claim no verifica, la política de grounding **bloquea la respuesta**. Como salvaguarda adicional, también se comprueba que no quede ninguna cifra suelta en el texto sin respaldo.

Las pruebas incluyen casos que manipulan un claim (categoría o valor cambiados) y confirman que la verificación lo rechaza.

## Las 7 reglas de política

| Regla | Comprueba | Acción |
|---|---|---|
| Grounding | Cada afirmación coincide con la evidencia en valor, categoría, métrica, periodo y unidad; ninguna cifra suelta sin respaldo | Bloquea |
| Suficiencia de datos y evidencia | Hay datos (y distingue si faltan datos, si los argumentos son inválidos o si hubo un fallo técnico), la serie es estable y la conclusión concreta tiene al menos una afirmación verificada | Bloquea |
| Extrapolación | El horizonte pedido no supera el **validado en backtesting** (1 semana) | Avisa |
| Supuestos declarados | Una afirmación económica exige supuestos con valor, **origen y fecha**; se acompaña de su sensibilidad. Ningún texto puede presentar un resultado como óptimo en beneficio ni hablar de rentabilidad sin decir que usa un margen supuesto | Bloquea |
| Fiabilidad del modelo | La categoría no tiene fiabilidad baja, medida por cobertura del intervalo y sesgo | Avisa |
| Recomendación robusta | La recomendación cumple sus restricciones (recalculadas); avisa si pierde dinero con algún margen supuesto, si el ganador cambia con el error del modelo o si la mejora no se distingue de ese error | Bloquea / avisa |
| Objetivo y restricciones | Un programa optimizado cumple sus restricciones, recalculadas a partir del calendario; avisa si el programa pierde dinero con el margen base o si el ROI mínimo filtra con un margen supuesto | Bloquea / avisa |

**Jerarquía de decisión:** `block > warn > pass`. Un incumplimiento crítico nunca queda neutralizado por avisos ni por reglas que pasan: una cifra sin respaldo se bloquea aunque el modelo sea fiable. Hay un test que lo comprueba.

**Dos conceptos separados:**
- *Fiabilidad del modelo* (regla 5): si el modelo rinde bien **en general** en esa categoría.
- *Suficiencia de evidencia* (regla 2): si **esta conclusión concreta** está respaldada. Un modelo puede ser fiable y, aun así, no tener evidencia para una pregunta determinada.

**Horizonte validado:** el estudio de forecasting validó previsiones a **1 semana** (rolling-origin, 3 ventanas). Por eso cualquier previsión a más plazo se entrega con aviso: el error a ese plazo no está medido. El sistema no se atribuye una precisión que no ha comprobado.

**Supuestos económicos:** la tool de ROI declara cada supuesto con su valor, origen y fecha, y añade un análisis de sensibilidad (ROI con margen ±5 puntos).

## Demostración

| Escenario | Pregunta | Resultado |
|---|---|---|
| Volumen (verde) | ¿Cuánto venderé de leche la próxima semana? | `get_category_forecast` → entregada con evidencia y `run_id` |
| Volumen a 4 semanas | ¿Y en las próximas 4 semanas? | Entregada con aviso: horizonte no validado |
| ROI | ¿Qué ROI tendrá una promo de leche? | `evaluate_promo_roi` → entregada: ventas estimadas y ROI con un margen supuesto del 20 % |
| Aviso | ¿Y de sopa? | Entregada, pero baja la confianza (modelo poco fiable) |
| Bloqueo por datos | ¿Qué ROI tendrá una promo de cervezas? | Bloqueada: no hay datos de esa categoría |
| Programa | Optimiza el programa del próximo mes con 1.000 € | 1 promoción de leche, +18 € de ventas; con aviso: pierde 418 € con el margen base |
| Beneficio | Maximiza el beneficio del programa con 1.000 € | Bloqueada: el beneficio no se optimiza sin márgenes reales |

El agente elige la tool según la pregunta. El bloqueo ya no depende de que falte una capacidad, sino de que **ninguna tool pueda respaldar la respuesta con datos**: así, pedir el ROI de una categoría inexistente se detiene en vez de inventar una cifra.

## Evaluación

Un set de 18 preguntas con la categoría y la decisión esperadas (`eval/casos.json`) y un arnés que puntúa al agente (`eval/run_eval.py`):

```bash
python eval/run_eval.py
```

Mide dos cosas: si enruta a la categoría correcta y si la decisión (entregar / avisar / bloquear) coincide con la esperada. El set cubre los cuatro comportamientos: entrega limpia, aviso por fiabilidad o extrapolación, y bloqueo económico o por falta de datos.

Hay dos conjuntos:

- **`eval/casos.json`** (28) — camino feliz, bloqueos conocidos, programas promocionales y recomendaciones con alternativas.
- **`eval/casos_adversos.json`** (17) — pedir que se maximice el beneficio (en un programa o en una recomendación), argumentos inválidos (horizonte 0 o 100, presupuesto 0), preguntas ambiguas o mixtas (volumen + ROI), sin sentido, categorías inexistentes y límites (extrapolación máxima, horizonte validado con fiabilidad baja).

El arnés puntúa **por separado** la selección de tool, el enrutado y la decisión de política, para localizar dónde falla si falla.

En **modo determinista** el enrutador acierta el 100 % por construcción: el set sirve de test de no-regresión (un cambio en las reglas que rompa un caso se detecta al instante). En **modo agente** el mismo arnés mide las decisiones del LLM, que es la prueba real de que el agente elige bien. Ejecutar el set con una clave de API da esa segunda cifra.

## Estructura

```
copilot/
├── app.py            # interfaz Streamlit
├── agente.py         # agente de preguntas (SDK de Anthropic, tool runner) y control de la respuesta final
├── ui_agente.py      # pestaña Preguntar al copiloto (chat)
├── agent.py          # circuito de gobierno: tool → claims → políticas → auditoría; enrutador por reglas
├── tools.py          # capa analítica (forecast, ROI y programa promocional)
├── scenarios.py      # comparación de escenarios (actual, alternativa, optimizada)
├── decision_engine.py # motor de decisión: recomendación, compromisos y robustez
├── decision_record.py # registro de decisiones: estados, aprobación, huella y reproducción
├── ui_decision.py    # espacio de decisión y decisiones registradas (Streamlit)
├── proyeccion.py     # previsión semanal con supuestos de promoción y precio
├── surtido.py        # optimizador de surtido por fabricante y subcategoría
├── preparar_surtido.py # transferencia de demanda por grupo desde la exportación de hogares
├── ui_surtido.py     # pestaña Surtido (Streamlit)
├── vistas_prevision.py # cálculos de la pestaña Previsión (backtest, descomposición, eficiencia)
├── ui_prevision.py   # pestaña Previsión (Streamlit)
├── roi_logic.py      # lógica de ROI (reutilizada del validador de promociones)
├── policies.py       # motor de políticas (7 reglas)
├── claims.py         # afirmaciones estructuradas y su verificación
├── audit.py          # registro de ejecuciones
├── demo.py           # demo por línea de comandos
├── test_copilot.py   # pruebas del circuito (grounding, jerarquía, fallos técnicos, auditoría)
├── test_roi_logic.py # pruebas de la fórmula de ROI y casos límite
├── test_programa.py  # pruebas del optimizador (fuerza bruta y restricciones)
├── test_metricas.py  # pruebas del formato común de métricas
├── test_objetivos.py # pruebas del selector de objetivo y las restricciones
├── test_escenarios.py # pruebas de la comparación de escenarios
├── test_decision.py  # pruebas del motor de decisión y de la política de robustez
├── test_registro.py  # pruebas del registro de decisiones
├── test_agente_decision.py # pruebas de la recomendación por el enrutador
├── test_agente.py    # pruebas del agente del SDK con API simulada
├── eval/
│   ├── casos.json    # 18 preguntas con categoría y decisión esperadas
│   └── run_eval.py   # arnés que puntúa enrutado y decisión
└── data/
    └── forecast_store.csv   # parámetros del modelo (derivados del estudio de forecasting)
```

## Ejecutar

```bash
pip install -r requirements.txt
python demo.py              # demo por consola
python test_copilot.py      # pruebas
python test_programa.py     # pruebas del optimizador
python test_metricas.py     # pruebas del formato común de métricas
python test_objetivos.py    # pruebas del selector de objetivo
python test_escenarios.py   # pruebas de la comparación de escenarios
python test_decision.py     # pruebas del motor de decisión
python test_registro.py     # pruebas del registro de decisiones
python test_agente_decision.py  # pruebas de la recomendación por el agente
python test_proyeccion.py   # pruebas de la previsión con supuestos
python test_vistas.py       # pruebas de la pestaña Previsión
python test_backtest_decision.py # pruebas del paso 7 (datos sintéticos)
python test_calidad_real.py     # paso 7 con los datos reales
python test_surtido.py          # optimizador de surtido
python test_agente.py           # agente (SDK de Anthropic) con API simulada
streamlit run app.py        # interfaz
```

## Auditoría

Cada ejecución deja un JSON en `runs/` con lo necesario para reconstruirla:

- pregunta, modo (agente o determinista) y **modelo LLM** usado;
- **versión de las políticas**;
- lo **solicitado** (tool y argumentos), lo **ejecutado** (si tuvo éxito o qué tipo de error) y si se **aprobó**;
- versión de datos, resultados y metadatos de cada tool;
- las afirmaciones con su verificación y el motivo de cada fallo;
- el veredicto de cada regla, la decisión final y los errores técnicos.

No registra claves ni secretos (hay un test que lo comprueba).

## Fiabilidad medida por categoría

La fiabilidad no es una etiqueta a mano: se deriva de dos métricas medidas en la validación del estudio de forecasting (ventana de test, intervalo del 80 %):

- **cobertura del intervalo** — qué fracción de los valores reales cae dentro del intervalo previsto (objetivo 0,80);
- **sesgo** — si el modelo se queda corto o se pasa de forma sistemática.

Regla documentada: `baja` si cobertura < 0,60 o |sesgo| > 5 %; `alta` si cobertura ≥ 0,85 y |sesgo| ≤ 2 %; `media` en el resto.

| Categoría | Cobertura | Sesgo | Fiabilidad |
|---|---|---|---|
| FLUID MILK PRODUCTS | 0,91 | +1,2 % | alta |
| SOFT DRINKS | 0,73 | +3,1 % | media |
| CHEESE | 0,64 | −1,3 % | media |
| FRZN MEAT/MEAT DINNERS | 0,64 | −3,5 % | media |
| BAKED BREAD/BUNS/ROLLS | 0,64 | −2,0 % | media |
| SOUP | 0,82 | −9,1 % | baja |
| VEGETABLES - SHELF STABLE | 0,55 | −1,4 % | baja |
| BAG SNACKS | 0,45 | −2,6 % | baja |

Tanto la cobertura como el sesgo quedan en los metadatos de cada ejecución y en la auditoría, así que el aviso de fiabilidad es trazable hasta el número que lo motivó.

## Por qué el tool runner y no LangGraph

El bucle del agente (pedir herramienta, ejecutarla, devolver el resultado, repetir) lo resuelve el tool runner del SDK de Anthropic, sin escribirlo a mano y sin otra dependencia. Un orquestador de grafos como LangGraph compensaría con reintentos controlados o con pausas para aprobación humana dentro del propio flujo. Aun así, la verificación y las políticas seguirían fuera del agente, como ahora: son las que garantizan que ninguna cifra sale de la IA.

## Límites

- Los parámetros del modelo provienen del estudio de forecasting sobre una muestra de 2.500 hogares y 8 categorías; no es un modelo de producción.
- La relación entre promoción y ventas es asociación, no causalidad.
- Esta es la fase 1 (una tool). El valor agéntico crece al añadir más tools entre las que el agente elige.
