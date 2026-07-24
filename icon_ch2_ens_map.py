import os
import sys
import time
import requests
import urllib3
import metview as mv
from datetime import datetime, timedelta
import warnings

# Disabilita i warning a schermo per Runtime e SSL
warnings.filterwarnings('ignore', category=RuntimeWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def scarica_grib_ch2_stac(dt_run_utc: datetime, step: int, var_name: str = "TOT_PREC") -> str:
    """Scarica i GRIB tramite la REST API STAC ufficiale di MeteoSwiss (filtro per nome file)."""
    stac_url = "https://data.geo.admin.ch/api/stac/v1/search"
    
    # Formatta l'orario di inizializzazione
    ref_datetime = dt_run_utc.strftime("%Y-%m-%dT%H:00:00Z")
    
    # Corpo della richiesta POST:
    # Omettiamo volutamente "forecast:horizon" in modo da ottenere TUTTI gli step di questo run
    payload = {
        "collections": ["ch.meteoschweiz.ogd-forecasting-icon-ch2"],
        "forecast:reference_datetime": ref_datetime,
        "forecast:variable": var_name.upper(),
        "forecast:perturbed": True
    }
    
    run_str = dt_run_utc.strftime("%Y%m%d%H%M")
    
    # Il pattern esatto del file che vogliamo (notare var_name in minuscolo per il file)
    target_pattern = f"icon-ch2-eps-{run_str}-{step}-{var_name.lower()}-perturb.grib2"
    filename = target_pattern
    
    try:
        print(f"Interrogo STAC API (recupero tutti gli step per il run {ref_datetime})...")
        r_stac = requests.post(stac_url, json=payload, timeout=30)
        r_stac.raise_for_status()
        
        data = r_stac.json()
        features = data.get("features", [])
        
        if not features:
            print(f"Nessun asset STAC trovato per il run {ref_datetime}")
            return ""
            
        download_url = ""
        
        # Scorriamo tutte le feature (cioè tutti gli step temporali restituiti)
        for feature in features:
            assets = feature.get("assets", {})
            for key, asset in assets.items():
                href = asset.get("href", "")
                # Cerchiamo il link pre-firmato che contiene il nome del nostro file esatto
                if target_pattern in href: 
                    download_url = href
                    break
            if download_url:
                break
                
        if not download_url:
            print(f"Nessun link GRIB trovato contenente: {target_pattern}")
            return ""
            
        print(f"Trovato! Scaricamento file da S3 per step +{step}h...")
        r_dl = requests.get(download_url, stream=True, timeout=120, verify=False)
        
        if r_dl.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in r_dl.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"File {filename} scaricato con successo.")
            return filename
        else:
            print(f"Errore download (HTTP {r_dl.status_code})")
            
    except Exception as e:
        print(f"Errore STAC/Download {filename}: {e}")
        
    return ""

def invia_telegram(file_path: str, caption: str):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id: 
        print("Credenziali Telegram mancanti.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": caption}
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as photo:
                requests.post(url, data=payload, files={"photo": photo})
            print("📸 Immagine inviata su Telegram!")
        except Exception as e:
            print(f"Errore invio Telegram: {e}")

def genera_mappa_test(dt_run_utc: datetime):
    # Passaggi da scaricare per la differenza
    step_start = 55
    step_end = 101
    
    file_start = scarica_grib_ch2_stac(dt_run_utc, step_start)
    file_end = scarica_grib_ch2_stac(dt_run_utc, step_end)

    if not file_start or not file_end:
        print("Impossibile procedere: mancano uno o entrambi i file GRIB.")
        return

    print("Inizio rendering mappa Metview...")
    
    coast = mv.mcoast(
        map_coastline_colour="brown", map_coastline_thickness=2, map_coastline_resolution="high",
        map_boundaries="on", map_boundaries_colour="brown", map_boundaries_thickness=2,
        map_administrative_boundaries="on", map_administrative_boundaries_colour="brown",
        map_administrative_boundaries_thickness=1, map_grid="off", map_label="off"
    )
    
    view = mv.geoview(
        map_area_definition="corners", area=[43.5, 6.0, 46.8, 10.5], 
        coastlines=coast, subpage_x_position=5, subpage_y_position=12,   
        subpage_x_length=75, subpage_y_length=80     
    )

    lats = [45.07, 44.38, 44.90, 44.91, 45.32, 45.45, 45.56, 45.92]
    lons = [7.68,  7.55,  8.20,  8.61,  8.42,  8.61,  8.05,  8.55]
    sigle = ["TO", "CN", "AT", "AL", "VC", "NO", "BI", "VB"]

    capoluoghi = mv.input_visualiser(input_plot_type="geo_points", input_longitude_values=lons, input_latitude_values=lats)
    stile_capoluoghi = mv.msymb(legend="off", symbol_type="text", symbol_text_list=sigle, symbol_text_font_colour="brown", symbol_text_font_size=0.5, symbol_text_font_style="bold")

    rivoli_point = mv.input_visualiser(input_plot_type="geo_points", input_longitude_values=[7.51], input_latitude_values=[45.07])
    stile_rivoli = mv.msymb(legend="off", symbol_type="marker", symbol_colour="brown", symbol_height=0.4, symbol_marker_index=15)

    tp_style = mv.mcont(
        legend="on", contour="off", contour_shade="on",           
        contour_shade_technique="polygon_shading", contour_shade_method="area_fill",
        contour_level_selection_type="level_list",
        contour_level_list=[1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200, 300],
        contour_shade_colour_method="list",
        contour_shade_colour_list=[
            "RGB(0.6, 0.8, 1.0)", "RGB(0.0, 0.3, 1.0)", "RGB(0.4, 0.9, 0.4)", "RGB(0.0, 0.6, 0.0)", 
            "RGB(0.6, 0.8, 0.0)", "RGB(1.0, 0.9, 0.0)", "RGB(0.9, 0.7, 0.0)", "RGB(1.0, 0.6, 0.0)", 
            "RGB(1.0, 0.4, 0.0)", "RGB(1.0, 0.2, 0.0)", "RGB(1.0, 0.2, 0.2)", "RGB(0.7, 0.0, 0.0)", 
            "RGB(0.8, 0.2, 1.0)", "RGB(0.5, 0.0, 0.8)", "RGB(0.3, 0.0, 0.5)"
        ]
    )
    
    legend = mv.mlegend(legend_display_type="continuous", legend_box_mode="positional", legend_box_x_position=26.5, legend_box_y_position=3.0, legend_box_x_length=1.5, legend_box_y_length=14.0, legend_text_font_size=0.4)

    try:
        tp_start_ens = mv.mean(mv.read(file_start))
        tp_end_ens = mv.mean(mv.read(file_end))
        
        tp_diff_mean = tp_end_ens - tp_start_ens
        
        str_run = dt_run_utc.strftime('%d/%m/%Y %H:%M')
        
        title = mv.mtext(
            text_lines=[f"TEST FORZATO: ICON-CH2 EPS - Precipitazioni Medie (Run: {str_run} UTC)", f"Accumulo da step +{step_start}h a step +{step_end}h"], 
            text_font_size=0.5, text_colour='black'
        )
        
        PNG_OUTPUT = "mappa_forzata_ch2"
        png = mv.png_output(output_name=PNG_OUTPUT, output_width=1200)
        mv.setoutput(png)
        mv.plot(view, tp_diff_mean, tp_style, capoluoghi, stile_capoluoghi, rivoli_point, stile_rivoli, legend, title)
        
        file_generato = f"{PNG_OUTPUT}.1.png"
        invia_telegram(file_generato, f"🌧 TEST API STAC: Mappa ICON-CH2 (Run {str_run}Z).\nAccumulo step {step_start}-{step_end}.")
        
    except Exception as e:
        print(f"❌ Errore rendering Metview: {e}")

if __name__ == "__main__":
    # FORZATURA DEL RUN: 23 Luglio 2026, ore 12:00 UTC (il run 06Z è scaduto)
    dt_forzato = datetime(2026, 7, 23, 12, 0, 0)
    print(f"🚀 Avvio script di TEST per il RUN FORZATO: {dt_forzato} UTC")
    genera_mappa_test(dt_forzato)
