# Demand Forecasting por categoría — Dunnhumby Complete Journey

Estudio de previsión semanal de unidades vendidas por categoría de producto, comparando métodos estadísticos clásicos y modelos de boosting, y midiendo cuánto aporta conocer el calendario promocional con antelación.

## Resumen ejecutivo

**La pregunta.** ¿Conocer con antelación el calendario de promociones ayuda a prever mejor las ventas de la semana siguiente en cada categoría?

**La respuesta.** Sí, pero menos de lo que parece y no en todas las categorías.

- **Previsión más precisa.** El error medio baja del 13,1 % al 11,0 % al añadir el calendario de promociones (referencia sencilla: 17,4 %).
- **Casi la mitad de la mejora viene de una sola categoría, la leche**, cuyas ventas suben y bajan siguiendo el folleto. Sin ella, el error pasa del 11,8 % al 10,9 %.
- **Un modelo más sofisticado no aporta nada.** Los modelos avanzados se quedan igual o peor que uno lineal sencillo con la misma información. Lo que mejora la previsión es el dato del calendario, no la complejidad del algoritmo.
- **En euros:** el coste estimado de los errores de previsión baja de 455 € a 374 € por semana (−18 %) en la muestra analizada, con un margen y una merma supuestos, porque los datos no incluyen costes.

**Recomendación.**
1. Incorporar el calendario de promociones a la previsión en las categorías sensibles al folleto: leche, carne congelada, refrescos, queso y verduras en conserva.
2. En snacks, sopa y pan, mantener un método sencillo: el calendario no mejora el resultado.
3. Esta regla, decidida con las primeras semanas y comprobada en las últimas, reduce el error al 11,8 % frente al 13,1 % de aplicar el método sencillo en todo.

**Qué hay que tener en cuenta.**
- Se analizan 8 categorías, unas 100 semanas y una muestra de 2.500 hogares.
- La relación entre promoción y ventas es una asociación, no una prueba de causa y efecto.
- Los márgenes de error de las previsiones salen demasiado estrechos y no deben usarse todavía para decidir el stock de seguridad.

**Siguiente paso.** Esta previsión alimenta el [copiloto de decisiones comerciales](../copilot/), que la usa para responder preguntas de volumen y calcular el ROI de cada promoción antes de lanzarla.

## Planteamiento

- **Datos:** transacciones de Dunnhumby Complete Journey, agregadas a unidades por categoría y semana. Se trabaja con las 8 categorías de mayor volumen, excluyendo categorías no representativas (cupones, bolsas, etc.).
- **Horizonte:** h = 1 (se predice la semana siguiente).
- **Métrica:** WAPE = Σ|real − predicho| / Σ real.
- **Validación:** rolling-origin en 3 ventanas de 12 semanas (semanas 67-78, 79-90 y 91-101). La semana 102 se excluye por estar incompleta (6 días).
- **Entrenamiento:** desde la semana 21 (las primeras semanas corresponden a la puesta en marcha del panel).
- **Reentrenamiento:** semanal en los modelos de boosting.

### Modelos

| Modelo | Descripción |
|---|---|
| Naive estacional | Referencia mínima |
| ETS | Una serie por categoría, tendencia aditiva amortiguada, sin estacionalidad |
| LightGBM, XGBoost, CatBoost | Modelo global (una sola fórmula para las 8 categorías, con la categoría como variable) |

### Variables

- **Base:** lag 1, 2 y 4, medias móviles de 4 y 8 semanas, semana del año, categoría.
- **Calendario promocional ex-ante:** número de productos de la categoría en folleto y en display cada semana, relativo a su media. Se construye desde `causal_data` y es información conocida antes de que empiece la semana.

## Resultados (WAPE, media de las 3 ventanas)

| Modelo | Sin promoción | Con calendario ex-ante |
|---|---|---|
| Naive (semana anterior) | 0,174 | — |
| Naive estacional | 0,140 | — |
| ETS | 0,131 | — |
| LightGBM | 0,142 | 0,120 |
| XGBoost | 0,143 | 0,120 |
| CatBoost | 0,131 | 0,116 |
| Ridge (control lineal) | 0,129 | **0,110** |

Detalle por ventana (67-78 / 79-90 / 91-101):

| Modelo | Sin promoción | Con calendario |
|---|---|---|
| Naive estacional | 0,133 / 0,156 / 0,133 | — |
| ETS | 0,135 / 0,126 / 0,131 | — |
| LightGBM | 0,134 / 0,134 / 0,158 | 0,101 / 0,115 / 0,145 |
| XGBoost | 0,136 / 0,139 / 0,155 | 0,110 / 0,113 / 0,137 |
| CatBoost | 0,130 / 0,123 / 0,141 | 0,107 / 0,103 / 0,138 |
| Ridge | 0,134 / 0,121 / 0,131 | 0,107 / 0,103 / 0,121 |

Todos los modelos se evalúan sobre las mismas semanas (hasta la 101).

## Hallazgos

1. **Sin información promocional, el boosting no mejora a ETS.** CatBoost empata (0,131) y LightGBM/XGBoost quedan algo peor. Con una serie corta y poca estacionalidad, el método simple compite bien.
2. **El calendario promocional ex-ante mejora a los tres modelos de boosting** en las 9 comparaciones modelo-ventana, entre 0,3 y 3,3 puntos de WAPE.
3. **La ventaja frente a ETS no es concluyente.** Se mantiene en las ventanas 1 y 2 y se invierte en la 3 (entre 0,6 y 1,4 puntos peor). La mejora relativa media ronda el 8-11%.
4. **La mejora viene de la información, no del algoritmo.** Un Ridge con las mismas variables e interacciones promoción × categoría pasa de 0,129 a 0,110 con el calendario, y queda por debajo de los tres boosting (0,116-0,120). El boosting no aporta nada sobre un modelo lineal en este problema.
5. **La mejora se concentra en FLUID MILK.** Con el Ridge, el calendario mejora esa categoría en 7,8 puntos de WAPE. La serie tiene forma de diente de sierra y su correlación con el folleto es de 0,81. Sin FLUID MILK, la mejora global baja de 1,9 a 0,9 puntos (ETS 0,118, Ridge sin promoción 0,118, Ridge con calendario 0,109): aproximadamente la mitad del efecto viene de una sola categoría.
6. **En el resto de categorías el efecto es pequeño o nulo.**

| Categoría | Mejora de WAPE con calendario (puntos, Ridge) |
|---|---|
| FLUID MILK PRODUCTS | +7,77 |
| FRZN MEAT/MEAT DINNERS | +2,51 |
| CHEESE | +1,94 |
| SOFT DRINKS | +1,09 |
| VEGETABLES - SHELF STABLE | +0,76 |
| BAG SNACKS | +0,59 |
| BAKED BREAD/BUNS/ROLLS | −0,19 |
| SOUP | −0,70 |

7. **Ningún modelo anticipa los picos.** En CHEESE (semanas 85 y 92), BAG SNACKS (92 y 99) y FRZN MEAT (88) las ventas saltan y las predicciones apenas se mueven; el calendario de folleto y display no los explica. Los cambios de nivel (VEGETABLES hacia la semana 80, SOUP a lo largo de la ventana) se siguen con retraso, y en SOUP ETS se adapta mejor que el Ridge, por eso ahí el calendario no ayuda.

## Gráficos

![Real vs predicción por categoría](images/forecast_por_categoria.png)

![Mejora de WAPE por categoría](images/mejora_por_categoria.png)

![WAPE por ventana y modelo](images/wape_por_ventana.png)

## Valor de negocio

### Valor añadido por capa (Forecast Value Added)

Puntos de WAPE que mejora cada modelo respecto a un método simple.

| Modelo | WAPE | vs naive semana anterior (0,174) | vs naive estacional (0,140) |
|---|---|---|---|
| ETS | 0,131 | +4,3 | +0,9 |
| Ridge sin calendario | 0,129 | +4,5 | +1,1 |
| Ridge con calendario | 0,110 | +6,4 | +3,0 |

Frente a la referencia estacional, que es la más exigente, casi todo el valor añadido viene de incorporar el calendario promocional. Pasar de un método simple a ETS o a Ridge sin calendario aporta poco.

### Sesgo

El sesgo mide si el modelo se queda corto (negativo) o se pasa (positivo) de forma sistemática.

- **Global:** ETS +0,6 %, Ridge sin calendario −1,6 %, Ridge con calendario −1,4 %. Es pequeño: el WAPE no esconde un error sistemático.
- **Por categoría (Ridge con calendario):** SOUP −9,1 %, FRZN MEAT −3,5 %, SOFT DRINKS +3,1 %, BAG SNACKS −2,6 %, BAKED BREAD −2,0 %, VEGETABLES −1,4 %, CHEESE −1,3 %, FLUID MILK +1,2 %. SOUP es la excepción: el modelo infravalora sus ventas de forma consistente porque no sigue bien su tendencia creciente, lo que en la práctica supondría roturas de stock.

### Error en euros

Cada unidad no prevista se valora así: si se queda corta, se pierde el margen de la unidad (25 % del precio medio); si sobra, se pierde el 30 % de su coste por merma o stock inmovilizado. Ambos porcentajes son supuestos de trabajo, porque el dataset no incluye costes. Las cifras son de la muestra de 2.500 hogares y sirven como orden de magnitud, no como ahorro real.

| Modelo | Coste medio semanal del error |
|---|---|
| Naive (semana anterior) | 613 € |
| ETS | 455 € |
| Ridge sin calendario | 447 € |
| Ridge con calendario | 374 € |

- Ridge con calendario reduce el coste un 18 % frente a ETS (81 € por semana) y un 39 % frente al naive (239 € por semana).
- Por categoría, el ahorro del calendario frente a no usarlo es de 42 € por semana en FLUID MILK, 10 € en CHEESE, 10 € en FRZN MEAT, 10 € en SOFT DRINKS y 2 € o menos en el resto (SOUP y BAKED BREAD, ligeramente negativo). FLUID MILK concentra en torno al 58 % del ahorro total.

**Implicación:** el calendario promocional merece integrarse en el proceso de previsión sobre todo en las categorías muy sensibles al folleto. En el resto, un método simple como ETS da un resultado casi equivalente con menos complejidad.

## Regla de decisión por categoría

Para no elegir el modelo mirando el propio test, la regla se decide con las ventanas 1 y 2 y se evalúa en la ventana 3: se usa el Ridge con calendario si mejora al menos 1 punto de WAPE y ETS en caso contrario.

| Categoría | Mejora en ventanas 1-2 (puntos) | Modelo asignado |
|---|---|---|
| FLUID MILK PRODUCTS | 8,58 | Ridge con calendario |
| FRZN MEAT/MEAT DINNERS | 2,64 | Ridge con calendario |
| SOFT DRINKS | 2,24 | Ridge con calendario |
| CHEESE | 1,54 | Ridge con calendario |
| VEGETABLES - SHELF STABLE | 1,37 | Ridge con calendario |
| BAG SNACKS | 0,28 | ETS |
| SOUP | −0,24 | ETS |
| BAKED BREAD/BUNS/ROLLS | −0,02 | ETS |

Resultado en la ventana 3 (11 semanas, fuera de la muestra usada para decidir la regla):

| Estrategia | WAPE | Coste semanal del error |
|---|---|---|
| ETS en todas las categorías | 0,131 | 466 € |
| Ridge con calendario en todas | 0,121 | 425 € |
| Regla por categoría | **0,118** | **416 €** |

La regla mejora ligeramente a las otras dos estrategias, aunque la diferencia con el Ridge en todas las categorías es pequeña (0,3 puntos, 9 € por semana). Con una sola ventana de evaluación no es una conclusión firme.

## Intervalos de predicción

Se calcularon intervalos del 80 % con los errores relativos del Ridge con calendario en las ventanas 1 y 2, y se comprobó su cobertura en la ventana 3.

| Categoría | Cobertura (objetivo 0,80) | Colchón medio sobre la previsión |
|---|---|---|
| FLUID MILK PRODUCTS | 0,91 | 18,8 % |
| SOUP | 0,82 | 32,2 % |
| SOFT DRINKS | 0,73 | 14,7 % |
| BAKED BREAD/BUNS/ROLLS | 0,64 | 15,0 % |
| CHEESE | 0,64 | 8,1 % |
| FRZN MEAT/MEAT DINNERS | 0,64 | 17,2 % |
| VEGETABLES - SHELF STABLE | 0,55 | 15,5 % |
| BAG SNACKS | 0,45 | 10,4 % |
| **Global** | **0,67** | |

Los intervalos son demasiado estrechos: cubren el 67 % de los casos en lugar del 80 %. Cada categoría solo tiene 11 observaciones en la ventana 3, así que la cobertura por categoría es ruidosa, pero la tendencia global es clara. Con estos intervalos, el stock de seguridad quedaría corto. Para usarlos en producción habría que calibrarlos con más ventanas o ampliarlos.

## Conexión con el copiloto

La función `escenario(categoría, semana, n_mailer, n_display)` ajusta el Ridge con los datos anteriores a la semana indicada y devuelve las unidades y el margen incrementales de una promoción propuesta frente a la actividad promocional media de la categoría. Su lógica es la base de la herramienta de ROI del [copiloto](../copilot/).

Ejemplo, FLUID MILK en la semana 100 con la máxima actividad de folleto y display observada:

| Concepto | Valor |
|---|---|
| Unidades base | 1.312 |
| Unidades con la promoción | 1.996 |
| Unidades incrementales | 685 |
| Margen incremental (25 % supuesto) | 303 € |

Limitaciones de esta estimación:

- Es una asociación estadística entre calendario y ventas, no un efecto causal.
- El escenario usa el máximo histórico de actividad, el límite de lo observado, y por eso es el caso más optimista.
- El margen depende del supuesto del 25 %.

## Medir la promoción con ventas vs. calendario previo

Usar el % de productos en promoción medido a partir de las propias ventas (`pct_display`, `pct_mailer`) mejora más las métricas, pero parte de esa mejora es medición, no previsión: la variable se conoce porque ya se ha vendido. El calendario ex-ante es la versión honesta, porque es lo que estaría disponible al planificar. Las cifras de este README usan solo el calendario ex-ante.

## Calidad de datos

- **Arranque del panel:** las primeras semanas tienen pocos hogares activos, por eso se entrena desde la semana 21.
- **Semana 102:** solo tiene 6 días y se excluye.
- **Cola final:** los hogares activos bajan de 1.384 a 1.205 al final del periodo, lo que desplaza el nivel de ventas en la ventana 3.

## Descartado

- **`lag_52`:** se eligió tras ver el test y, al validar en 3 ventanas, resultó inestable. Se descartó.

## Qué no se ha probado

- Horizontes superiores a una semana.
- Ajuste de hiperparámetros (se usan valores fijos: 300 árboles, learning rate 0,05).
- Nivel SKU.
- Efecto causal de la promoción: este estudio mide capacidad predictiva, no incrementalidad.

## Limitaciones

- 8 categorías y ~100 semanas: tres ventanas de validación dan una idea de la estabilidad, pero no permiten afirmar diferencias pequeñas entre modelos.
- El calendario promocional se reconstruye desde `causal_data` y no incluye profundidad de descuento.
- Los resultados corresponden a un único conjunto de datos de una cadena y un periodo concreto.
