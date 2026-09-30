# process/tps.py
import os
import yaml
import pytz
import pandas as pd
from datetime import datetime
from process.ventanas import get_ventanas_dia, correccion_para_hora

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


# Aplica la corrección de disponibilidad a las horas que caen dentro
# de alguna ventana de mantenimiento del día.
# Si una hora cae en varias ventanas solapadas, aplica la corrección más alta.
def _corregir_timeseries(timeseries: list, ventanas: list) -> list:

    resultado = []
    for ts_ms, valor in timeseries:
        hora       = _hora_chile(ts_ms)
        correccion = correccion_para_hora(hora, ventanas)

        if correccion is not None and valor < correccion:
            resultado.append((ts_ms, correccion))
        else:
            resultado.append((ts_ms, valor))
    return resultado

# Evalúa si existe un TP con impacto para la fecha y aplica la corrección correspondiente
"""
Evalúa las ventanas de mantenimiento del día (TP del Excel + ventanas extra)
y aplica la corrección correspondiente.

Returns:
    (timeseries_final, disponibilidad_final, hay_ventanas, ventanas)

    - timeseries_final:     lista corregida o sin cambios
    - disponibilidad_final: promedio de horas corregidas, o valor API si no hay ventanas
    - hay_ventanas:         True si hubo al menos una ventana
    - ventanas:             lista de ventanas del día (para propagar al resto del pipeline)
"""
def aplicar_tps(
    timeseries:         list,
    disponibilidad_api: float,
    fecha:              str,
) -> tuple:

    cfg = _load_config()

    hay_tp   = _hay_tp_con_impacto(fecha, cfg)
    ventanas = get_ventanas_dia(fecha, hay_tp, cfg)

    if not ventanas:
        print(f"[TPS] {fecha}: sin ventanas de mantención — "
              f"usando disponibilidad API: {disponibilidad_api}%")
        return timeseries, disponibilidad_api, False, []

    # Log de las ventanas detectadas
    for v in ventanas:
        print(f"[TPS] {fecha}: ventana {v['inicio']:02d}:00–{v['fin'] - 1:02d}:59 "
              f"({v['tipo']}) → corrección {v['correccion']}%")

    ts_corregida = _corregir_timeseries(timeseries, ventanas)

    valores = [v for _, v in ts_corregida]
    disponibilidad_corregida = round(sum(valores) / len(valores), 4)

    print(f"[TPS] {fecha}: disponibilidad API={disponibilidad_api}% "
          f"→ corregida={disponibilidad_corregida}%")

    return ts_corregida, disponibilidad_corregida, True, ventanas

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