import os
import requests
import metview as mv
from ecmwf.opendata import Client
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

FILENAME = "piemonte-tp-pf.grib"
PNG_OUTPUT = "piemonte-tp-ens-mean"

def download_and_plot():
    client = Client("ecmwf", beta=False)
    
    # Scarichiamo tutti i 50 spaghi dell'ensemble (type="pf")
    try:
        client.retrieve(
            date=20260723,
            time=0,
            step=[48, 96],
            stream="enfo",     
            type="pf",         
            levtype="sfc",     
            param=['tp'],
            target=FILENAME
        )
    except Exception as e:
        print(f"Errore download: {e}")
        return False

    if not os.path.exists(FILENAME):
        print("Errore: GRIB non scaricato.")
        return False

    data = mv.read(FILENAME)
    
    tp_48 = data.select(step=48)
    tp_96 = data.select(step=96)
    
    # 1. Calcoliamo la differenza in mm per ogni scenario
    tp_diff_mm = (tp_96 - tp_48) * 1000
    
    # 2. Calcoliamo la MEDIA di tutti i 50 scenari
    tp_mean_mm = mv.mean(tp_diff_mm)
    
    # CONFINI GEOGRAFICI MARRONI
    coast = mv.mcoast(
        map_coastline_colour="brown",
        map_coastline_thickness=2,
        map_coastline_resolution="high",
        map_boundaries="on",
        map_boundaries_colour="brown",
        map_boundaries_thickness=2,
        map_administrative_boundaries="on", 
        map_administrative_boundaries_colour="brown",
        map_administrative_boundaries_thickness=1,
        map_coastline_land_shade="off", 
        map_coastline_sea_shade="off",
        map_grid="off",
        map_label="off"
    )
    
    # IMPAGINAZIONE
    view = mv.geoview(
        map_area_definition="corners",
        area=[43.5, 6.0, 46.8, 10.5], 
        coastlines=coast,
        subpage_y_position=5,   
        subpage_y_length=80     
    )

    # CAPOLUOGHI DI PROVINCIA (Sigle testuali al posto dei pallini)
    # Ordine esatto geografico: Torino, Cuneo, Asti, Alessandria, Vercelli, Novara, Biella, Verbania
    lats = [45.07, 44.38, 44.90, 44.91, 45.32, 45.45, 45.56, 45.92]
    lons = [7.68,  7.55,  8.20,  8.61,  8.42,  8.61,  8.05,  8.55]
    sigle = ["TO", "CN", "AT", "AL", "VC", "NO", "BI", "VB"]

    capoluoghi = mv.input_visualiser(
        input_plot_type="geo_points",
        input_longitude_values=lons,
        input_latitude_values=lats
    )

    # Stile: Testo marrone in grassetto
    stile_capoluoghi = mv.msymb(
        legend="off",
        symbol_type="text",
        symbol_text_list=sigle,
        symbol_text_font_colour="brown",
        symbol_text_font_size=0.5,
        symbol_text_font_style="bold"
    )

    # STILE PIOGGIA: Tinta unita, scala personalizzata (parte da 5mm)
    tp_style = mv.mcont(
        legend="on",                  
        contour="off",                
        contour_shade="on",           
        contour_shade_technique="polygon_shading",
        contour_level_selection_type="level_list",
        contour_level_list=[0.5, 2, 5, 10, 15, 20, 30, 40, 50, 65, 80, 100, 150],
        contour_shade_colour_method="list",
        contour_shade_colour_list=[
            "RGB(0.6, 0.8, 1.0)",  
            "RGB(0.0, 0.3, 1.0)",  
            "RGB(0.4, 0.9, 0.4)",  
            "RGB(0.0, 0.6, 0.0)",  
            "RGB(1.0, 0.9, 0.0)",  
            "RGB(0.9, 0.7, 0.0)",  
            "RGB(1.0, 0.6, 0.0)",  
            "RGB(1.0, 0.4, 0.0)",  
            "RGB(1.0, 0.2, 0.2)",  
            "RGB(0.7, 0.0, 0.0)",  
            "RGB(0.8, 0.2, 1.0)",  
            "RGB(0.5, 0.0, 0.8)",  
            "RGB(0.3, 0.0, 0.5)"   
        ]
    )
    
    # LEGENDA IN BASSO (Alzato il valore y da 17.5 a 16.5)
    legend = mv.mlegend(
        legend_display_type="continuous",
        legend_box_mode="positional",
        legend_box_x_position=1.0,   
        legend_box_y_position=16.5,  # <-- Legenda un po' più in alto
        legend_box_x_length=27.0,    
        legend_box_y_length=1.5,     
        legend_text_font_size=0.4
    )
    
    # TITOLO VUOTO 
    title = mv.mtext(
        text_lines=[" "], 
        text_font_size=0.1
    )
    
    png = mv.png_output(
        output_name=PNG_OUTPUT,
        output_title="piemonte-tp-ens-mean",
        output_width=1200 
    )
    
    mv.setoutput(png)
    
    # Plot finale
    mv.plot(view, tp_mean_mm, tp_style, capoluoghi, stile_capoluoghi, legend, title)
    return True

def invia_telegram():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Credenziali Telegram non fornite.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": "Media Scenari ENS (50 Spaghi) - Precipitazioni 48h"}
    
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
