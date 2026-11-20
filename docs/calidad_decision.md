# ¿Funcionan las recomendaciones? Calidad de la decisión

Una página sobre cómo se comprueba que el copiloto recomienda mejor que la práctica actual, y hasta dónde llega esa comprobación.

## Qué se comprueba

Se separan las últimas 12 semanas completas del histórico (semanas 90 a 101) y se tratan como futuro: el modelo de volumen se entrenó hasta la semana 80 y no las ha visto. La comprobación tiene tres niveles, de más a menos sólido.

| Nivel | Pregunta | Tipo de evidencia |
| --- | --- | --- |
| 1 | ¿Acierta el modelo en las semanas con promoción? | **Medido** con ventas reales |
| 2 | ¿El plan recomendado supera al plan que ejecutó el retailer, con el mismo presupuesto? | **Simulado** con el mismo modelo |
| 3 | ¿Habría vendido más el retailer siguiendo la recomendación? | **No demostrable** con estos datos; requiere un experimento |

## Nivel 1: el modelo acierta el volumen, pero exagera el aumento promocional

- **Error semanal (WAPE) en las 12 semanas no vistas: 10,8 %**, en línea con el 11,0 % del estudio de forecasting. El backtest reconstruido con el mismo esquema (origen móvil, 3 ventanas de 12 semanas, horizonte de una semana) da un 11,4 %.
- **Calibración del aumento:** en las semanas con folleto, el aumento real fue el **80 % del predicho** en el conjunto de categorías y el **67 %** en las dos donde el aumento es medible (leche y refrescos).
  - **Refrescos:** calibración 1,03, el modelo acierta.
  - **Leche:** calibración 0,56, el modelo predice casi el doble de aumento del que hubo. Es la categoría que más pesa en las recomendaciones.
- **En el resto de categorías el efecto no es medible:** con 3 a 6 semanas de folleto, el aumento predicho no supera dos veces el ruido semanal. No se puede afirmar ni que funcione ni que no.

## Nivel 2: con el mismo presupuesto, el plan recomendado supera al real

**Plan real:** las 39 promociones que hizo el retailer en esas 12 semanas, definidas como categorías con folleto al menos un 30 % por encima de su media. **Plan recomendado:** el que propone el optimizador con el mismo coste (15.567 €, el descuento total del plan real), los mismos huecos por semana y las mismas semanas.

| Objetivo | Plan real | Plan recomendado | Mejora | Mejora con el aumento corregido por la calibración |
| --- | --- | --- | --- | --- |
| Unidades | 39 promociones, +5.296 ud | 38 promociones, +6.162 ud | **+866 ud (+16 %)** | **+842 ud** |
| Ventas | 39 promociones, −5.609 € | 8 promociones, +144 € | **+5.753 €** | **+6.193 €** |

- **La recomendación aguanta la corrección:** el plan recomendado sigue ganando aunque el aumento de cada categoría se ajuste a lo que realmente ocurrió en el nivel 1.
- **El objetivo de ventas cambia la recomendación:** con ese objetivo, el optimizador propone hacer 8 promociones en lugar de 39 y gastar menos de un tercio del presupuesto. Con el aumento corregido, ni siquiera esas 8 suman ventas: el plan pierde 1.487 € frente a los 7.680 € del plan real. Para crecer en ventas, la mejor palanca es promocionar menos.

## Lo que no se puede afirmar

- Que el retailer habría vendido 866 unidades más: es una simulación con el mismo modelo que se usa para decidir.
- Que la promoción causa el aumento: es una asociación estimada en datos observacionales.
- Beneficio real: los márgenes son supuestos ilustrativos y el coste es el descuento total, que asume el distribuidor.

## Siguiente paso para pasar al nivel 3

Un piloto de 12 semanas con tiendas de prueba que siguen el plan recomendado y tiendas de control que mantienen la práctica actual, emparejadas por ventas y perfil, midiendo unidades, ventas y coste promocional. Es el mismo piloto que se propone en el business case.

## Cómo reproducirlo

```bash
cd copilot
python reconstruir_backtest.py        # backtest de la previsión (data/backtest_semanal.csv)
python test_calidad_real.py           # comprueba las cifras con los datos reales
streamlit run app.py                  # pestaña Previsión → ¿Funcionan las recomendaciones?
```

Datos: `data/ventas_semanales.csv` y `data/actividad_semanal.csv`, agregados desde Dunnhumby *The Complete Journey* (CC BY 4.0). La semana 102 se excluye por incompleta.
