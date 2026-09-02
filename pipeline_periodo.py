# pipeline_periodo.py
import os
from datetime import datetime
from process.tps     import _load_config
from process.gap     import calcular_gap, calcular_desglose_causas 
from process.periodo import (
    calcular_disponibilidad_periodo,
    calcular_launcher_periodo,
    get_tps_display_periodo,
)
from sources.npaw    import fetch_kpis, fetch_errores_por_codigo, fetch_canales_por_hora
from process.peaks  import detectar_peaks_periodo

# Run completo
def run(fecha_desde: str, fecha_hasta: str):
    cfg        = _load_config()
    output_dir = cfg["rutas"]["salida_html"]

    print(f"\n{'='*50}")
    print(f"  Dashboard OTT Período — {fecha_desde} → {fecha_hasta}")
    print(f"{'='*50}\n")

    # 1. Disponibilidad día a día + corrección TPs
    disp_final, disp_por_dia, dias_con_tp, hay_tp, ts_hora_raw = calcular_disponibilidad_periodo(
        fecha_desde, fecha_hasta
    )

    # 2. Launcher promedio del período
    launcher_final, _ = calcular_launcher_periodo(fecha_desde, fecha_hasta)

    # 3. KPIs totales del período (una sola llamada granularity=total)
    kpis = fetch_kpis(fecha_desde, fecha_hasta)

    # 4. Sobreescribir disponibilidad y launcher con los valores calculados
    kpis["metric_6323436ccf03"] = disp_final
    kpis["metric_dbbf01e41a88"] = launcher_final

    # 5. Desglose del gap
    errores = fetch_errores_por_codigo(fecha_desde, fecha_hasta)
    gap     = calcular_gap(errores, disp_final)

    # 5.1 — Desglose Pareto de causas por categoría
    desglose_causas = calcular_desglose_causas(errores, disp_final, cfg)

    # 5.5 — Detección de peaks por día + causas + canales
    from process.peaks import detectar_peaks_periodo
    from sources.npaw  import fetch_por_dimension_dia, fetch_version_device

    umbral            = cfg["peaks"]["umbral_periodo"]
    max_peaks_por_dia = cfg["peaks"]["max_peaks_por_dia"]
    top_canales       = cfg["peaks"]["top_canales_periodo"]
    top_versiones     = cfg["peaks"]["top_versiones"]

    dias_afectados_raw = detectar_peaks_periodo(
        disp_por_dia = disp_por_dia,
        ts_hora_raw  = ts_hora_raw,
        dias_con_tp  = dias_con_tp,
        umbral       = umbral,
        max_peaks    = max_peaks_por_dia,
    )

    dias_afectados = []
    for dia in dias_afectados_raw:
        fecha    = dia["fecha"]
        tiene_tp = dia["hay_tp"]

        # Canales del día completo
        canales = fetch_por_dimension_dia(
            fecha, "content_channel", top_canales, tiene_tp
        )

        # Versiones + dispositivos que las usan
        version_devices = fetch_version_device(
            fecha, hora=None, top=top_versiones, excluir_ventana=tiene_tp
        )

        # Causas del día completo
        errores_dia = fetch_errores_por_codigo(fecha, fecha)
        gap_dia     = calcular_gap(errores_dia, dia["disp_dia"])

        dias_afectados.append({
            "fecha":           fecha,
            "fecha_fmt":       datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y"),
            "disp_dia":        dia["disp_dia"],
            "hay_tp":          tiene_tp,
            "horas_bajo_slo":  dia["horas_bajo_slo"],
            "peaks":           dia["peaks"],
            "canales":         canales,
            "version_devices": version_devices,
            "gap_dia":         gap_dia,
        })

        print(f"[PERIODO] {fecha}: detalle completo obtenido")

    print(f"[PERIODO] {len(dias_afectados)} días afectados con detalle completo")

    # 6. Lista de TPs del período
    tps_list = get_tps_display_periodo(fecha_desde, fecha_hasta, cfg)

    # 7. Render HTML
    from render.template_periodo import render_dashboard_periodo

    fecha_label    = f"{fecha_desde[8:10]}/{fecha_desde[5:7]}/{fecha_desde[:4]} - {fecha_hasta[8:10]}/{fecha_hasta[5:7]}/{fecha_hasta[:4]}"
    nombre_archivo = f"dashboard_periodo_{fecha_desde}_{fecha_hasta}.html"
    output_path    = os.path.join(output_dir, nombre_archivo)

    render_dashboard_periodo(
        kpis         = kpis,
        disp_por_dia = disp_por_dia,
        dias_con_tp  = dias_con_tp,
        gap          = gap,
        desglose_causas = desglose_causas,
        tps_list     = tps_list,
        fecha_label  = fecha_label,
        hay_tp       = hay_tp,
        dias_afectados = dias_afectados,
        output_path  = output_path,
    )

    # 8. Screenshot
    from pipeline_diario import capturar_screenshot
    nombre_png = f"dashboard_periodo_{fecha_desde}_{fecha_hasta}.png"
    png_path   = os.path.join(cfg["rutas"]["salida_png"], nombre_png)
    capturar_screenshot(output_path, png_path)

    print(f"\n✓ Listo → {output_path}\n")