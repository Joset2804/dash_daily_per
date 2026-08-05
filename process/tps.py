# process/tps.py
import os
import yaml
import pytz
import pandas as pd
from datetime import datetime

# Carga la configuración desde config.yaml
def _load_config() -> dict:

    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# Lectura del Excel de TPs y verificación de impacto (True="si")
def _hay_tp_con_impacto(fecha: str, cfg: dict) -> bool:

    tps_cfg = cfg["tps"]
    archivo = tps_cfg["archivo"]
    hoja    = tps_cfg["hoja"]

    df = pd.read_excel(archivo, sheet_name=hoja)
    df["PLANIFICADO"]  = pd.to_datetime(df["PLANIFICADO"], errors="coerce")
    df["impacto_norm"] = df["IMPACTO"].astype(str).str.strip().str.lower()

    fecha_dt   = pd.Timestamp(fecha).date()
    df_dia     = df[df["PLANIFICADO"].dt.date == fecha_dt]
    df_impacto = df_dia[df_dia["impacto_norm"] == "si"]

    return len(df_impacto) > 0

# Se lee la hora directamente de la marca de tiempo en ms, sin conversión de zona horaria
def _hora_chile(timestamp_ms: int) -> int:

    return datetime.utcfromtimestamp(timestamp_ms / 1000).hour


# Corrección de la timeseries según la ventana de mantenimiento y el valor mínimo de disponibilidad
"""
Para cada hora dentro de la ventana de mantenimiento:
  - valor < disponibilidad_correccion → forzar al valor mínimo
  - valor >= disponibilidad_correccion → dejar igual
Fuera de la ventana → no tocar.
"""
def _corregir_timeseries(timeseries: list, cfg: dict) -> list:

    tps_cfg     = cfg["tps"]
    hora_inicio = tps_cfg["ventana_mantenimiento"]["hora_inicio"]
    hora_fin    = tps_cfg["ventana_mantenimiento"]["hora_fin"]
    val_min     = tps_cfg["disponibilidad_correccion"]

    resultado = []
    for ts_ms, valor in timeseries:
        hora = _hora_chile(ts_ms)
        if hora_inicio <= hora < hora_fin and valor < val_min:
            resultado.append((ts_ms, val_min))
        else:
            resultado.append((ts_ms, valor))
    return resultado

# Evalúa si existe un TP con impacto para la fecha y aplica la corrección correspondiente
def aplicar_tps(
    timeseries:         list,
    disponibilidad_api: float,
    fecha:              str,
) -> tuple:
    """
    Evalúa si existe un TP con impacto para la fecha y aplica
    la corrección correspondiente.

    Args:
        timeseries:         [(timestamp_ms, valor), ...] de fetch_timeseries()
        disponibilidad_api: metric_6323436ccf03 directo de la API
        fecha:              "YYYY-MM-DD"

    Returns:
        (timeseries_final, disponibilidad_final, hay_impacto)

        - timeseries_final:     lista corregida o sin cambios
        - disponibilidad_final: promedio de horas corregidas o valor API
        - hay_impacto:          True si hubo corrección
    """
    cfg = _load_config()

    hay_impacto = _hay_tp_con_impacto(fecha, cfg)

    if not hay_impacto:
        print(f"[TPS] {fecha}: sin TPs con impacto — usando disponibilidad API: {disponibilidad_api}%")
        return timeseries, disponibilidad_api, False

    # Corregir timeseries
    ts_corregida = _corregir_timeseries(timeseries, cfg)

    # Nueva disponibilidad = promedio simple de las 24 horas corregidas
    valores = [v for _, v in ts_corregida]
    disponibilidad_corregida = round(sum(valores) / len(valores), 4)

    print(f"[TPS] {fecha}: TP con impacto detectado")
    print(f"[TPS] Disponibilidad API={disponibilidad_api}% → corregida={disponibilidad_corregida}%")

    return ts_corregida, disponibilidad_corregida, True

# Retorna la lista de TPs del día para mostrar en el dashboard
def get_tps_display(fecha: str, cfg: dict = None) -> list:

    if cfg is None:
        cfg = _load_config()

    tps_cfg = cfg["tps"]
    df = pd.read_excel(tps_cfg["archivo"], sheet_name=tps_cfg["hoja"])
    df["PLANIFICADO"]  = pd.to_datetime(df["PLANIFICADO"], errors="coerce")
    df["impacto_norm"] = df["IMPACTO"].astype(str).str.strip().str.lower()

    fecha_dt   = pd.Timestamp(fecha).date()
    df_dia     = df[df["PLANIFICADO"].dt.date == fecha_dt]
    df_impacto = df_dia[df_dia["impacto_norm"] == "si"]

    resultado = []
    for _, row in df_impacto.iterrows():
        planificado = row["PLANIFICADO"]
        resultado.append({
            "fecha":  planificado.strftime("%d/%m/%Y · %H:%M"),
            "id":     str(row["TP"]),
            "titulo": str(row["TITULO"]),
        })
    return resultado