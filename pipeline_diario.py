import os
import yaml
#import argparse
#from datetime import date, timedelta

from sources.npaw       import fetch_kpis, fetch_timeseries, fetch_errores_por_codigo, fetch_canales_por_hora
from process.tps        import aplicar_tps, get_tps_display, _load_config
from process.gap        import calcular_gap, calcular_desglose_causas
from render.template    import render_dashboard
from process.peaks import detectar_peak_diario
from playwright.sync_api import sync_playwright
from datetime import datetime

# Captura el dashboard HTML como PNG a ancho fijo
def capturar_screenshot(html_path: str, output_path: str, ancho: int = 1600):

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page    = browser.new_page(viewport={"width": ancho, "height": 1000})
        page.goto(f"file:///{os.path.abspath(html_path)}")
        page.wait_for_timeout(1000)  # espera que cargue Chart.js
        page.locator("body").screenshot(path=output_path)
        browser.close()
    print(f"[SCREENSHOT] Guardado: {output_path}")

# Run completo
def run(fecha_desde: str, fecha_hasta: str):
    
    cfg        = _load_config()

    output_html_dir = cfg["rutas"]["salida_html"]
    output_png_dir  = cfg["rutas"]["salida_png"]

    print(f"\n{'='*50}")
    print(f"  Dashboard OTT — {fecha_desde} → {fecha_hasta}")
    print(f"{'='*50}\n")

    # 1. Datos NPAW
    kpis    = fetch_kpis(fecha_desde, fecha_hasta)
    ts_raw  = fetch_timeseries(fecha_desde, fecha_hasta)
    errores = fetch_errores_por_codigo(fecha_desde, fecha_hasta)

    # 2. Corrección TPs
    ts_final, disp_final, hay_tp = aplicar_tps(
        timeseries         = ts_raw,
        disponibilidad_api = kpis["metric_6323436ccf03"],
        fecha              = fecha_desde,
    )

    # 3.5. Detección de peaks y canales
    umbral      = cfg["peaks"]["umbral"]
    max_peaks   = cfg["peaks"]["max_peaks_diario"]
    top_canales = cfg["peaks"]["top_canales_diario"]

    peaks_detectados = detectar_peak_diario(
        ts_raw,
        hay_tp     = hay_tp,
        umbral     = umbral,
        max_peaks  = max_peaks,
    )

    peaks_data = []
    for peak in peaks_detectados:
        canales = fetch_canales_por_hora(peak["fecha"], peak["hora"])
        peaks_data.append({
            "fecha":          peak["fecha"],
            "fecha_fmt":      datetime.strptime(peak["fecha"], "%Y-%m-%d").strftime("%d-%b").lower(),
            "hora":           f"{peak['hora']:02d}:00",
            "disponibilidad": peak["disponibilidad"],
            "canales":        canales[:top_canales],
        })
        print(f"[PEAKS] Top {top_canales} canales para "
              f"{peak['fecha']} {peak['hora']:02d}:00")

    # 3. Desglose del gap
    gap = calcular_gap(errores, disp_final)

    # 3.6. Desglose Pareto de causas por categoría
    desglose_causas = calcular_desglose_causas(errores, disp_final, cfg)

    # 4. Lista de TPs para el dashboard
    tps_list = get_tps_display(fecha_desde, cfg)

    # 5. Render HTML
    nombre_archivo = f"dashboard_operativo_{fecha_desde}.html"
    output_path    = os.path.join(output_html_dir, nombre_archivo)

    render_dashboard(
        kpis                 = kpis,
        ts_final             = ts_final,
        disponibilidad_final = disp_final,
        gap                  = gap,
        desglose_causas      = desglose_causas,
        tps_list             = tps_list,
        fecha_desde          = fecha_desde,
        hay_tp               = hay_tp,
        peaks_data            = peaks_data,
        output_path          = output_path,
    )

    # 6. Screenshot
    nombre_png = f"dashboard_operativo_{fecha_desde}.png"
    png_path   = os.path.join(output_png_dir, nombre_png)
    capturar_screenshot(output_path, png_path)

    print(f"\n✓ Listo → {output_path}\n")

## Entry point
#if __name__ == "__main__":
#    fecha_desde, fecha_hasta = resolver_fechas()
#    run(fecha_desde, fecha_hasta)