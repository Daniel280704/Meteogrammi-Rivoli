import os
import sys
import time
import requests
import urllib3
import metview as mv
from datetime import datetime, timedelta
import warnings

# Disabilita i warning a schermo
warnings.filterwarnings('ignore', category=RuntimeWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Coordinate di Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_LAST_HOUR = "ultima_ora_icon_ch2_map.txt"
RUN_DURATION = 120
START_DELAY = 1

# Base URL del bucket S3 OGD di MeteoSwiss
BASE_URL = "https://ch.meteoschweiz.ogd-forecasting-icon-ch2.s3.eu-central-1.amazonaws.com"

def estrai_limiti_run(hourly_data: dict, ref_param: str, utc_offset_sec: int) -> tuple[bool, str, datetime]:
    times = hourly_data.get("time", [])
    mean_vals = hourly_data.get(ref_param, [])
    
    if not times or not mean_vals: return False, "", None
    
    end_idx = -1
    for i in range(len(mean_vals) - 1, -1, -1):
        if mean_vals[i] is not None:
            end_idx = i
            break
            
    if end_idx == -1: return False, "", None
    
    ultima_ora_valida_str = times[end_idx]
    dt_end_local = datetime.fromisoformat(ultima_ora_valida_str)
    dt_end_utc = dt_end_local - timedelta(seconds=utc_offset_sec)
    dt_run_utc = dt_end_utc - timedelta(hours=RUN_DURATION)
    
    nome_run = dt_run_utc.strftime("%H") + "Z"
    
    if os.path.exists(FILE_LAST_HOUR):
        with open(FILE_LAST_HOUR, "r") as f:
            ultima_ora_salvata = f.read().strip()
        if ultima_ora_valida_str <= ultima_ora_salvata:
            print(f"✅ Run ICON-CH2 {nome_run} già elaborato.")
            return False, "", None

    with open(FILE_LAST_HOUR, "w") as f:
        f.write(ultima_ora_valida_str)

    return True, nome_run, dt_run_utc

def fetch_dati_con_retry() -> dict:
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "temperature_2m",
        "models": "meteoswiss_icon_ch2_ensemble_mean",
        "timezone": "Europe/Rome",
        "past_days": 1,
        "forecast_days": 6 
    }
    headers = {"User-Agent": "MeteoBot-ICONCH2-Map/1.0"}

    for _ in range(3):
        try:
            response = requests.get(URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Errore API: {e}", file=sys.stderr)
            time.sleep(15)
    return {}

def scarica_grib_ch2(dt_run_utc: datetime, step: int, var_name: str = "tot_prec") -> str:
    # Formato file derivato da schema grafico: icon-ch2-eps-YYYYMMDDHHMM-STEP-VAR-perturb.grib2
    run_str = dt_run_utc.strftime("%Y%m%d%H%M")
    filename = f"icon-ch2-eps-{run_str}-{step}-{var_name}-perturb.grib2"
    url = f"{BASE_URL}/{filename}"
    
    try:
        print(f"Download {filename}...")
        # Ignora la verifica del certificato SSL per scavalcare l'errore di Hostname mismatch
        r = requests.get(url, stream=True, timeout=60, verify=False)
        if r.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filename
        else:
            print(f"File non trovato (HTTP {r.status_code}): {url}")
    except Exception as e:
        print(f"Errore download {filename}: {e}")
    return ""

def invia_telegram(file_path: str, caption: str):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id: return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": caption}
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as photo:
                requests.post(url, data=payload, files={"photo": photo})
        except Exception as e:
            print(f"Errore invio Telegram: {e}")

def genera_mappe_metview(dt_run_utc: datetime, nome_run: str):
    indomani_00z = (dt_run_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Impostazioni mappa Piemonte
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

    # Ciclo previsionale (es. 3 giorni per l'orizzonte ad alta risoluzione)
    for i in range(3):
        target_start = indomani_00z + timedelta(days=i)
        target_end = target_start + timedelta(days=1)
        
        step_start = int((target_start - dt_run_utc).total_seconds() / 3600)
        step_end = int((target_end - dt_run_utc).total_seconds() / 3600)
        
        if step_end > RUN_DURATION: continue

        file_start = scarica_grib_ch2(dt_run_utc, step_start)
        file_end = scarica_grib_ch2(dt_run_utc, step_end)

        if not file_end or not file_start: 
            print(f"Skipping {target_start.strftime('%d/%m')} per mancanza dati.")
            continue

        try:
            # Calcolo ensemble mean per gli step (Metview gestisce in automatico il calcolo medio dei member presenti)
            tp_start_ens = mv.mean(mv.read(file_start))
            tp_end_ens = mv.mean(mv.read(file_end))
            
            # ICON restituisce solitamente le precipitazioni totali già in mm (kg/m2)
            tp_24h_mean = tp_end_ens - tp_start_ens
            
            str_run = dt_run_utc.strftime('%d/%m/%Y %H:%M')
            str_valida = f"{target_start.strftime('%d/%m/%Y')} - {target_end.strftime('%d/%m/%Y')}"
            
            title = mv.mtext(text_lines=[f"ICON-CH2 EPS - Precipitazioni Medie 24 ore (Run: {str_run} UTC)", str_valida], text_font_size=0.5, text_colour='black')
            
            PNG_OUTPUT = f"tp_ch2_{step_start}"
            png = mv.png_output(output_name=PNG_OUTPUT, output_width=1200)
            mv.setoutput(png)
            mv.plot(view, tp_24h_mean, tp_style, capoluoghi, stile_capoluoghi, rivoli_point, stile_rivoli, legend, title)
            
            file_generato = f"{PNG_OUTPUT}.1.png"
            invia_telegram(file_generato, f"🌧 ICON-CH2 EPS (Media 24h): {str_valida}\n⚙️ Run: {str_run} UTC")
            
        except Exception as e:
            print(f"Errore rendering Metview: {e}")

        # Pulizia file per risparmiare I/O
        for f in [file_start, file_end, file_generato]:
            if os.path.exists(f): os.remove(f)

def main():
    data = fetch_dati_con_retry()
    if not data: sys.exit(0)
        
    hourly = data.get("hourly", {})
    utc_offset = data.get("utc_offset_seconds", 0)
    
    is_new, nome_run, dt_run_utc = estrai_limiti_run(hourly, "temperature_2m", utc_offset)
    
    if is_new:
        print(f"🚀 Lancio generazione mappe ICON-CH2 per il RUN {nome_run} ({dt_run_utc})")
        genera_mappe_metview(dt_run_utc, nome_run)
    else:
        print("Nessun nuovo run. Uscita.")

if __name__ == "__main__":
    main()
