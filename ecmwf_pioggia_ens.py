import os
import requests
import metview as mv
from ecmwf.opendata import Client
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

FILENAME = "piemonte-tp-hres.grib"
PNG_OUTPUT = "piemonte-tp-hres"

def download_and_plot():
    client = Client("ecmwf", beta=False)
    
    # Run base: 23 Luglio 2026 alle 00:00 UTC.
    # Finestra accumulo: dalle 00:00 del 25 Luglio (+48h) alle 00:00 del 27 Luglio (+96h)
    
    try:
        client.retrieve(
            date=20260723,
            time=0,
            step=[48, 96],
            stream="oper",     # <-- CAMBIATO: Run Deterministico (HRES)
            type="fc",         # <-- CAMBIATO: Forecast
            levtype="sfc",     
            param=['tp'],      # Precipitazione Totale
            target=FILENAME
        )
    except Exception as e:
        print(f"Errore download: {e}")
        return False

    if not os.path.exists(FILENAME):
        print("Errore: GRIB non scaricato.")
        return False

    data = mv.read(FILENAME)
    
    # Estraiamo le due mappe dal file
    tp_48 = data.select(step=48)
    tp_96 = data.select(step=96)
    
    # Sottrazione per isolare l'accumulo delle 48 ore e conversione in millimetri
    tp_accumulo_mm = (tp_96 - tp_48) * 1000
    
    coast = mv.mcoast(
        map_coastline_colour="black",
        map_coastline_thickness=2,
        map_coastline_resolution="high",
        map_boundaries="on",
        map_boundaries_colour="black",
        map_boundaries_thickness=2,
        map_administrative_boundaries="on", 
        map_administrative_boundaries_colour="RGB(0.3, 0.3, 0.3)",
        map_administrative_boundaries_thickness=1,
        map_coastline_land_shade="off",
        map_coastline_sea_shade="off",
        map_grid="off",
        map_label="off"
    )
    
    view = mv.geoview(
        map_area_definition="corners",
        area=[43.5, 6.0, 46.8, 10.5], 
        coastlines=coast,
        subpage_y_position=12,
        subpage_y_length=72
    )

    # STILE PRECIPITAZIONI
    tp_style = mv.mcont(
        legend="on",
        contour="off", 
        contour_shade="on",
        contour_shade_technique="polygon_shading",
        contour_level_selection_type="level_list",
        contour_level_list=[0.5, 2, 5, 10, 20, 30, 50, 75, 100, 150, 200],
        contour_shade_colour_method="list",
        contour_shade_colour_list=[
            "RGB(0.7, 0.9, 1.0)",  
            "RGB(0.4, 0.7, 1.0)",  
            "RGB(0.1, 0.4, 1.0)",  
            "RGB(0.0, 0.2, 0.7)",  
            "RGB(0.2, 0.8, 0.2)",  
            "RGB(0.0, 0.5, 0.0)",  
            "RGB(1.0, 1.0, 0.0)",  
            "RGB(1.0, 0.6, 0.0)",  
            "RGB(1.0, 0.0, 0.0)",  
            "RGB(0.6, 0.0, 0.6)"   
        ]
    )
    
    legend = mv.mlegend(
        legend_display_type="continuous",
        legend_box_mode="positional",
        legend_box_x_position=1.0,   
        legend_box_y_position=17.5,  
        legend_box_x_length=27.0,    
        legend_box_y_length=1.5,     
        legend_text_font_size=0.4
    )
    
    title = mv.mtext(
        text_lines=[
            "Precipitazione Accumulata in 48h (mm) - ECMWF HRES",
            "Inizio: 25 Lug 00:00 UTC  |  Fine: 26 Lug 23:59 UTC (Run Base: 23 Lug 2026 00:00 UTC)"
        ],
        text_font_size=0.45,
        text_colour='black'
    )
    
    png = mv.png_output(
        output_name=PNG_OUTPUT,
        output_title="piemonte-tp",
        output_width=1200 
    )
    
    mv.setoutput(png)
    mv.plot(view, tp_accumulo_mm, tp_style, legend, title)
    return True

def invia_telegram():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Credenziali Telegram non fornite.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": "Accumulo Precipitazioni 48h (25-26 Luglio) - ECMWF HRES"}
    
    file_path = f"{PNG_OUTPUT}.1.png"
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as photo:
                requests.post(url, data=payload, files={"photo": photo})
                print("Inviato su Telegram!")
        except Exception as e:
            print(f"Errore invio Telegram: {e}")
    else:
        print(f"File {file_path} non trovato.")

if __name__ == "__main__":
    if download_and_plot():
        invia_telegram()
