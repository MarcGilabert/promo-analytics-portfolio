# Surtido: cuántos fabricantes mantener y cuánto se arriesga

## La idea en tres frases

1. Se ordenan los fabricantes de una subcategoría por ventas y se quitan los pequeños hasta conservar las ventas que se quieren (por ejemplo, el 98 %), dejando siempre al menos una marca propia del distribuidor.
2. Lo que vendían los retirados no se pierde del todo: parte de sus clientes ya compra otras marcas de la subcategoría y probablemente se pasaría.
3. Como eso no está probado, el resultado es un **rango**: entre «nadie se cambia» (pesimista) y «se cambian los que ya compran otra marca» (optimista).

## Resultados (conservar el 98 %)

| Subcategoría | Fabricantes | Ventas conservadas | Lectura |
| --- | --- | --- | --- |
| Pretzels | 7 de 12 | 95 % – 99 % | Rango estrecho: recortar la cola es seguro |
| Bebidas sin gas en lata | 6 de 7 | 99 % – 99 % | Seguro, pero casi no hay nada que recortar |
| Refrescos en lata 12/18 | 3 de 13 | 84 % – 99 % | Rango amplio: probar antes en unas tiendas |
| Refrescos en botella de 2 l | 3 de 9 | 84 % – 99 % | Rango amplio: probar antes en unas tiendas |

**Conclusión:** quedarse con los que más venden ya es casi lo mejor. Lo que aporta el análisis es **cuántos** fabricantes dejar y **cuánto se arriesga** con cada decisión.

## Por qué por fabricante y no por referencia (SKU)

Se probó primero por referencia. Cada referencia tiene muy pocos compradores en el panel (entre 2 y 9 hogares en las subcategorías grandes) y su ranking de ventas cambia mucho de un año a otro, así que cualquier resultado sería ruido. Agrupando por fabricante dentro de cada subcategoría hay compradores suficientes y el ranking es estable en refrescos y pretzels; el resto de snacks quedó fuera.

## Detalle técnico (por si preguntan)

- **«Ya compran otra marca»:** para cada fabricante, la parte de sus ventas que viene de hogares que ese año también compran otro fabricante de la subcategoría. A los fabricantes con pocos compradores se les acerca a la media de la subcategoría para que no salgan cifras extremas por azar.
- **Cálculo:** un programa lineal entero (PuLP) elige qué fabricantes mantener para conservar el máximo de ventas, con un máximo de fabricantes y al menos una marca propia.
- **Comprobación:** decidido con el año 1, el surtido conserva en el año 2 prácticamente lo mismo que la mejor elección posible.

## Lo que no se puede afirmar

- Se conservan ventas, no beneficio: no hay márgenes por fabricante ni espacio en lineal.
- Que un cliente ya compre otra marca no prueba que se cambiaría. Para medirlo haría falta un piloto: retirar fabricantes de cola en unas tiendas y compararlas con otras que no cambian.

## Cómo reproducirlo

```bash
cd copilot
python preparar_surtido.py     # data/raw/compras_hogar_grupo.csv → data/surtido_grupos.csv
python test_surtido.py
streamlit run app.py           # pestaña Surtido
```
