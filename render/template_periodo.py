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
    _con_barra,
    _con_aporte_gap,
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
    dias_afectados:   list,
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

    # Días afectados: colores, formato y chips de causas

    LABELS_CHIP = {
        "FIBRA":          "Conectividad y plataforma",
        "HOMENETWORKING": "Homenetworking",
        "SENALES":        "Señales de origen / cabecera",
        "INTERNOS":       "Internos",
        "ZAPPING":        "Fast Zapping",
    }

    # Versión hex de COLORES_GAP para transparencias en el template
    COLORES_GAP_HEX = {
        "FIBRA":          "#7c3aed",
        "HOMENETWORKING": "#3358ff",
        "SENALES":        "#ff6600",
        "INTERNOS":       "#dc2626",
        "ZAPPING":        "#7c3aed",
    }

    dias_afectados_ctx = []
    for i, dia in enumerate(dias_afectados):
        gap_dia_total = dia["gap_dia"]["gap_total"]

        # Causas del día
        chips = []
        for key in ["FIBRA", "HOMENETWORKING", "SENALES", "INTERNOS", "ZAPPING"]:
            valor = dia["gap_dia"].get(key, 0)
            if valor <= 0.001:
                continue
            share = (valor / gap_dia_total * 100) if gap_dia_total else 0
            chips.append({
                "label":     LABELS_CHIP[key],
                "valor":     _fmt_pct(valor, 3),
                "color":     COLORES_GAP_HEX[key],
                "share_w":   f"{share:.2f}",
                "share_fmt": _fmt_pct(share, 1),
            })

        # Dimensiones con aporte al gap del día
        canales  = _con_barra(_con_aporte_gap(dia["canales"],         gap_dia_total))
        ver_devs = _con_barra(_con_aporte_gap(dia["version_devices"], gap_dia_total))

        # Nota extendida: top 3 de cada dimensión, en párrafos separados
        top_canales_nota = [c for c in canales  if not c["es_otros"]][:3]
        top_vd_nota      = [v for v in ver_devs if not v["es_otros"]][:3]

        nota_canales = None
        if top_canales_nota:
            lista = ", ".join(
                f'<b>{c["nombre"]}</b> '
                f'<span class="npct" style="--nc:#002eff;">{c["aporte_gap_fmt"]}</span>'
                for c in top_canales_nota
            )
            nota_canales = (
                f"Durante esta jornada, los canales con mayor afectación fueron "
                f"{lista} de indisponibilidad sobre el total del día."
            )

        nota_vd = None
        if top_vd_nota:
            lista = ", ".join(
                f'la versión <b>{v["version"]}</b> en '
                f'{", ".join(v["devices"]) if v["devices"] else "—"} '
                f'<span class="npct" style="--nc:#7c3aed;">{v["aporte_gap_fmt"]}</span>'
                for v in top_vd_nota
            )
            nota_vd = (
                f"En cuanto a dispositivos y versiones, destacaron {lista} "
                f"de indisponibilidad sobre el total del día."
            )

        dias_afectados_ctx.append({
            "num":             i + 1,
            "fecha":           dia["fecha"],
            "fecha_fmt":       dia["fecha_fmt"],
            "disp_fmt":        _fmt_pct(dia["disp_dia"], 2),
            "disp_raw":        dia["disp_dia"],
            "hay_tp":          dia["hay_tp"],
            "horas_bajo_slo":  dia["horas_bajo_slo"],
            "gap_total_fmt":   _fmt_pct(gap_dia_total, 3),
            "peaks": [
                {
                    "hora":     f"{p['hora']:02d}:00",
                    "disp_fmt": _fmt_pct(p["disponibilidad"], 3),
                }
                for p in dia["peaks"]
            ],
            "canales":         canales,
            "version_devices": ver_devs,
            "chips":           chips,
            "nota_canales":    nota_canales,
            "nota_vd":         nota_vd,
        })

    # Índices de los días afectados en el chart
    fechas_dias = [fecha for fecha, _ in disp_por_dia]
    peak_chart_indices = [
        fechas_dias.index(d["fecha"])
        for d in dias_afectados
        if d["fecha"] in fechas_dias
    ]

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

    LABELS_GAP = {
        "FIBRA":          "Conectividad y plataforma (red ISP, backend y aplicación)",
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
        # Días afectados
        "dias_afectados": dias_afectados_ctx,
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
    dias_afectados:   list,
    output_path:  str,
) -> str:
    cfg = _load_config()
    ctx = _preparar_contexto_periodo(
        kpis, disp_por_dia, dias_con_tp,
        gap, desglose_causas, tps_list, fecha_label, 
        hay_tp, dias_afectados, cfg,
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