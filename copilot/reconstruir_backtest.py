"""Reconstruye el backtest de la prevision con el mismo esquema del estudio:
origen movil, 3 ventanas de 12 semanas, horizonte 1 semana, Ridge por categoria
con calendario promocional (folleto, display) y ventas de semanas anteriores.
Cada prediccion solo usa semanas anteriores a la que predice.

Uso:  python reconstruir_backtest.py   ->  data/backtest_semanal.csv
No es el notebook original: es una reconstruccion transparente y reproducible.
"""
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

DATA = os.path.join(os.path.dirname(__file__), "data")
PRIMERA_SEMANA = 20                 # se excluye el arranque del panel
VENTANAS = [(66, 77), (78, 89), (90, 101)]


def preparar():
    v = pd.read_csv(os.path.join(DATA, "ventas_semanales.csv"))
    a = pd.read_csv(os.path.join(DATA, "actividad_semanal.csv"))
    df = v.merge(a, on=["semana", "categoria"]).sort_values(["categoria", "semana"])
    g = df.groupby("categoria")["unidades"]
    df["lag1"] = g.shift(1)
    df["lag2"] = g.shift(2)
    df["media4"] = g.transform(lambda s: s.shift(1).rolling(4).mean())
    return df.dropna()


def reconstruir():
    df = preparar()
    feats = ["folleto", "display", "lag1", "lag2", "media4"]
    filas = []
    for cat, g in df.groupby("categoria"):
        for i, (ini, fin) in enumerate(VENTANAS, 1):
            for w in range(ini, fin + 1):
                tr = g[(g["semana"] >= PRIMERA_SEMANA) & (g["semana"] < w)]
                te = g[g["semana"] == w]
                if te.empty:
                    continue
                m = Ridge(alpha=1.0).fit(tr[feats], tr["unidades"])
                filas.append({"semana": w, "categoria": cat, "ventana": i,
                              "prediccion": float(m.predict(te[feats])[0])})
    bt = pd.DataFrame(filas)
    real = df[["semana", "categoria", "unidades"]]
    chk = bt.merge(real, on=["semana", "categoria"])
    wape = (chk["unidades"] - chk["prediccion"]).abs().sum() / chk["unidades"].sum()
    return bt, wape, chk


if __name__ == "__main__":
    bt, wape, chk = reconstruir()
    bt.to_csv(os.path.join(DATA, "backtest_semanal.csv"), index=False)
    por_cat = chk.groupby("categoria").apply(
        lambda d: (d["unidades"] - d["prediccion"]).abs().sum() / d["unidades"].sum())
    print(f"WAPE global: {wape:.3f}")
    print(por_cat.round(3).to_string())
