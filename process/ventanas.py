import os
import json
import yaml

# Configuración
def _load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

# Cargar ventanas extraordinarias desde un JSON
def _cargar_extras(fecha: str, cfg: dict) -> list:

    ruta = cfg["tps"]["ventanas_extra"]["archivo"]
    if not os.path.exists(ruta):
        return []

    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[VENTANAS] No se pudo leer {ruta}: {exc}")
        return []

    correccion = cfg["tps"]["ventanas_extra"]["disponibilidad_correccion_extra"]

    ventanas = []
    for v in data:
        if v.get("fecha") != fecha:
            continue
        ventanas.append({
            "inicio":      int(v["hora_inicio"]),
            "fin":         int(v["hora_fin"]),
            "correccion":  correccion,
            "tipo":        v.get("tipo", "mantenimiento"),
            "descripcion": v.get("descripcion", ""),
            "tp":          v.get("tp"),
            "origen":      "extra",
        })
    return ventanas

# Función principal: obtener las ventanas de un día
def get_ventanas_dia(fecha: str, hay_tp: bool, cfg: dict = None) -> list:

    if cfg is None:
        cfg = _load_config()

    ventanas = []

    # Ventana fija del Excel — solo si el día tiene TP con impacto
    if hay_tp:
        ventanas.append({
            "inicio":      cfg["tps"]["ventana_mantenimiento"]["hora_inicio"],
            "fin":         cfg["tps"]["ventana_mantenimiento"]["hora_fin"],
            "correccion":  cfg["tps"]["disponibilidad_correccion"],
            "tipo":        "tp_excel",
            "descripcion": "Ventana de mantención programada",
            "tp":          None,
            "origen":      "excel",
        })

    # Ventanas extraordinarias del JSON
    ventanas.extend(_cargar_extras(fecha, cfg))

    ventanas.sort(key=lambda v: v["inicio"])
    return ventanas

# Función que retorna la corrección que aplica a una hora, o None si no está en ninguna ventana.
def correccion_para_hora(hora: int, ventanas: list) -> float | None:

    aplicables = [
        v["correccion"] for v in ventanas
        if v["inicio"] <= hora < v["fin"]
    ]
    return max(aplicables) if aplicables else None

# Función que retorna True si la hora está dentro de alguna ventana, False si no
def hora_en_ventana(hora: int, ventanas: list) -> bool:

    return any(v["inicio"] <= hora < v["fin"] for v in ventanas)

# Calcula los rangos horarios del día que quedan FUERA de todas las ventanas.
def rangos_fuera_ventana(fecha: str, ventanas: list) -> list:

    if not ventanas:
        return [(f"{fecha} 00:00:00", f"{fecha} 23:59:59")]

    # Marcar qué horas están cubiertas
    cubiertas = set()
    for v in ventanas:
        for h in range(max(0, v["inicio"]), min(24, v["fin"])):
            cubiertas.add(h)

    libres = [h for h in range(24) if h not in cubiertas]
    if not libres:
        return []

    # Agrupar horas consecutivas en rangos
    rangos  = []
    inicio  = libres[0]
    anterior = libres[0]

    for h in libres[1:]:
        if h != anterior + 1:
            rangos.append((inicio, anterior))
            inicio = h
        anterior = h
    rangos.append((inicio, anterior))

    return [
        (f"{fecha} {ini:02d}:00:00", f"{fecha} {fin:02d}:59:59")
        for ini, fin in rangos
    ]

# Devuelve las ventanas extra de un rango de fechas, para
# mostrarse en la card de trabajos junto a los TPs del Excel
def get_ventanas_extra_display(
    fecha_desde: str,
    fecha_hasta: str = None,
    cfg:         dict = None,
) -> list:

    if cfg is None:
        cfg = _load_config()
    if fecha_hasta is None:
        fecha_hasta = fecha_desde

    ruta = cfg["tps"]["ventanas_extra"]["archivo"]
    if not os.path.exists(ruta):
        return []

    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    colores = cfg["tps"]["ventanas_extra"]["colores"]

    salida = []
    for v in data:
        fecha = v.get("fecha", "")
        if not (fecha_desde <= fecha <= fecha_hasta):
            continue

        d, m, a = fecha[8:10], fecha[5:7], fecha[:4]
        tipo    = v.get("tipo", "mantenimiento")

        salida.append({
            "fecha":  f"{d}/{m}/{a} · {int(v['hora_inicio']):02d}:00–{int(v['hora_fin']):02d}:00",
            "id":     v.get("tp"),
            "titulo": v.get("descripcion", "Ventana de mantención extraordinaria"),
            "tipo":   tipo,
            "color":  colores.get(tipo, "#f59e0b"),
        })

    salida.sort(key=lambda x: x["fecha"])
    return salida