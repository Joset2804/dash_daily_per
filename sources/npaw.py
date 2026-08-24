# sources/npaw.py
import json
import requests
import urllib3
import yaml
from dotenv import load_dotenv
from datetime import datetime
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()


# Configuración
def _load_config() -> dict:

    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# GET al endpoint NPAW (reintenta hasta 3 veces ante fallos)
def _get(params: list, cfg: dict) -> dict:

    base_url = cfg["npaw"]["base_url"]
    api_key  = os.getenv("NPAW_API_KEY", "")
    headers  = {"npaw-api-key": api_key}

    last_exc = None
    for attempt in range(3):
        try:
            r = requests.get(
                base_url,
                headers=headers,
                params=params,
                verify=False,
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                import time
                time.sleep(1)
    raise last_exc


# Construye el filtro JSON a partir de config.yaml
# Lee cualquier dimensión en filtros.rules y filtros.exclude
def _build_filter(cfg: dict) -> str:

    filtros = cfg["npaw"]["filtros"]
    rules   = {}

    # Inclusiones — tal cual están en el YAML
    for dimension, values in filtros.get("rules", {}).items():
        rules[dimension] = values

    # Exclusiones — NPAW las recibe con prefijo "-"
    for dimension, values in filtros.get("exclude", {}).items():
        rules[f"-{dimension}"] = values

    filtro = {
        "name":  "filtro_general",
        "rules": rules,
    }
    return json.dumps([filtro])


# Parseo de la respuesta JSON de NPAW (granularity=total)
def _parse_flat(raw: dict) -> dict:

    result  = {}
    metrics = raw.get("data", [{}])[0].get("metrics", [])
    for m in metrics:
        code = m.get("code")
        try:
            value = m["values"][0]["data"][0]["value"]
        except (KeyError, IndexError, TypeError):
            value = None
        result[code] = value
    return result

# Parseo de la respuesta JSON de NPAW (granularity=hour)
def _parse_timeseries(raw: dict) -> list[tuple]:

    try:
        data = raw["data"][0]["metrics"][0]["values"][0]["data"]
        return [(int(pair[0]), float(pair[1])) for pair in data if pair[1] is not None]
    except (KeyError, IndexError, TypeError):
        return []

# Parseo de la respuesta JSON de NPAW (errores agrupados por código)
def _parse_errores(raw: dict) -> list[dict]:

    try:
        values = raw["data"][0]["metrics"][0]["values"]
        return [
            {"codigo": v.get("error_name"), "cantidad": v.get("value", 0)}
            for v in values
        ]
    except (KeyError, IndexError, TypeError):
        return []

#-------------------------------------------
# Funciones API NPAW
#-------------------------------------------

# KPIs totales del período
def fetch_kpis(fecha_desde: str, fecha_hasta: str) -> dict:

    cfg = _load_config()

    metricas = ",".join(cfg["npaw"]["kpis"]["metricas"])
    params = [
        ("fromDate",    f"{fecha_desde} 00:00:00"),
        ("toDate",      f"{fecha_hasta} 23:59:59"),
        ("metrics",     metricas),
        ("granularity", cfg["npaw"]["kpis"]["granularity"]),
        ("filter",      _build_filter(cfg)),
    ]

    raw  = _get(params, cfg)
    kpis = _parse_flat(raw)
    print(f"[NPAW] KPIs {fecha_desde} → {fecha_hasta}: {kpis}")
    return kpis

# Disponibilidad hora a hora para el gráfico
def fetch_timeseries(fecha_desde: str, fecha_hasta: str) -> list[tuple]:

    cfg = _load_config()

    metricas = ",".join(cfg["npaw"]["timeseries"]["metricas"])
    params = [
        ("fromDate",    f"{fecha_desde} 00:00:00"),
        ("toDate",      f"{fecha_hasta} 23:59:59"),
        ("metrics",     metricas),
        ("granularity", cfg["npaw"]["timeseries"]["granularity"]),
        ("filter",      _build_filter(cfg)),
    ]

    raw    = _get(params, cfg)
    puntos = _parse_timeseries(raw)
    print(f"[NPAW] Timeseries {fecha_desde} → {fecha_hasta}: {len(puntos)} puntos")
    return puntos

# Errores agrupados por código para calcular el desglose del gap
def fetch_errores_por_codigo(fecha_desde: str, fecha_hasta: str) -> list[dict]:
    
    cfg = _load_config()

    params = [
        ("fromDate",        f"{fecha_desde} 00:00:00"),
        ("toDate",          f"{fecha_hasta} 23:59:59"),
        ("metrics",         "errors"),
        ("groupBy",         "error_name"),
        ("orderBy",         "errors"),
        ("orderDirection",  "desc"),
        ("limit",           "100"),
        ("filter",          _build_filter(cfg)),
    ]

    raw     = _get(params, cfg)
    errores = _parse_errores(raw)
    print(f"[NPAW] Errores por código {fecha_desde} → {fecha_hasta}: {len(errores)} códigos")
    return errores

# Timeseries por día, retorna las métricas configuradas en config.yaml (granularity=day)
def fetch_timeseries_dia(fecha_desde: str, fecha_hasta: str) -> dict:

    cfg      = _load_config()
    metricas = ",".join(cfg["npaw"]["timeseries_dia"]["metricas"])

    params = [
        ("fromDate",    f"{fecha_desde} 00:00:00"),
        ("toDate",      f"{fecha_hasta} 23:59:59"),
        ("metrics",     metricas),
        ("granularity", cfg["npaw"]["timeseries_dia"]["granularity"]),
        ("filter",      _build_filter(cfg)),
    ]

    raw     = _get(params, cfg)
    metrics = raw.get("data", [{}])[0].get("metrics", [])

    resultado = {}
    for m in metrics:
        code   = m.get("code")
        puntos = m.get("values", [{}])[0].get("data", [])
        resultado[code] = [
            (datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d"), valor)
            for ts, valor in puntos
        ]

    print(f"[NPAW] Timeseries día {fecha_desde} → {fecha_hasta}: "
          f"{len(resultado)} métricas")
    return resultado

# Top canales con más errores para una hora específica (identificar la causa de peaks de disponibilidad)
def fetch_canales_por_hora(fecha: str, hora: int) -> list[dict]:

    cfg = _load_config()

    # Construir rango de esa hora exacta
    hora_str      = f"{hora:02d}:00:00"
    hora_fin_str  = f"{hora:02d}:59:59"
    from_date     = f"{fecha} {hora_str}"
    to_date       = f"{fecha} {hora_fin_str}"

    params = [
        ("fromDate",       from_date),
        ("toDate",         to_date),
        ("metrics",        "errors"),
        ("groupBy",        "content_channel"),
        ("orderBy",        "errors"),
        ("orderDirection", "desc"),
        ("limit",          "10"),
        ("filter",         _build_filter(cfg)),
    ]

    raw = _get(params, cfg)

    # Parsear respuesta agrupada
    try:
        values = raw["data"][0]["metrics"][0]["values"]
    except (KeyError, IndexError):
        return []

    # Calcular total para el porcentaje
    total = sum(v.get("value", 0) for v in values)
    if total == 0:
        return []

    return [
        {
            "canal":   v.get("content_channel", "Desconocido"),
            "errores": v.get("value", 0),
            "pct":     round(v.get("value", 0) / total * 100, 1),
        }
        for v in values
        if v.get("value", 0) > 0
    ]

# Errores agrupados por código para una hora específica
def fetch_errores_por_hora(fecha: str, hora: int) -> list[dict]:

    cfg = _load_config()
    params = [
        ("fromDate",        f"{fecha} {hora:02d}:00:00"),
        ("toDate",          f"{fecha} {hora:02d}:59:59"),
        ("metrics",         "errors"),
        ("groupBy",         "error_name"),
        ("orderBy",         "errors"),
        ("orderDirection",  "desc"),
        ("limit",           "100"),
        ("filter",          _build_filter(cfg)),
    ]
    raw     = _get(params, cfg)
    errores = _parse_errores(raw)
    print(f"[NPAW] Errores por código {fecha} {hora:02d}:00: {len(errores)} códigos")
    return errores

# Errores agrupados por una dimensión para una hora específica (content_channel, device, app_release_version)
def fetch_por_dimension_hora(
    fecha:     str,
    hora:      int,
    dimension: str,
    top:       int = 3,
) -> list[dict]:

    cfg = _load_config()
    params = [
        ("fromDate",        f"{fecha} {hora:02d}:00:00"),
        ("toDate",          f"{fecha} {hora:02d}:59:59"),
        ("metrics",         "errors"),
        ("groupBy",         dimension),
        ("orderBy",         "errors"),
        ("orderDirection",  "desc"),
        ("limit",           "50"),
        ("filter",          _build_filter(cfg)),
    ]

    raw = _get(params, cfg)

    try:
        values = raw["data"][0]["metrics"][0]["values"]
    except (KeyError, IndexError, TypeError):
        return []

    # Extraer pares (nombre, cantidad) ignorando ceros
    items = [
        {"nombre": v.get(dimension, "Desconocido"), "errores": v.get("value", 0)}
        for v in values
        if v.get("value", 0) > 0
    ]

    if not items:
        return []

    total = sum(i["errores"] for i in items)
    if total == 0:
        return []

    individuales = items[:top]
    remanentes   = items[top:]

    if len(remanentes) == 1:
        individuales.append(remanentes[0])
        remanentes = []

    resultado = [
        {
            "nombre":   i["nombre"],
            "errores":  i["errores"],
            "pct":      round(i["errores"] / total * 100, 1),
            "es_otros": False,
        }
        for i in individuales
    ]

    if remanentes:
        errores_otros = sum(r["errores"] for r in remanentes)
        resultado.append({
            "nombre":   f"Otros ({len(remanentes)})",
            "errores":  errores_otros,
            "pct":      round(errores_otros / total * 100, 1),
            "es_otros": True,
        })

    print(f"[NPAW] {dimension} {fecha} {hora:02d}:00: "
          f"{len(resultado)} ítems (total {total} errores)")
    return resultado