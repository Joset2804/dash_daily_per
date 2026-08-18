# render/template.py
import os
import base64
import yaml
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from decimal import Decimal, ROUND_HALF_UP

# Carga la configuración desde config.yaml
def _load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# Lee una imagen y retorna su contenido en base64
def _b64(img_path: str) -> str:

    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

## Formateo de valores para mostrar en el dashboard
#def _fmt_pct(valor: float, decimales: int = 3) -> str:
#
#    return f"{valor:.{decimales}f}".replace(".", ",") + "%"

# Formateo de valores para mostrar en el dashboard (99.792 → '99,79%' | 99.796 → '99,80%' — redondeo exacto)
def _fmt_pct(valor: float, decimales: int = 2) -> str:

    cuantizador = Decimal("0." + "0" * decimales)
    d = Decimal(str(valor)).quantize(cuantizador, rounding=ROUND_HALF_UP)
    return str(d).replace(".", ",") + "%"

# Formateo de valores numéricos para mostrar en el dashboard
def _fmt_num(valor: float) -> str:
    
    return f"{int(valor):,}".replace(",", ".")

# Formateo de valores de tiempo en milisegundos para mostrar en el dashboard
def _fmt_ms(segundos: float) -> str:
    
    return f"{int(segundos * 1000)}ms"


# Colorización de KPIs según thresholds definidos en config.yaml
def _color_var(
    valor:              float,
    verde_threshold:    float,
    rojo_threshold:     float,
    higher_is_better:   bool = False,
) -> str:

    if higher_is_better:
        if valor >= verde_threshold:
            return "var(--green)"
        elif valor >= rojo_threshold:
            return "var(--yellow)"
        else:
            return "var(--red)"
    else:
        if valor <= verde_threshold:
            return "var(--green)"
        elif valor <= rojo_threshold:
            return "var(--yellow)"
        else:
            return "var(--red)"

# Colorización de KPIs según thresholds definidos en config.yaml, para el caso de lower_is_better
def _sdot(valor: float, verde_threshold: float, rojo_threshold: float) -> str:

    color = _color_var(valor, verde_threshold, rojo_threshold, higher_is_better=False)
    return {
        "var(--green)":  "sdot-g",
        "var(--yellow)": "sdot-y",
        "var(--red)":    "sdot-r",
    }[color]

# Preparación del contexto para renderizar el dashboard
def _preparar_contexto(
    kpis:                 dict,
    ts_final:             list,
    disponibilidad_final: float,
    gap:                  dict,
    desglose_causas:      dict,
    tps_list:             list,
    fecha_desde:          str,
    hay_tp:               bool,
    peaks_data:           list,
    cfg:                  dict,
) -> dict:

    slo       = cfg["slo"]
    fecha_dt  = datetime.strptime(fecha_desde, "%Y-%m-%d")
    fecha_lbl = fecha_dt.strftime("%d/%m/%Y")

    # Disponibilidad
    disp = float(Decimal(str(disponibilidad_final)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) # 99.792 → 99.79 | 99.796 → 99.80 (antes del semáforo)
    disp_dot_color = _color_var(
        disp,
        verde_threshold  = slo["availability"]["verde"],
        rojo_threshold   = slo["availability"]["amarillo"],
        higher_is_better = True,
    )

    # Launcher (Restart Launcher %)
    launcher     = kpis.get("metric_dbbf01e41a88", 0)
    launcher_dot = _sdot(
        launcher,
        verde_threshold = slo["restart_launcher"]["amarillo"],
        rojo_threshold  = slo["restart_launcher"]["rojo"],
    )

    # Join Time (segundos → ms)
    join_time     = kpis.get("joinTime", 0)
    join_time_dot = _sdot(
        join_time,
        verde_threshold = slo["join_time"]["amarillo"],
        rojo_threshold  = slo["join_time"]["rojo"],
    )

    # In Stream Error
    in_stream     = kpis.get("inStreamError", 0)
    in_stream_dot = _sdot(
        in_stream,
        verde_threshold = slo["in_stream_error"]["amarillo"],
        rojo_threshold  = slo["in_stream_error"]["rojo"],
    )

    # Calidad de carga
    buffer    = kpis.get("bufferRatio", 0)
    rebuffered = kpis.get("rebufferedRatioG1n", 0)
    ebvs      = kpis.get("exits", 0)

    buffer_color    = _color_var(buffer,    slo["buffer_ratio"]["amarillo"],    slo["buffer_ratio"]["rojo"])
    rebuffered_color = _color_var(rebuffered, slo["rebuffered_plays"]["amarillo"], slo["rebuffered_plays"]["rojo"])
    ebvs_color      = _color_var(ebvs,      slo["ebvs"]["amarillo"],            slo["ebvs"]["rojo"])

    # Chart
    # NPAW devuelve timestamps como hora Chile expresada en UTC
    chart_labels = [
        datetime.utcfromtimestamp(ts / 1000).strftime("%H:%M")
        for ts, _ in ts_final
    ]
    chart_data = [round(v, 3) for _, v in ts_final]

    hora_inicio = cfg["tps"]["ventana_mantenimiento"]["hora_inicio"]
    hora_fin    = cfg["tps"]["ventana_mantenimiento"]["hora_fin"]

    chart_maint_indices = (
        [
            i for i, (ts, _) in enumerate(ts_final)
            if hora_inicio <= datetime.utcfromtimestamp(ts / 1000).hour < hora_fin
        ]
        if hay_tp else []
    )

    # Suscriptores
    subscribers    = kpis.get("subscribers", 0)
    unique_devices = kpis.get("uniqueDeviceIDs", 0)

    # Gap items dinámicos
    COLORES_GAP = {
        "FIBRA":          "#7c3aed",
        "HOMENETWORKING": "var(--blue-mid)",
        "SENALES":        "var(--accent)",
        "INTERNOS":       "var(--red)",
        "ZAPPING":        "#7c3aed", 
    }

    # Mismo color que COLORES_GAP pero en rgba semitransparente, para el fondo de la card del resumen
    COLORES_GAP_BG = {
        "FIBRA":          "rgba(124, 58, 237, 0.07)",
        "HOMENETWORKING": "rgba(51, 88, 255, 0.07)",
        "SENALES":        "rgba(255, 102, 0, 0.08)",
        "INTERNOS":       "rgba(220, 38, 38, 0.07)",
        "ZAPPING":        "rgba(124, 58, 237, 0.07)",
    }

    # Mismo color que COLORES_GAP pero en hex plano.
    COLORES_GAP_HEX = {
        "FIBRA":          "#7c3aed",
        "HOMENETWORKING": "#3358ff",
        "SENALES":        "#ff6600",
        "INTERNOS":       "#dc2626",
        "ZAPPING":        "#7c3aed",
    }

    LABELS_GAP = {
        "FIBRA":          "Conectividad y plataforma (red ISP, backend y aplicación)",
        "HOMENETWORKING": "Homenetworking (red domiciliaria del cliente)",
        "SENALES":        "Señales de origen / cabecera (fallas en entrega de contenido desde proveedores)",
        "INTERNOS":       "Errores internos (Backend / DRM / Aplicación)",
        "ZAPPING":        "Efecto Fast Zapping (retry de licencia DRM en zapping rápido)",
    }

    PALETA_PEAKS = [
    "#dc2626",   # 1° — Rojo
    "#ea580c",   # 2° — Naranja
    "#d97706",   # 3° — Ámbar
    "#16a34a",   # 4° — Verde oscuro
    "#0284c7",   # 5° — Azul
    ]

    peaks_data_con_color = [
    {**p, "color": PALETA_PEAKS[i] if i < len(PALETA_PEAKS) else "#64748b"}
    for i, p in enumerate(peaks_data)
    ]
    
    # Índices de los peaks en el chart
    peak_chart_indices = []
    for p in peaks_data:
        hora_peak = int(p["hora"].split(":")[0])
        idx = next(
            (i for i, (ts, _) in enumerate(ts_final)
             if datetime.utcfromtimestamp(ts / 1000).hour == hora_peak),
            None
        )
        if idx is not None:
            peak_chart_indices.append(idx)

    gap_items = [
        {
            "color": COLORES_GAP[key],
            "color_hex": COLORES_GAP_HEX[key],
            "bg":    COLORES_GAP_BG[key],
            "label": LABELS_GAP[key],
            "valor": _fmt_pct(gap.get(key, 0), 3),
            "causas": [
                {
                    "codigo":        c["codigo"],
                    "descripcion":   c["descripcion"],
                    "gap_fmt":       _fmt_pct(c["gap"], 3),
                    "participacion": c["participacion"],
                    "acumulado":     c["acumulado"],
                    "es_otros":      c["es_otros"],
                }
                for c in desglose_causas.get(key, [])
            ],
        }
        for key in ["FIBRA", "HOMENETWORKING", "SENALES", "INTERNOS", "ZAPPING"]
        if gap.get(key, 0) > 0.001
    ]

    # Eje Y dinámico
    valores_chart = [v for _, v in ts_final]
    min_valor     = min(valores_chart)
    # Bajar el mínimo 0.3 para dar aire visual, redondeado hacia abajo a 0.1
    y_min = round(min_valor - 0.3, 1)

    return {
        # Imágenes
        "logo_emp_b64": _b64(cfg["assets"]["logo_emp"]),
        "logo_chile_b64": _b64(cfg["assets"]["logo_chile"]),

        # Fecha
        "fecha_label": fecha_lbl,

        # Disponibilidad
        "disponibilidad_fmt": _fmt_pct(disp, 2),
        "disp_dot_color":     disp_dot_color,
        "hay_tp":             hay_tp,

        # KPIs
        "launcher_fmt":        _fmt_pct(launcher, 2),
        "launcher_dot":        launcher_dot,
        "join_time_fmt":       _fmt_ms(join_time),
        "join_time_dot":       join_time_dot,
        "in_stream_error_fmt": _fmt_pct(in_stream, 3),
        "in_stream_error_dot": in_stream_dot,

        # Calidad
        "buffer_ratio_fmt":   _fmt_pct(buffer, 2),
        "buffer_ratio_color": buffer_color,
        "rebuffered_fmt":     _fmt_pct(rebuffered, 2),
        "rebuffered_color":   rebuffered_color,
        "ebvs_fmt":           _fmt_pct(ebvs, 2),
        "ebvs_color":         ebvs_color,

        # Suscriptores
        "subscribers_fmt":    _fmt_num(subscribers),
        "unique_devices_fmt": _fmt_num(unique_devices),

        # Chart
        "chart_labels":      chart_labels,
        "chart_data":        chart_data,
        "maint_start_hour":  hora_inicio,
        "maint_end_hour":    hora_fin,

        # Gap
        "gap_total_fmt": _fmt_pct(gap["gap_total"], 2),
        "gap_items":     gap_items,

        # Peak
        "peaks_data": peaks_data_con_color,
        "peak_chart_indices": peak_chart_indices,

        # TPs
        "tps_list": tps_list,

        # Eje Y dinámico
        "chart_y_min": y_min,
    }

# Renderiza el dashboard HTML y lo guarda en output_path
def render_dashboard(
    kpis:                 dict,
    ts_final:             list,
    disponibilidad_final: float,
    gap:                  dict,
    desglose_causas:      dict,
    tps_list:             list,
    fecha_desde:          str,
    hay_tp:               bool,
    peaks_data:           list,
    output_path:          str,
) -> str:

    cfg = _load_config()
    ctx = _preparar_contexto(
        kpis, ts_final, disponibilidad_final,
        gap, desglose_causas, tps_list, fecha_desde, hay_tp, 
        peaks_data, cfg,
    )

    template_dir = os.path.join(os.path.dirname(__file__), "template")
    env          = Environment(loader=FileSystemLoader(template_dir))
    template     = env.get_template("dashboard_diario.html.j2")

    html = template.render(**ctx)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[RENDER] Dashboard generado: {output_path}")
    return output_path