import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from jinja2 import Environment, FileSystemLoader

from render.template import (
    _load_config,
    _b64,
    _fmt_pct,
    _fmt_num,
    _fmt_ms,
    _color_var,
    _sdot,
)


# Preparación del contexto para renderizar el dashboard
def _preparar_contexto_periodo(
    kpis:         dict,
    disp_por_dia: list,
    dias_con_tp:  set,
    gap:          dict,
    desglose_causas: dict,
    tps_list:     list,
    fecha_label:  str,
    hay_tp:       bool,
    peaks_data:   list,
    cfg:          dict,
) -> dict:

    slo = cfg["slo"]

    # Disponibilidad
    disp = float(
        Decimal(str(kpis["metric_6323436ccf03"])).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )
    disp_dot_color = _color_var(
        disp,
        verde_threshold  = slo["availability"]["verde"],
        rojo_threshold   = slo["availability"]["amarillo"],
        higher_is_better = True,
    )

    # Launcher
    launcher     = kpis.get("metric_dbbf01e41a88", 0)
    launcher_dot = _sdot(
        launcher,
        verde_threshold = slo["restart_launcher"]["amarillo"],
        rojo_threshold  = slo["restart_launcher"]["rojo"],
    )

    # Join Time
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

    # Calidad
    buffer     = kpis.get("bufferRatio", 0)
    rebuffered = kpis.get("rebufferedRatioG1n", 0)
    ebvs       = kpis.get("exits", 0)

    buffer_color     = _color_var(buffer,     slo["buffer_ratio"]["amarillo"],     slo["buffer_ratio"]["rojo"])
    rebuffered_color = _color_var(rebuffered, slo["rebuffered_plays"]["amarillo"],  slo["rebuffered_plays"]["rojo"])
    ebvs_color       = _color_var(ebvs,       slo["ebvs"]["amarillo"],             slo["ebvs"]["rojo"])

    # Chart
    chart_labels = [
        datetime.strptime(f, "%Y-%m-%d").strftime("%d/%m")
        for f, _ in disp_por_dia
    ]
    chart_data = [v for _, v in disp_por_dia]

    # Índices de días con TP para la franja azul
    chart_maint_indices = [
        i for i, (fecha, _) in enumerate(disp_por_dia)
        if fecha in dias_con_tp
    ]

    # Índices de los días peak para resaltar su punto en el gráfico (igual que peak_chart_index en el diario)
    fechas_dias = [fecha for fecha, _ in disp_por_dia]
    peak_chart_indices = [
        fechas_dias.index(p["fecha"])
        for p in peaks_data
        if p.get("fecha") in fechas_dias
    ]

    # Paleta de colores para peaks — del más grave al menos grave
    PALETA_PEAKS = [
        "#dc2626",   # 1° — Rojo       (más grave)
        "#ea580c",   # 2° — Naranja
        "#d97706",   # 3° — Ámbar
        "#16a34a",   # 4° — Verde oscuro
        "#0284c7",   # 5° — Azul
    ]

    # Ordenar peaks de menor a mayor disponibilidad y asignar color
    peaks_ordenados = sorted(
        enumerate(peaks_data),
        key=lambda x: x[1]["disponibilidad"]
    )
    colores_peaks = {}
    for rank, (idx_original, _) in enumerate(peaks_ordenados):
        colores_peaks[idx_original] = PALETA_PEAKS[rank] if rank < len(PALETA_PEAKS) else "#64748b"

    # Agregar color a cada peak
    peaks_data_con_color = [
        {**p, "color": colores_peaks[i]}
        for i, p in enumerate(peaks_data)
    ]

    # Suscriptores
    subscribers    = kpis.get("subscribers", 0)
    unique_devices = kpis.get("uniqueDeviceIDs", 0)

    # Gap items dinámicos
    COLORES_GAP = {
        "FIBRA":          "var(--blue)",
        "HOMENETWORKING": "var(--blue-mid)",
        "SENALES":        "var(--accent)",
        "INTERNOS":       "var(--red)",
        "ZAPPING":        "#7c3aed", 
    }

    # Mismo color que COLORES_GAP pero en rgba semitransparente, para el fondo de la card del resumen
    COLORES_GAP_BG = {
        "FIBRA":          "rgba(0, 46, 255, 0.06)",
        "HOMENETWORKING": "rgba(51, 88, 255, 0.07)",
        "SENALES":        "rgba(255, 102, 0, 0.08)",
        "INTERNOS":       "rgba(220, 38, 38, 0.07)",
        "ZAPPING":        "rgba(124, 58, 237, 0.07)",
    }

    #  Versión hex de COLORES_GAP para transparencias en el template
    COLORES_GAP_HEX = {
        "FIBRA":          "#002eff",
        "HOMENETWORKING": "#3358ff",
        "SENALES":        "#ff6600",
        "INTERNOS":       "#dc2626",
        "ZAPPING":        "#7c3aed",
    }

    LABELS_GAP = {
        "FIBRA":          "Conectividad (red ISP / fibra)",
        "HOMENETWORKING": "Homenetworking (red domiciliaria del cliente)",
        "SENALES":        "Señales de origen / cabecera (fallas en entrega de contenido desde proveedores)",
        "INTERNOS":       "Errores internos (Backend / DRM / Aplicación)",
        "ZAPPING":        "Efecto Fast Zapping (retry de licencia DRM en zapping rápido)",
    }
    gap_items = [
        {
            "color":     COLORES_GAP[key],
            "color_hex": COLORES_GAP_HEX[key],
            "bg":        COLORES_GAP_BG[key],
            "label":     LABELS_GAP[key],
            "valor":     _fmt_pct(gap.get(key, 0), 3),
            "causas": [
                {
                    "codigo": c["codigo"],
                    "descripcion": c["descripcion"],
                    "gap_fmt": _fmt_pct(c["gap"], 3),
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
    y_min = round(min(chart_data) - 0.3, 1)

    return {
        # Imágenes
        "logo_emp_b64": _b64(cfg["assets"]["logo_emp"]),
        "logo_chile_b64": _b64(cfg["assets"]["logo_chile"]),

        # Fecha
        "fecha_label": fecha_label,

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
        "ebvs_fmt":           _fmt_pct(ebvs, 3),
        "ebvs_color":         ebvs_color,

        # Suscriptores
        "subscribers_fmt":    _fmt_num(subscribers),
        "unique_devices_fmt": _fmt_num(unique_devices),

        # Chart
        "chart_labels":        chart_labels,
        "chart_data":          chart_data,
        "chart_maint_indices": chart_maint_indices,
        "chart_y_min":         y_min,

        # Gap
        "gap_total_fmt": _fmt_pct(gap["gap_total"], 2),
        "gap_items":     gap_items,

        # TPs
        "tps_list": tps_list,
        
        # Peaks
        #"peaks_data": peaks_data,
        "peaks_data": peaks_data_con_color,
        "peak_chart_indices": peak_chart_indices,
    }


# Renderiza el dashboard HTML y lo guarda en output_path
def render_dashboard_periodo(
    kpis:         dict,
    disp_por_dia: list,
    dias_con_tp:  set,
    gap:          dict,
    desglose_causas: dict,
    tps_list:     list,
    fecha_label:  str,
    hay_tp:       bool,
    peaks_data:   list,
    output_path:  str,
) -> str:
    cfg = _load_config()
    ctx = _preparar_contexto_periodo(
        kpis, disp_por_dia, dias_con_tp,
        gap, desglose_causas, tps_list, fecha_label, 
        hay_tp, peaks_data, cfg,
    )

    template_dir = os.path.join(os.path.dirname(__file__), "template")
    env          = Environment(loader=FileSystemLoader(template_dir))
    template     = env.get_template("dashboard_periodo.html.j2")

    html = template.render(**ctx)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[RENDER] Dashboard período generado: {output_path}")
    return output_path