import os
import requests
import metview as mv
from ecmwf.opendata import Client
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore', category=RuntimeWarning)

FILENAME = "piemonte-z925-t925-custom.grib"
PNG_OUTPUT = "piemonte-z925-t925-custom"

def download_and_plot():
    client = Client("ecmwf", beta=False)
    
    # Oggi è il 23 Luglio. Usiamo il run del 2026-07-23 alle 00:00 UTC come base.
    base_date = datetime(2026, 7, 23, 0, 0) 
    
    # Target: 26 luglio 00:00 UTC (corrispondono alle 02:00 di notte in Italia - CEST)
    target_date = datetime(2026, 7, 26, 0, 0) 
    
    # Calcolo step in ore
    diff = target_date - base_date
    step_hours = int(diff.total_seconds() / 3600)

    try:
        client.retrieve(
            date=base_date.strftime("%Y%m%d"),
            time=base_date.hour,
            step=step_hours,
            stream="oper",
            type="fc",
            levtype="pl",
            levelist=[925],
            param=['gh', 't'],
            target=FILENAME
        )
    except Exception as e:
        print(f"Errore download: {e}")
        return False

    if not os.path.exists(FILENAME):
        print("Errore: GRIB non scaricato.")
        return False

    data = mv.read(FILENAME)
    
    t925 = data.select(shortName='t', level=925)
    gh925 = data.select(shortName='gh', level=925)
    
    # Converti geopotenziale in decametri
    gh925 /= 10
    
    # Visuale focalizzata sul Piemonte
    coast = mv.mcoast(
        map_coastline_colour="charcoal",
        map_coastline_resolution="high",
        map_coastline_land_shade="off", # Niente colore sulla terra per far vedere i geopotenziali
        map_coastline_sea_shade="off",
        map_boundaries="on",
        map_boundaries_colour="charcoal",
        map_boundaries_thickness=1,
        map_disputed_boundaries="off",
        map_grid_colour="grey",
        map_grid_line_style="dash",
        map_label_height=0.35,
    )
    
    view = mv.geoview(
        map_area_definition="corners",
        area=[43.5, 6.0, 46.5, 10.0], # Sud, Ovest, Nord, Est - Centrato sul Piemonte
        coastlines=coast
    )

    # 1. Geopotenziale: Varia col colore (sfumato)
    gh925_shade = mv.mcont(
        legend="on",
        contour="off", # Niente linee, solo colore
        contour_shade="on",
        contour_shade_technique="polygon_shading",
        contour_level_selection_type="interval",
        contour_interval=2.0, # Intervallo sfumatura 2 decametri
        contour_shade_colour_method="calculate",
        contour_shade_min_level=60.0, 
        contour_shade_max_level=90.0, 
        contour_shade_min_level_colour="blue",
        contour_shade_max_level_colour="red",
        contour_shade_colour_direction="clockwise"
    )

    # 2. Temperatura: Solo Isoterme (linee) ben visibili, ogni 1 grado
    t925_lines = mv.mcont(
        legend="off",
        contour="on",
        contour_line_colour="black",
        contour_line_thickness=2,
        contour_highlight="on", # Linee principali in grassetto ogni 5 gradi
        contour_highlight_thickness=4,
        contour_highlight_frequency=5,
        contour_level_selection_type="interval",
        contour_interval=1.0, # Ogni singola isoterma
        contour_label="on", # Accende l'etichetta del numero sulla linea
        contour_label_height=0.4,
        contour_label_frequency=1,
        contour_label_colour="black",
        contour_shade="off" # Niente colore riempitivo
    )
    
    # 3. Titoli espliciti
    title = mv.mtext(
        text_lines=[
            "Piemonte - Geopotenziale (Colore) e Temperatura (Isoterme) a 925 hPa",
            "Data Run Modello: <grib_info key='base-date' format='%d %b %Y %H:%M'/> UTC",
            "VALIDITA' CARTA: <grib_info key='valid-date' format='%d %b %Y %H:%M'/> UTC (ATTENZIONE: +2 ore per ora locale CEST)"
        ],
        text_font_size=0.4,
        text_colour='charcoal'
    )
    
    png = mv.png_output(
        output_name=PNG_OUTPUT,
        output_title="piemonte-custom",
        output_width=1200 # Aumentata la risoluzione per non sfocare i numeri delle isoterme
    )
    
    mv.setoutput(png)
    # L'ordine di plot sovrappone le linee nere (t925) sopra i colori (gh925)
    mv.plot(view, gh925, gh925_shade, t925, t925_lines, title)
    return True

def invia_telegram():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Credenziali Telegram non fornite.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": "Mappa 925 hPa Piemonte - Valida per Domenica 26 Luglio ore 02:00 CEST"}
    
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
