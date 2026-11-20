"""Prepara data/surtido_grupos.csv a partir de la exportacion de Colab
data/raw/compras_hogar_grupo.csv (hogar x subcategoria x fabricante x tamano x ano).

Unidad de decision: fabricante dentro de subcategoria (la subcategoria ya fija el
formato: latas 12/18, botella de 2 l...). Por cada grupo y ano:
  ventas, hogares, si es marca propia y la TRANSFERENCIA ESTIMADA: parte de sus
  ventas que viene de hogares que ese mismo ano tambien compran otro fabricante
  de la subcategoria (tienen alternativa en su repertorio). Los grupos con pocos
  hogares se ajustan hacia la media de la subcategoria (Bayes empirico, peso
  equivalente a K hogares).
Es una estimacion (que un hogar tenga alternativa no prueba que cambiaria).
"""
import os

import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")
K_AJUSTE = 30


def transferencia(h, anio):
    a = h[h["anio"] == anio].groupby(
        ["SUB_COMMODITY_DESC", "household_key", "MANUFACTURER"]).agg(
        ventas=("ventas", "sum"), privada=("BRAND", lambda b: (b == "Private").any())).reset_index()
    a["con_alternativa"] = a.groupby(["SUB_COMMODITY_DESC", "household_key"])[
        "MANUFACTURER"].transform("nunique") > 1
    g = a.groupby(["SUB_COMMODITY_DESC", "MANUFACTURER"]).apply(lambda d: pd.Series({
        "ventas": d["ventas"].sum(), "hogares": d["household_key"].nunique(),
        "privada": bool(d["privada"].any()),
        "transf_bruta": (d["ventas"] * d["con_alternativa"]).sum() / d["ventas"].sum()
        if d["ventas"].sum() > 0 else 0.0}), include_groups=False).reset_index()
    media = g.groupby("SUB_COMMODITY_DESC").apply(
        lambda d: (d["transf_bruta"] * d["ventas"]).sum() / d["ventas"].sum(), include_groups=False)
    g["transf_sub"] = g["SUB_COMMODITY_DESC"].map(media)
    g["transf"] = (g["hogares"] * g["transf_bruta"] + K_AJUSTE * g["transf_sub"]) / (
        g["hogares"] + K_AJUSTE)
    return g


def preparar(ruta=os.path.join(DATA, "raw", "compras_hogar_grupo.csv")):
    h = pd.read_csv(ruta)
    t1 = transferencia(h, 1)
    t2 = transferencia(h, 2)[["SUB_COMMODITY_DESC", "MANUFACTURER", "ventas", "hogares"]]
    g = t1.merge(t2, on=["SUB_COMMODITY_DESC", "MANUFACTURER"], how="outer",
                 suffixes=("_a1", "_a2"))
    g[["ventas_a1", "ventas_a2", "hogares_a1", "hogares_a2"]] = g[
        ["ventas_a1", "ventas_a2", "hogares_a1", "hogares_a2"]].fillna(0)
    g["privada"] = g["privada"].fillna(False).astype(bool)
    g = g.rename(columns={"SUB_COMMODITY_DESC": "subcategoria", "MANUFACTURER": "fabricante"})
    g["fabricante"] = g["fabricante"].astype(int)
    cols = ["subcategoria", "fabricante", "privada", "ventas_a1", "hogares_a1", "transf_bruta",
            "transf_sub", "transf", "ventas_a2", "hogares_a2"]
    g = g[cols].sort_values(["subcategoria", "ventas_a1"], ascending=[True, False])
    for c in ["ventas_a1", "ventas_a2"]:
        g[c] = g[c].round(2)
    for c in ["transf_bruta", "transf_sub", "transf"]:
        g[c] = g[c].round(3)
    return g


if __name__ == "__main__":
    g = preparar()
    g.to_csv(os.path.join(DATA, "surtido_grupos.csv"), index=False)
    print(g.groupby("subcategoria").size())
