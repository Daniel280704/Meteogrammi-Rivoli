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
    
    # Conversione in Celsius
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
        coastlines=coast
    )

    # STILE TEMPERATURA: Solo linee (isoterme), sfondo bianco, niente riempimento
    t925_style = mv.mcont(
        legend="off",                # Legenda completamente disattivata
        contour="on",
        contour_line_colour="black", # Linee nere per staccare sul bianco
        contour_line_thickness=2,
        contour_highlight="on",      # Linee spesse ogni 5 gradi
        contour_highlight_thickness=4,
        contour_highlight_frequency=5,
        contour_label="on",      
        contour_label_height=0.4,
        contour_label_frequency=1,
        contour_label_colour="black",
        contour_shade="off",         # SPENTO TOTALMENTE IL COLORE/PUNTINATO
        contour_level_selection_type="interval",
        contour_interval=1.0         # Isoterma ogni 1 grado
    )
    
    title = mv.mtext(
        text_lines=[
            "Temperatura 925 hPa (°C) - Modello ECMWF HRES",
            "Run: <grib_info key='base-date' format='%d %b %Y %H:%M'/> UTC  |  Valida per: Domenica 26 Luglio 2026, 02:00 CEST"
        ],
        text_font_size=0.45,
        text_colour='black'
    )
    
    png = mv.png_output(
        output_name=PNG_OUTPUT,
        output_title="piemonte-t925",
        output_width=1200
    )
    
    mv.setoutput(png)
    
    # Eliminato l'oggetto 'legend' dal plot
    mv.plot(view, t925_celsius, t925_style, title)
    return True

def invia_telegram():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Credenziali Telegram non fornite.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": "Mappa Termica ECMWF (925 hPa) - Solo Isoterme"}
    
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
