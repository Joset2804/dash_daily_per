import argparse
from datetime import date, timedelta

# Resuelve las fechas según los argumentos de línea de comandos
def resolver_fechas():
    parser = argparse.ArgumentParser(description="Dashboard OTT")
    parser.add_argument("--daily",  type=str, nargs="?", const="ayer",
                        help="Ejecuta para el día anterior o una fecha específica YYYY-MM-DD")
    parser.add_argument("--desde",  type=str, help="Fecha inicio YYYY-MM-DD")
    parser.add_argument("--hasta",  type=str, help="Fecha fin   YYYY-MM-DD")
    args = parser.parse_args()

    if args.daily is not None:
        if args.daily == "ayer":
            # Sin fecha → día anterior
            fecha = str(date.today() - timedelta(days=1))
        else:
            # Con fecha → usar la fecha indicada
            fecha = args.daily
        return fecha, fecha, "daily"

    elif args.desde and args.hasta:
        if args.desde == args.hasta:
            # Mismo día → usar template diario
            return args.desde, args.hasta, "daily"
        return args.desde, args.hasta, "periodo"

    else:
        parser.print_help()
        exit(1)


if __name__ == "__main__":
    fecha_desde, fecha_hasta, modo = resolver_fechas()

    if modo == "daily":
        from pipeline_diario import run
        run(fecha_desde, fecha_hasta)

    elif modo == "periodo":
        from pipeline_periodo import run
        run(fecha_desde, fecha_hasta)