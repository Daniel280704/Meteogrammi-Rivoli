import os
import sys
import time
import json
import requests
import metview as mv
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

# Endpoint ufficiale STAC MeteoSvizzera per ICON-CH2-EPS (Ensemble 2.1 km)
STAC_URL = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-forecasting-icon-ch2/items?sortby=-datetime&limit=1"
FILE_LAST_HOUR = "ultima_ora_icon_ch2.txt"

def verifica_e_scarica_run():
    # 1. Controlla l'ultimo run tramite STAC API
    try:
        response = requests.get(STAC_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"⚠️ Errore connessione STAC MeteoSvizzera: {e}")
        return False, None, None, []

    if not data.get("features"):
        return False, None, None, []
        
    latest_item = data["features"][0]
    run_datetime_str = latest_item["properties"]["datetime"]
    dt_run_utc = datetime.strptime(run_datetime_str, "%Y-%m-%dT%H:%M:%SZ")
    nome_run = dt_run_utc.strftime("%H") + "Z"

    # 2. Controllo Semaforo
    if os.path.exists(FILE_LAST_HOUR):
        with open(FILE_LAST_HOUR, "r") as f:
            ultima_ora_salvata = f.read().strip()
        if run_datetime_str <= ultima_ora_salvata:
            print(f"✅ Run ICON-CH2-EPS {nome_run} già elaborato in precedenza.")
            return False, None, None, []

    print(f"🚀 Nuovo run MeteoSvizzera trovato: {run_datetime_str}")

    # 3. Estrazione dei Pre-signed URLs per la sola Precipitazione
    assets = latest_item.get("assets", {})
    grib_urls = []
    
    for key, asset in assets.items():
        key_upper = key.upper()
        if key_upper.endswith('.GRIB2') and "CONSTANTS" not in key_upper:
            # Filtriamo chirurgicamente per le precipitazioni (TOT_PREC)
            if "TOT_PREC" in key_upper or "PRECIP" in key_upper or "TP" in key_upper:
                grib_urls.append(asset["href"])
                
    # Fallback nel caso non ci sia lo split per variabile
    if not grib_urls:
        for key, asset in assets.items():
            if key.upper().endswith('.GRIB2') and "CONSTANTS" not in key.upper():
                grib_urls.append(asset["href"])

    # 4. Download effettivo dei GRIB in locale
    grib_files = []
    print(f"Scaricamento di {len(grib_urls)} file GRIB2...")
    for i, url in enumerate(grib_urls):
        local_filename = f"icon_ch2_precip_{i}.grib2"
        try:
            r = requests.get(url, stream=True, timeout=60)
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            grib_files.append(local_filename)
        except Exception as e:
            print(f"Errore download GRIB: {e}")

    # Aggiorna il semaforo
    with open(FILE_LAST_HOUR, "w") as f:
        f.write(run_datetime_str)

    return True, nome_run, dt_run_utc, grib_files


def invia_album_telegram(file_paths, caption_testo):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Credenziali Telegram mancanti.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    media = []
    files = {}
    opened_files = []
    
    for i, path in enumerate(file_paths):
        if os.path.exists(path):
            f = open(path, "rb")
            opened_files.append(f)
            file_id = f"photo{i}"
            files[file_id] = f
            
            media_item = {"type": "photo", "media": f"attach://{file_id}"}
            if i == 0:
                media_item["caption"] = caption_testo
            media.append(media_item)
            
    if not media:
        return

    payload = {"chat_id": chat_id, "media": json.dumps(media)}
    
    try:
        response = requests.post(url, data=payload, files=files)
        if response.status_code == 200:
            print("📸 Album inviato con successo!")
        else:
            print(f"Errore invio album: {response.text}")
    except Exception as e:
        print(f"Errore di connessione Telegram: {e}")
    finally:
        for f in opened_files:
            f.close()

def genera_mappe_metview(dt_run_utc, nome_run, grib_files):
    # Caricamento unificato di tutti i GRIB scaricati
    data = mv.read(grib_files)
    
    indomani_00z = (dt_run_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Confini Regionali e coste
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
    
    view = mv.geoview(
        map_area_definition="corners",
        area=[43.5, 6.0, 46.8, 10.5], 
        coastlines=coast,
        subpage_x_position=5,
        subpage_y_position=12,   
        subpage_x_length=75,
        subpage_y_length=80     
    )

    lats = [45.07, 44.38, 44.90, 44.91, 45.32, 45.45, 45.56, 45.92]
    lons = [7.68,  7.55,  8.20,  8.61,  8.42,  8.61,  8.05,  8.55]
    sigle = ["TO", "CN", "AT", "AL", "VC", "NO", "BI", "VB"]

    capoluoghi = mv.input_visualiser(
        input_plot_type="geo_points",
        input_longitude_values=lons,
        input_latitude_values=lats
    )

    stile_capoluoghi = mv.msymb(
        legend="off", symbol_type="text", symbol_text_list=sigle,
        symbol_text_font_colour="brown", symbol_text_font_size=0.5, symbol_text_font_style="bold"
    )

    rivoli_point = mv.input_visualiser(
        input_plot_type="geo_points",
        input_longitude_values=[7.51], input_latitude_values=[45.07]
    )

    stile_rivoli = mv.msymb(
        legend="off", symbol_type="marker", symbol_colour="brown", 
        symbol_height=0.4, symbol_marker_index=15     
    )

    tp_style = mv.mcont(
        legend="on", contour="off", contour_shade="on",           
        contour_shade_technique="polygon_shading",
        contour_shade_method="area_fill",
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
    
    legend = mv.mlegend(
        legend_display_type="continuous", legend_box_mode="positional",
        legend_box_x_position=26.5, legend_box_y_position=3.0,   
        legend_box_x_length=1.5, legend_box_y_length=14.0, legend_text_font_size=0.4
    )

    # Elaborazione delle giornate (5 giorni)
    for i in range(5):
        data_giorno = indomani_00z + timedelta(days=i)
        str_giorno = data_giorno.strftime('%d/%m/%Y')
        print(f"--- Elaborazione mappe MeteoSvizzera per il giorno {str_giorno} ---")
        
        file_generati_giorno = []
        
        # 4 Mappe da 6 ore per ogni giorno
        for j in range(4):
            target_start = data_giorno + timedelta(hours=j*6)
            target_end = target_start + timedelta(hours=6)
            
            step_start = int((target_start - dt_run_utc).total_seconds() / 3600)
            step_end = int((target_end - dt_run_utc).total_seconds() / 3600)
            
            # ICON-CH2 arriva a 120h, evitiamo calcoli fuori range
            if step_end > 120:
                print(f"Step +{step_end}h oltre il limite del modello (120h).")
                continue
                
            tp_start = data.select(step=step_start)
            tp_end = data.select(step=step_end)
            
            if len(tp_start) == 0 or len(tp_end) == 0:
                print(f"Dati non trovati per gli step {step_start} o {step_end}.")
                continue
            
            # Differenza step (ICON esprime solitamente la pioggia in kg/m2 che equivale in mm)
            tp_diff = tp_end - tp_start
            
            # Media Ensemble automatica per tutti i 21 membri
            tp_mean = mv.mean(tp_diff)

            # Check di sicurezza per convertire i metri in millimetri se necessario
            max_val = mv.maxvalue(tp_mean)
            if max_val < 5.0 and max_val > 0.001:
                tp_mean_mm = tp_mean * 1000
            else:
                tp_mean_mm = tp_mean

            PNG_OUTPUT = f"icon_ch2_map_{step_start}"
            str_run = dt_run_utc.strftime('%d/%m/%Y %H:%M')
            str_valida = f"{target_start.strftime('%d/%m/%Y')} | {target_start.strftime('%H:%M')} - {target_end.strftime('%H:%M')} UTC"

            title = mv.mtext(
                text_lines=[
                    f"ICON-CH2-EPS - precipitazioni 6 ore (Run: {str_run} UTC)", 
                    str_valida
                ], 
                text_font_size=0.5, text_colour='black'
            )
            
            png = mv.png_output(output_name=PNG_OUTPUT, output_width=1200)
            mv.setoutput(png)
            mv.plot(view, tp_mean_mm, tp_style, capoluoghi, stile_capoluoghi, rivoli_point, stile_rivoli, legend, title)
            
            file_generato = f"{PNG_OUTPUT}.1.png"
            file_generati_giorno.append(file_generato)

        if file_generati_giorno:
            str_run_finale = dt_run_utc.strftime('%d/%m/%Y %H:%M')
            caption_album = f"🌧 Precipitazioni 6h - {str_giorno}\n⚙️ Media Ensemble MeteoSvizzera (ICON-CH2-EPS)\n🕒 Run: {str_run_finale} UTC"
            invia_album_telegram(file_generati_giorno, caption_album)

            for f in file_generati_giorno:
                if os.path.exists(f):
                    os.remove(f)
            
            if i < 4:
                time.sleep(15)

    # Pulizia GRIB fisici
    for f in grib_files:
        if os.path.exists(f):
            os.remove(f)

def main():
    print("Verifica stato Run ICON-CH2 via STAC API...")
    is_new, nome_run, dt_run_utc, grib_files = verifica_e_scarica_run()
    
    if is_new and grib_files:
        print(f"🚀 Lancio generazione pluvio 6h ICON-CH2 per il RUN {nome_run} ({dt_run_utc})")
        genera_mappe_metview(dt_run_utc, nome_run, grib_files)
    else:
        print("Nessun nuovo run ICON-CH2 completo trovato. Uscita.")

if __name__ == "__main__":
    main()