import os
import pandas as pd
import yaml
from decimal import Decimal, ROUND_HALF_UP

# Carga el config.yaml y retorna un dict
def _load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

# Carga el CSV de lookup de errores y retorna un dict {codigo: (macro, sub)}
def _load_lookup() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "error_lookup.csv")
    df   = pd.read_csv(path, dtype=str).fillna("")

    lookup = {}
    for _, row in df.iterrows():
        code  = str(row["error_code"]).strip().replace(" | ", "|").replace(" / ", "|")
        macro = row["macro"].strip() or None
        sub   = row["sub"].strip()   or None
        desc  = row["descripcion"].strip() or ""
        lookup[code] = (macro, sub, desc)
    return lookup


# Clasifica un código de error en (macro, sub) según el lookup y reglas definidas
"""
    Orden de búsqueda:
      1. Exacto en lookup
      2. Si tiene "|", buscar solo el prefijo en lookup
      3. Si es numérico entre 4000-6009  →  INTERNOS / INTERNOS
      4. Nada encontrado                 →  EXCLUIR

    Retorna (None, None) para EXCLUIR.
"""
def _clasificar(codigo: str, lookup: dict) -> tuple:

    if not codigo:
        return (None, None, "")

    # Normalizar separadores
    code = str(codigo).strip().replace(" | ", "|").replace(" / ", "|")

    # 1. Exacto
    if code in lookup:
        macro, sub, desc = lookup[code]
        return (None, None, "") if macro == "EXCLUIR" else (macro, sub, desc)

    # 2. Prefijo (compound codes)
    if "|" in code:
        prefix = code.split("|")[0]
        if prefix in lookup:
            macro, sub, desc = lookup[prefix]
            return (None, None, "") if macro == "EXCLUIR" else (macro, sub, desc)

    # 3. Rango numérico SSP/OPF
    try:
        n = int(code.split("|")[0])
        if 4000 <= n <= 6009:
            return ("INTERNOS", "INTERNOS", "Error backend SSP/OPF (rango 4000-6009)")
    except ValueError:
        pass

    # 4. No clasificado → excluir
    return (None, None, "")


# Calcula el gap de disponibilidad por subcategoría a partir de la lista de errores y la disponibilidad total
"""
Args:
    errores: lista de {"codigo": str, "cantidad": int}
             (salida de fetch_errores_por_codigo)
    disponibilidad: valor float de metric_6323436ccf03 (ej. 99.799)

    Returns:
        {
            "gap_total":    0.201,
            "FIBRA":        0.045,
            "HOMENETWORKING": 0.012,
            "SENALES":      0.038,
            "INTERNOS":     0.071,
            "ZAPPING":      0.035,
        }
"""
def calcular_gap(errores: list[dict], disponibilidad: float) -> dict:

    lookup    = _load_lookup()

    disp_redondeada = float(Decimal(str(disponibilidad)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    gap_total = float(Decimal(str(round(100 - disp_redondeada, 2))))

    # Acumular cantidades por subcategoría
    conteo = {
        "FIBRA":          0,
        "HOMENETWORKING": 0,
        "SENALES":        0,
        "INTERNOS":       0,
        "ZAPPING":        0,
    }

    for item in errores:
        codigo   = item.get("codigo", "")
        cantidad = item.get("cantidad", 0)
        macro, sub, _ = _clasificar(codigo, lookup)

        if macro is None or sub is None:
            continue  # EXCLUIR

        if sub in conteo:
            conteo[sub] += cantidad

    total_clasificable = sum(conteo.values())

    # Calcular proporción del gap para cada subcategoría
    resultado = {"gap_total": gap_total}

    if total_clasificable == 0:
        for sub in conteo:
            resultado[sub] = 0.0
    else:
        for sub, cantidad in conteo.items():
            resultado[sub] = round(
                gap_total * (cantidad / total_clasificable), 4
            )

    print(f"[GAP] total={gap_total}% | clasificables={total_clasificable} errores")
    print(f"[GAP] {resultado}")
    return resultado

# Desglose Pareto de causas individuales por cada subcategoría del GAP
"""
Args:
    errores:        lista de {"codigo": str, "cantidad": int}
    disponibilidad: valor float de metric_6323436ccf03
    cfg:            config.yaml ya cargado (opcional)

Returns:
    {
      "FIBRA": [
        {
          "codigo":        "4021",
          "descripcion":   "Error de conectividad...",
          "gap":           0.051,
          "participacion": 49.0,
          "acumulado":     49.0,
          "es_otros":      False,
        },
        ...
      ],
      "SENALES":  [...],
      "INTERNOS": [...],
      ...
    }
"""
def calcular_desglose_causas(
    errores:        list[dict],
    disponibilidad: float,
    cfg:            dict = None,
) -> dict:

    if cfg is None:
        cfg = _load_config()

    desglose_cfg = cfg.get("desglose_causas", {})
    max_causas   = desglose_cfg.get("max_causas_por_categoria", 3)
    umbral_otros = desglose_cfg.get("umbral_otros", 5.0)

    lookup = _load_lookup()

    # Mismo gap_total que usa calcular_gap
    disp_redondeada = float(
        Decimal(str(disponibilidad)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    gap_total = float(Decimal(str(round(100 - disp_redondeada, 2))))

    # Agrupar causas individuales por subcategoría
    por_categoria = {
        "FIBRA":          [],
        "HOMENETWORKING": [],
        "SENALES":        [],
        "INTERNOS":       [],
        "ZAPPING":        [],
    }

    total_clasificable = 0

    for item in errores:
        codigo   = item.get("codigo", "")
        cantidad = item.get("cantidad", 0)
        macro, sub, desc = _clasificar(codigo, lookup)

        if macro is None or sub is None:
            continue  # EXCLUIR

        if sub in por_categoria:
            por_categoria[sub].append({
                "codigo":      codigo,
                "descripcion": desc or "Sin descripción registrada",
                "cantidad":    cantidad,
            })
            total_clasificable += cantidad

    if total_clasificable == 0:
        return {sub: [] for sub in por_categoria}

    # Construir el desglose Pareto por categoría
    resultado = {}

    for sub, causas in por_categoria.items():
        if not causas:
            resultado[sub] = []
            continue

        # Ordenar de mayor a menor cantidad
        causas = sorted(causas, key=lambda x: x["cantidad"], reverse=True)
        total_categoria = sum(c["cantidad"] for c in causas)

        if total_categoria == 0:
            resultado[sub] = []
            continue

        # Separar individuales vs agrupadas
        individuales = []
        remanentes   = []

        for i, causa in enumerate(causas):
            participacion = causa["cantidad"] / total_categoria * 100

            fuera_del_top   = i >= max_causas
            bajo_el_umbral  = participacion < umbral_otros

            if fuera_del_top or bajo_el_umbral:
                remanentes.append(causa)
            else:
                individuales.append(causa)

        # Caso especial: si solo queda 1 remanente, mostrarlo individual
        if len(remanentes) == 1:
            individuales.append(remanentes[0])
            remanentes = []

        # Armar filas finales con gap, participación y acumulado
        filas     = []
        acumulado = 0.0

        for causa in individuales:
            participacion = round(causa["cantidad"] / total_categoria * 100, 1)
            gap_causa     = round(gap_total * (causa["cantidad"] / total_clasificable), 4)
            acumulado    += participacion
            filas.append({
                "codigo":        causa["codigo"],
                "descripcion":   causa["descripcion"],
                "gap":           gap_causa,
                "participacion": participacion,
                "acumulado":     round(acumulado, 1),
                "es_otros":      False,
            })

        # Bucket "Otros" solo si quedan 2 o más
        if len(remanentes) >= 2:
            cantidad_otros      = sum(c["cantidad"] for c in remanentes)
            participacion_otros = round(cantidad_otros / total_categoria * 100, 1)
            gap_otros           = round(gap_total * (cantidad_otros / total_clasificable), 4)
            acumulado          += participacion_otros
            filas.append({
                "codigo":        "OTROS",
                "descripcion":   f"{len(remanentes)} códigos adicionales con menor impacto",
                "gap":           gap_otros,
                "participacion": participacion_otros,
                "acumulado":     round(acumulado, 1),
                "es_otros":      True,
            })

        resultado[sub] = filas

    # Log resumen
    for sub, filas in resultado.items():
        if filas:
            print(f"[DESGLOSE] {sub}: {len(filas)} causas")

    return resultado