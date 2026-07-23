import os
import requests
import metview as mv
from ecmwf.opendata import Client
import warnings
from datetime import datetime

warnings.filterwarnings('ignore', category=RuntimeWarning)

FILENAME = "piemonte-t925.grib"
PNG_OUTPUT = "piemonte-t925"

def download_and_plot():
    client = Client("ecmwf", beta=False)
    
    # Run di partenza: 23 Luglio 00:00 UTC
    # Target: 26 Luglio 00:00 UTC (02:00 CEST)
    base_date = datetime(2026, 7, 23, 0, 0)
    step_hours = 72

    try:
        client.retrieve(
            date=base_date.strftime("%Y%m%d"),
            time=base_date.hour,
            step=step_hours,
            stream="oper",
            type="fc",
            levtype="pl",
            levelist=[925],
            param=['t'], 
            target=FILENAME
        )
    except Exception as e:
        print(f"Errore download: {e}")
        return False

    if not os.path.exists(FILENAME):
        print("Errore: GRIB non scaricato.")
        return False

    data = mv.read(FILENAME)
    
    t925_kelvin = data.select(shortName='t', level=925)
    t925_celsius = t925_kelvin - 273.15 
    
    coast = mv.mcoast(
        map_coastline_colour="black",
        map_coastline_thickness=2,
        map_coastline_resolution="high",
        map_boundaries="on",
        map_boundaries_colour="black",
        map_boundaries_thickness=2,
        map_administrative_boundaries="on", 
        map_administrative_boundaries_colour="RGB(0.2, 0.2, 0.2)",
        map_administrative_boundaries_thickness=1,
        map_coastline_land_shade="off",
        map_coastline_sea_shade="off",
        map_grid="off",
        map_label="off"
    )
    
    view = mv.geoview(
        map_area_definition="corners",
        area=[43.5, 6.0, 46.8, 10.5], 
        coastlines=coast
    )

    # Stile Temperatura: aggiunta la tinta unita (area_fill) e scala modificata
    t925_style = mv.mcont(
        legend="on",
        contour="on",
        contour_line_colour="RGB(0.5, 0.5, 0.5)", 
        contour_line_thickness=1,
        contour_highlight="off", 
        contour_label="on",      
        contour_label_height=0.4,
        contour_label_frequency=1,
        contour_label_colour="black",
        contour_shade="on",
        contour_shade_technique="polygon_shading",
        contour_shade_method="area_fill", # <-- FORZA IL COLORE A TINTA UNITA PIENA
        contour_level_selection_type="interval",
        contour_interval=1.0,    
        contour_shade_colour_method="calculate",
        contour_shade_min_level=-15.0, # <-- SCALA AGGIORNATA
        contour_shade_max_level=40.0,  # <-- SCALA AGGIORNATA
        contour_shade_min_level_colour="purple",
        contour_shade_max_level_colour="red",
        contour_shade_colour_direction="clockwise" 
    )
    
    # Legenda spostata verso il basso (coordinata y negativa)
    legend = mv.mlegend(
        legend_display_type="continuous",
        legend_box_mode="positional",
        legend_box_x_position=0.5,
        legend_box_y_position=-1.5, # <-- PIU' IN BASSO
        legend_box_x_length=20.0,
        legend_box_y_length=1.5,
        legend_text_font_size=0.4
    )
    
    title = mv.mtext(
        text_lines=[
            "Temperatura 925 hPa (°C)",
            "Run: <grib_info key='base-date' format='%d %b %Y %H:%M'/> UTC  |  Valida per: Domenica 26 Luglio 2026, 02:00 CEST"
        ],
        text_font_size=0.5,
        text_colour='black'
    )
    
    png = mv.png_output(
        output_name=PNG_OUTPUT,
        output_title="piemonte-t925",
        output_width=1000
    )
    
    mv.setoutput(png)
    mv.plot(view, t925_celsius, t925_style, legend, title)
    return True

def invia_telegram():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Credenziali Telegram non fornite.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": "Mappa Termica ECMWF (925 hPa) - Tinta unita"}
    
    file_path = f"{PNG_OUTPUT}.1.png"
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as photo:
                requests.post(url, data=payload, files={"photo": photo})
        except Exception:
            pass

if __name__ == "__main__":
    if download_and_plot():
        invia_telegram()
