import os
import yaml
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sources.npaw import fetch_timeseries_dia, fetch_timeseries,_load_config

# Configuración
def _load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

# Función para redondear y promediar valores
def _redondear(valor: float, decimales: int = 2) -> float:
    q = Decimal("0." + "0" * decimales)
    return float(Decimal(str(valor)).quantize(q, rounding=ROUND_HALF_UP))

# Promedio de una lista de valores
def _promedio(valores: list) -> float:
    if not valores:
        return 0.0
    valores_redondeados = [
        float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        for v in valores
    ]
    resultado = sum(valores_redondeados) / len(valores_redondeados)
    return float(Decimal(str(resultado)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

# Funciones de conversión de timestamps
def _ts_a_fecha(timestamp_ms: int) -> str:

    return datetime.utcfromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d")

# Función para convertir timestamp a hora (0-23)
def _ts_a_hora(timestamp_ms: int) -> int:

    return datetime.utcfromtimestamp(timestamp_ms / 1000).hour

# Retorna set de fechas 'YYYY-MM-DD' que tienen al menos un TP con IMPACTO=si
def _get_dias_con_tp(fecha_desde: str, fecha_hasta: str, cfg: dict) -> set:
  
    tps_cfg = cfg["tps"]
    df = pd.read_excel(tps_cfg["archivo"], sheet_name=tps_cfg["hoja"])
    df["PLANIFICADO"]  = pd.to_datetime(df["PLANIFICADO"], errors="coerce")
    df["impacto_norm"] = df["IMPACTO"].astype(str).str.strip().str.lower()

    desde = pd.Timestamp(fecha_desde)
    hasta = pd.Timestamp(fecha_hasta)

    df_rango   = df[
        (df["PLANIFICADO"].dt.normalize() >= desde) &
        (df["PLANIFICADO"].dt.normalize() <= hasta)
    ]
    df_impacto = df_rango[df_rango["impacto_norm"] == "si"]

    return set(df_impacto["PLANIFICADO"].dt.strftime("%Y-%m-%d").unique())

# Funciones para obtener TPs con impacto en un período
def get_tps_display_periodo(fecha_desde: str, fecha_hasta: str, cfg: dict = None) -> list:

    if cfg is None:
        cfg = _load_config()

    tps_cfg = cfg["tps"]
    df = pd.read_excel(tps_cfg["archivo"], sheet_name=tps_cfg["hoja"])
    df["PLANIFICADO"]  = pd.to_datetime(df["PLANIFICADO"], errors="coerce")
    df["impacto_norm"] = df["IMPACTO"].astype(str).str.strip().str.lower()

    desde = pd.Timestamp(fecha_desde)
    hasta = pd.Timestamp(fecha_hasta)

    df_rango   = df[
        (df["PLANIFICADO"].dt.normalize() >= desde) &
        (df["PLANIFICADO"].dt.normalize() <= hasta)
    ]
    df_impacto = df_rango[df_rango["impacto_norm"] == "si"].copy()
    df_impacto = df_impacto.sort_values("PLANIFICADO")

    resultado = []
    for _, row in df_impacto.iterrows():
        resultado.append({
            "fecha":  row["PLANIFICADO"].strftime("%d/%m/%Y · %H:%M"),
            "id":     str(row["TP"]),
            "titulo": str(row["TITULO"]),
        })
    return resultado


# Calcular disponibilidad promedio del período aplicando correcciones de TPs
def calcular_disponibilidad_periodo(
    fecha_desde: str,
    fecha_hasta: str,
) -> tuple:
    cfg         = _load_config()
    dias_con_tp = _get_dias_con_tp(fecha_desde, fecha_hasta, cfg)
    hay_tp      = len(dias_con_tp) > 0

    hora_inicio = cfg["tps"]["ventana_mantenimiento"]["hora_inicio"]
    hora_fin    = cfg["tps"]["ventana_mantenimiento"]["hora_fin"]
    val_min     = cfg["tps"]["disponibilidad_correccion"]

    # Fetch diario desde npaw.py
    ts_dia = fetch_timeseries_dia(fecha_desde, fecha_hasta)
    disp_por_dia_api = {
        fecha: valor
        for fecha, valor in ts_dia.get("metric_6323436ccf03", [])
    }

    # Fetch horario siempre: se usa para corregir días con TP y para detectar peaks
    ts_hora = fetch_timeseries(fecha_desde, fecha_hasta)
    por_dia_horas = {}
    for ts_ms, valor in ts_hora:
        fecha = datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")
        hora  = datetime.utcfromtimestamp(ts_ms / 1000).hour
        if fecha not in por_dia_horas:
            por_dia_horas[fecha] = []
        por_dia_horas[fecha].append((hora, valor))

    # Calcular disponibilidad por día
    disp_por_dia = []
    for fecha in sorted(disp_por_dia_api.keys()):
        if fecha in dias_con_tp and fecha in por_dia_horas:
            horas = por_dia_horas[fecha]
            horas_corregidas = [
                val_min if (hora_inicio <= h < hora_fin and v < val_min) else v
                for h, v in horas
            ]
            valor_dia = _redondear(_promedio(horas_corregidas), 2)
            print(f"[PERIODO] {fecha}: disp={valor_dia}% (corregido)")
        else:
            valor_dia = _redondear(disp_por_dia_api[fecha], 2)
            print(f"[PERIODO] {fecha}: disp={valor_dia}% (API)")

        disp_por_dia.append((fecha, valor_dia))

    disp_final = _promedio([v for _, v in disp_por_dia])
    print(f"[PERIODO] Disponibilidad período: {disp_final}%")

    return disp_final, disp_por_dia, dias_con_tp, hay_tp, ts_hora

# Calcular Launcher promedio del período usando granularity=day
def calcular_launcher_periodo(
    fecha_desde: str,
    fecha_hasta: str,
) -> tuple:
    ts_dia = fetch_timeseries_dia(fecha_desde, fecha_hasta)
    launcher_por_dia = ts_dia.get("metric_dbbf01e41a88", [])
    launcher_final   = _promedio([v for _, v in launcher_por_dia])
    print(f"[PERIODO] Launcher promedio: {launcher_final}%")
    return launcher_final, launcher_por_dia