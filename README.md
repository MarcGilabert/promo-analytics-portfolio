# Copiloto de decisiones comerciales con gobernanza

Toolkit de analítica promocional para un retailer, construido sobre promociones históricas: previsión de demanda, ROI por promoción y **programa promocional optimizado** bajo presupuesto. Se usa a través de un asistente que responde preguntas comerciales con cálculos reales, respalda cada conclusión con evidencia verificable y **se detiene en lugar de inventar** cuando no puede respaldar una respuesta. Demostrado sobre datos reales de retail: [Dunnhumby — The Complete Journey](https://data.mendeley.com/datasets/7myy93ym6k/1) (2.500 hogares, 711 días, licencia CC BY 4.0).

**App en línea:** https://promo-copilot-569896642310.europe-west1.run.app

## Qué hace

1. Recibe una pregunta comercial: «¿cuánto venderé de leche la próxima semana?», «¿es rentable una promo de queso?».
2. Elige el análisis adecuado: previsión de volumen, ROI de una promoción, programa promocional óptimo («¿qué promociono cada semana con 1.000 €?») o recomendación comparando escenarios («¿y si permitimos 4 promociones por categoría?»).
3. Calcula en Python. Un agente construido con el SDK de Anthropic (tool runner) decide qué análisis usar y puede encadenar varios, pero **nunca calcula**.
4. Convierte el resultado en afirmaciones estructuradas y las verifica contra los datos: valor, categoría, periodo y unidad.
5. Pasa siete políticas que deciden si la respuesta se **entrega**, se **entrega con aviso** o se **bloquea**.
6. Comprueba la redacción final del agente: si cita una cifra que no sale de un análisis, se descarta y se entrega el texto verificado.
7. Registra la ejecución completa para poder reconstruirla.

## Por qué no es un chatbot más

- **Gobernanza fuera del modelo.** Las políticas no dependen de que el modelo diga que ha acertado. Un bloqueo nunca lo neutraliza un aviso ni una regla en verde.
- **El texto nace de afirmaciones verificadas.** No se puede atribuir una cifra real a otra categoría ni cambiar su unidad: la verificación lo detecta y bloquea.
- **No se atribuye precisión que no ha medido.** La previsión está validada a una semana; a más plazo, la respuesta sale con aviso.
- **Fiabilidad medida, no opinada.** Cada categoría se clasifica con la cobertura del intervalo y el sesgo medidos en backtesting.
- **Evaluado con preguntas trampa.** 28 casos normales y 17 adversos, puntuando por separado la selección de análisis, la categoría y la decisión: 45/45 en modo determinista.

## Contenido

| Carpeta | Qué hay |
| --- | --- |
| [`copilot/`](copilot/) | El copiloto: análisis, políticas, verificación, auditoría, evaluación y app Streamlit |
| [`forecasting/`](forecasting/) | El estudio de previsión que respalda la herramienta de volumen |
| [`docs/business_case.md`](docs/business_case.md) | Proceso antes y después, business case y plan de adopción |
| [`docs/calidad_decision.md`](docs/calidad_decision.md) | ¿Funcionan las recomendaciones? Backtest de la decisión en semanas no vistas |
| [`docs/viabilidad_surtido.md`](docs/viabilidad_surtido.md) | Optimizador de surtido: viabilidad por referencia y por fabricante, transferencia de demanda y resultados |

## Resultados clave

- **Forecasting:** conocer el calendario de promociones baja el error de previsión del 13,1 % al 11,0 %; casi la mitad de la mejora viene de una sola categoría (leche) y un modelo más complejo no aporta nada.
- **Las promociones compran volumen a costa de ventas y de beneficio:** con 15 puntos de descuento extra, casi ninguna aumenta las ventas en euros, y como el distribuidor asume todo el descuento, ninguna sale rentable con márgenes razonables. Con 1.000 €, el programa que maximiza ventas es 1 promoción de leche (+18 €, −418 € de beneficio ilustrativo); el que maximiza volumen, 3 promociones, +603 unidades y −50 € de ventas.
- **El beneficio no se optimiza:** el dataset no tiene márgenes ni costes promocionales, así que el beneficio se muestra en tres escenarios ilustrativos de margen y cada métrica declara si es medida, estimada o supuesta. El copiloto avisa siempre que un programa pierde dinero con el margen supuesto.
- **Business case:** para un equipo con 150 preguntas al mes, el escenario conservador libera 135 horas de analista al mes y recupera un piloto de 24.000 € en unos 5 meses. Todos los supuestos están declarados en el documento.

## Ejecutar en local

```bash
git clone https://github.com/<usuario>/<repo>.git
cd <repo>/copilot
pip install -r requirements.txt
python demo.py              # demo por consola
python test_copilot.py      # pruebas del circuito
python test_roi_logic.py    # pruebas de la fórmula de ROI
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
python eval/run_eval.py     # evaluación (45 casos)
streamlit run app.py        # interfaz
```

Funciona sin clave de API, en modo determinista. Con `ANTHROPIC_API_KEY`, Claude elige el análisis; la verificación y las políticas son las mismas.

## Surtido: evaluado antes de construir

- **Por referencia (SKU) no es viable:** con 2.500 hogares, la mediana es de 2 a 9 compradores por referencia y los rankings no se mantienen entre años.
- **Por fabricante dentro de subcategoría sí,** en refrescos y pretzels: un programa lineal entero elige qué fabricantes mantener conservando el máximo de ventas, con una transferencia de demanda estimada en los hogares y tratada como cota superior.
- **Ejemplo:** en pretzels, con 7 de 12 fabricantes se conserva entre el 95,3 % y el 98,9 % de las ventas.

Detalle en [`docs/viabilidad_surtido.md`](docs/viabilidad_surtido.md).

## Límites

Muestra de 2.500 hogares y 8 categorías; previsión validada solo a una semana; la relación entre promoción y ventas es una asociación, no un efecto causal; los márgenes son supuestos editables porque el dataset no incluye costes. Detalle en cada carpeta.

## Autor

Marc Gilabert — Máster en Data Science & Business Analytics.
