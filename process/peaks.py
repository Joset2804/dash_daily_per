import os
import yaml
from datetime import datetime

# Cargar configuración
def _load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

# Función auxiliar para convertir timestamp_ms a hora UTC
def _ts_a_hora(timestamp_ms: int) -> int:

    return datetime.utcfromtimestamp(timestamp_ms / 1000).hour

# Retorna True si la hora está dentro de la ventana de mantenimiento
def _hora_en_ventana(hora: int, cfg: dict) -> bool:
    
    inicio = cfg["tps"]["ventana_mantenimiento"]["hora_inicio"]
    fin    = cfg["tps"]["ventana_mantenimiento"]["hora_fin"]
    return inicio <= hora < fin

# Detecta el peak horario más bajo del día por debajo del umbral
# Excluyendo horas de ventana de mantenimiento si hay TP
#def detectar_peak_diario(
#    timeseries: list,
#    hay_tp:     bool,
#    umbral:     float = 99.70,
#) -> dict | None:
#
#    cfg = _load_config()
#
#    candidatos = []
#    for ts_ms, valor in timeseries:
#        if valor >= umbral:
#            continue
#        hora = _ts_a_hora(ts_ms)
#        if hay_tp and _hora_en_ventana(hora, cfg):
#            continue
#        fecha = datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")
#        candidatos.append({"fecha": fecha, "hora": hora, "disponibilidad": valor})
#
#    if not candidatos:
#        return None
#
#    peak = min(candidatos, key=lambda x: x["disponibilidad"])
#    print(f"[PEAKS] Peak diario detectado: {peak['fecha']} "
#          f"{peak['hora']:02d}:00 → {peak['disponibilidad']}%")
#    return peak

# Detecta los peaks horario más bajo del día por debajo del umbral
# Excluyendo horas de ventana de mantenimiento si hay TP
def detectar_peak_diario(
    timeseries: list,
    hay_tp:     bool,
    umbral:     float = 99.70,
    max_peaks:  int   = 3,
) -> list:

    cfg = _load_config()

    candidatos = []
    for ts_ms, valor in timeseries:
        if valor >= umbral:
            continue
        hora = _ts_a_hora(ts_ms)
        if hay_tp and _hora_en_ventana(hora, cfg):
            continue
        fecha = datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")
        candidatos.append({"fecha": fecha, "hora": hora, "disponibilidad": valor})

    if not candidatos:
        return []

    # Ordenar de menor a mayor disponibilidad y tomar los N peores
    peaks = sorted(candidatos, key=lambda x: x["disponibilidad"])[:max_peaks]

    for p in peaks:
        print(f"[PEAKS] Peak diario detectado: {p['fecha']} "
              f"{p['hora']:02d}:00 → {p['disponibilidad']}%")
    return peaks

# Detecta el peak horario más bajo de cada día del período por debajo del umbral
# Excluyendo horas de ventana de mantenimiento si hay TP
def detectar_peaks_periodo(
    disp_por_dia:  list,
    ts_hora_raw:   list,
    dias_con_tp:   set,
    umbral:        float = 99.70,
) -> list:

    cfg = _load_config()

    # Agrupar timeseries horaria por día
    por_dia = {}
    for ts_ms, valor in ts_hora_raw:
        fecha = datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")
        hora  = datetime.utcfromtimestamp(ts_ms / 1000).hour
        if fecha not in por_dia:
            por_dia[fecha] = []
        por_dia[fecha].append((hora, valor))

    peaks = []
    for fecha, disp_dia in disp_por_dia:
        if disp_dia >= umbral:
            continue

        # Buscar el peak horario más bajo de ese día
        horas_dia = por_dia.get(fecha, [])
        candidatos = []
        for hora, valor in horas_dia:
            if valor >= umbral:
                continue
            # Si tiene TP, excluir horas de ventana de mantenimiento
            if fecha in dias_con_tp and _hora_en_ventana(hora, cfg):
                continue
            candidatos.append({"fecha": fecha, "hora": hora, "disponibilidad": valor})

        if not candidatos:
            if not horas_dia:
                print(f"[PEAKS] {fecha}: peak diario {disp_dia}% pero "
                      f"sin datos horarios disponibles")
            else:
                print(f"[PEAKS] {fecha}: peak diario {disp_dia}% pero "
                      f"sin horas válidas fuera de ventana")
            continue

        peak = min(candidatos, key=lambda x: x["disponibilidad"])
        peaks.append(peak)
        print(f"[PEAKS] Peak período detectado: {peak['fecha']} "
              f"{peak['hora']:02d}:00 → {peak['disponibilidad']}%")

    return peaks