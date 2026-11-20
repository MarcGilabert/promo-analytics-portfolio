"""Demo por linea de comandos: una ejecucion verde y una bloqueada."""
from agent import responder


def mostrar(r):
    print("\n" + "=" * 70)
    print("PREGUNTA:", r["pregunta"])
    print("DECISION:", r["decision"], " | audit:", r["audit_id"])
    print("-" * 70)
    for regla, estado, msg in r["veredictos"]:
        marca = {"pass": "[OK ]", "warn": "[AV ]", "block": "[BLK]"}[estado]
        print(f"  {marca} {regla}: {msg}")
    print("-" * 70)
    print("CONCLUSION:", r["conclusion"])


if __name__ == "__main__":
    # El agente elige la tool segun la pregunta.
    mostrar(responder("¿Cuánto venderé de leche la próxima semana?"))      # -> forecast, verde
    mostrar(responder("¿Cuánto venderé de leche en las próximas 4 semanas?"))  # -> aviso: horizonte no validado
    mostrar(responder("¿Qué ROI tendrá una promo de leche?"))               # -> roi
    mostrar(responder("¿Y de sopa cuánto venderé en 4 semanas?"))           # -> forecast + aviso
    mostrar(responder("¿Qué ROI tendrá una promo de cervezas?"))            # -> bloqueo (sin datos)
    mostrar(responder("Optimiza el programa de promociones del próximo mes con 1.000 €"))

    # Paso 3: comparacion de escenarios (aun sin pasar por el agente).
    from scenarios import compare_scenarios
    actual = [{"semana": w, "categoria": c} for w in (1, 2) for c in ("CHEESE", "SOFT DRINKS",
                                                                       "BAG SNACKS")]
    r = compare_scenarios(1000, 4, calendario_actual=actual,
                          alternativa={"max_promos_categoria": 4})
    print("\n" + "=" * 70)
    print("ESCENARIOS · objetivo:", r["metadata"]["objetivo_descripcion"])
    cab = ["promos", "unid. inc", "ventas €", "coste €", "dto. €", "viable"]
    print(f"{'':12}" + "".join(f"{c:>10}" for c in cab) + "   benef. ilustrativo €")
    for e in r["resultado"]["escenarios"]:
        m = e["metricas"]
        b = m["beneficio_ilustrativo_eur"]
        fila = [m["n_promociones"], m["unidades_incrementales"], m["ventas_incrementales_eur"],
                m["coste_eur"], m["descuento_total_eur"], "sí" if e["viable"] else "no"]
        print(f"{e['nombre']:12}" + "".join(f"{str(v):>10}" for v in fila)
              + f"   {b['bajo']} / {b['base']} / {b['alto']}")
    print("Beneficio ilustrativo con margen supuesto -5 pp / base / +5 pp: no es un criterio "
          "de optimizacion.")
    print("Ranking:", " > ".join(r["resultado"]["ranking"]))

    # Paso 4: motor de decision (aun sin pasar por el agente ni por la app).
    from decision_engine import recommend_promo_decision
    from policies import r_robustez, Contexto
    for objetivo in ("ventas", "volumen"):
        d = recommend_promo_decision(presupuesto_eur=1000, semanas=4, 
                                     objetivo=objetivo, calendario_actual=actual,
                                     alternativa=[{"mecanica": "folleto"},
                                                  {"max_promos_categoria": 4}])
        R = d["resultado"]
        rec, pq = R["recomendacion"], R["por_que"]
        print("\n" + "=" * 70)
        print(f"DECISION ({objetivo}) · estado: {R['estado']}")
        print(f"Recomendado: {rec['escenario']} — {rec['descripcion']}")
        print(f"  valor del objetivo {rec['valor_objetivo']}; ventaja frente a "
              f"{pq['segundo']}: {pq['ventaja_vs_segundo']}; frente al actual: "
              f"{pq['ventaja_vs_actual']}")
        print("  compromisos:", ", ".join(f"{c['metrica']} {c['diferencia']:+}"
                                         for c in R["compromisos"]) or "ninguno")
        print("  beneficio ilustrativo (-5pp/base/+5pp):",
              " / ".join(str(v) for v in R["robustez"]["margen"]["beneficio_ilustrativo_eur"].values()))
        for c in R["supuestos_criticos"]:
            print(f"  supuesto critico {c['supuesto']}: {c['efecto']} (umbral {c['umbral']})")
        v = r_robustez(Contexto("", [d]))
        print(f"  politica de robustez: {v.estado} — {v.mensaje}")

    # Paso 5: registro de la decision (propuesta -> aprobada, con motivo y huella).
    import decision_record as dr
    from policies import evaluar, POLICY_VERSION
    d = recommend_promo_decision(presupuesto_eur=1000, semanas=4, 
                                 objetivo="volumen", alternativa={"max_promos_categoria": 4})
    rob = r_robustez(Contexto("", [d]))
    reg = dr.crear(d, {"decision": "ENTREGAR" if rob.estado == "pass" else "ENTREGAR_CON_AVISO",
                       "veredictos": [(rob.regla, rob.estado, rob.mensaje)],
                       "policy_version": POLICY_VERSION}, creado_por="demo")
    reg = dr.cambiar_estado(reg["decision_id"], "aprobada", "demo",
                            "volumen prioritario confirmado",
                            avisos_reconocidos=True)
    print("\n" + "=" * 70)
    print(f"REGISTRO {reg['decision_id']} · estado {reg['estado']} · huella {reg['huella'][:12]}…")
    for h in reg["historial"]:
        print(f"  {h['fecha']}  {h['de']} -> {h['a']}  ({h['usuario']}: {h['motivo']})")
    print("  reproducible:", dr.reproducir(reg["decision_id"])["reproducible"])
