import os
import sys
import time
import requests
import metview as mv
from ecmwf.opendata import Client
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_LAST_HOUR = "ultima_ora_ecmwf.txt"
RUN_DURATION = 362
START_DELAY = 2

def estrai_limiti_run(hourly_data: dict, hourly_params: list, utc_offset_sec: int):
    times = hourly_data.get("time", [])
    if not times: return False, "", None

    hourly_end_indices = []
    for param in hourly_params:
        vals = hourly_data.get(param, [])
        if not vals: return False, "", None
        
        end_idx = -1
        for i in range(len(vals) - 1, -1, -1):
            if vals[i] is not None:
                end_idx = i
                break
        
        if end_idx == -1: return False, "", None
        hourly_end_indices.append(end_idx)

    if len(set(hourly_end_indices)) != 1:
        return False, "", None

    end_idx1 = hourly_end_indices[0]
    ultima_ora_valida_str = times[end_idx1]

    dt_end_local = datetime.fromisoformat(ultima_ora_valida_str)
    dt_end_utc = dt_end_local - timedelta(seconds=utc_offset_sec)
    dt_run_utc = dt_end_utc - timedelta(hours=RUN_DURATION)
    dt_start_utc = dt_run_utc + timedelta(hours=START_DELAY)

    dt_start_local = dt_start_utc + timedelta(seconds=utc_offset_sec)
    start_time_str = dt_start_local.strftime("%Y-%m-%dT%H:%M")
    nome_run = dt_run_utc.strftime("%H") + "Z"

    try:
        start_idx = times.index(start_time_str)
    except ValueError:
        return False, "", None

    expected_points = RUN_DURATION - START_DELAY + 1
    actual_points = end_idx1 - start_idx + 1

    if actual_points < expected_points:
        print(f"⏳ Run ECMWF {nome_run} in caricamento... ({actual_points}/{expected_points} ore)")
        return False, "", None

    if os.path.exists(FILE_LAST_HOUR):
        with open(FILE_LAST_HOUR, "r") as f:
            ultima_ora_salvata = f.read().strip()
        if ultima_ora_valida_str <= ultima_ora_salvata:
            print(f"✅ Run ECMWF {nome_run} già elaborato in precedenza.")
            return False, "", None

    with open(FILE_LAST_HOUR, "w") as f:
        f.write(ultima_ora_valida_str)

    return True, nome_run, dt_run_utc

def fetch_dati_con_retry() -> dict:
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    var_list = [
        "temperature_2m", "temperature_2m_spread",
        "temperature_500hPa_spread", "geopotential_height_500hPa"
    ]
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "ecmwf_ifs025_ensemble_mean",
        "timezone": "Europe/Rome",
        "past_days": 1,
        "forecast_days": 16
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter/8.1"}

    for tentativo in range(3):
        try:
            response = requests.get(URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Errore API Open-Meteo: {e}", file=sys.stderr)
            time.sleep(15)
    return {}

def invia_telegram(file_path, caption):
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
                print(f"📸 Mappa inviata: {caption}")
        except Exception as e:
            print(f"Errore invio Telegram: {e}")
    else:
        print(f"File {file_path} non trovato.")

def genera_mappe_metview(dt_run_utc, nome_run):
    client = Client("ecmwf", beta=False)
    
    # Calcoliamo l'indomani a mezzanotte (00:00 UTC)
    indomani_00z = (dt_run_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Coste e Confini Regionali (tolti gli shapefile provinciali)
    coast = mv.mcoast(
        map_coastline_colour="brown",
        map_coastline_thickness=2,
        map_coastline_resolution="high",
        map_boundaries="on",
        map_boundaries_colour="brown",
        map_boundaries_thickness=2,
        map_administrative_boundaries="on", 
        map_administrative_boundaries_colour="brown",
        map_administrative_boundaries_thickness=1, # Spessore regionale rimesso fine
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
        subpage_x_position=5,
        subpage_y_position=12,   
        subpage_x_length=75,
        subpage_y_length=80     
    )

    # CAPOLUOGHI DI PROVINCIA (Sigle testuali)
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

    # RIVOLI
    lat_rivoli = [45.07]
    lon_rivoli = [7.51]

    rivoli_point = mv.input_visualiser(
        input_plot_type="geo_points",
        input_longitude_values=lon_rivoli,
        input_latitude_values=lat_rivoli
    )

    stile_rivoli = mv.msymb(
        legend="off", symbol_type="marker", symbol_colour="brown", 
        symbol_height=0.4, symbol_marker_index=15     
    )

    # STILE PIOGGIA DETTAGLIATO (Da 1 mm in su)
    tp_style = mv.mcont(
        legend="on",                  
        contour="off",                
        contour_shade="on",           
        contour_shade_technique="polygon_shading",
        contour_shade_method="area_fill",
        contour_level_selection_type="level_list",
        contour_level_list=[1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200, 300], # 16 valori = 15 colori
        contour_shade_colour_method="list",
        contour_shade_colour_list=[
            "RGB(0.6, 0.8, 1.0)",  # 1-2
            "RGB(0.0, 0.3, 1.0)",  # 2-5
            "RGB(0.4, 0.9, 0.4)",  # 5-10
            "RGB(0.0, 0.6, 0.0)",  # 10-15
            "RGB(0.6, 0.8, 0.0)",  # 15-20 (Verde/Giallo)
            "RGB(1.0, 0.9, 0.0)",  # 20-25 (Giallo)
            "RGB(0.9, 0.7, 0.0)",  # 25-30
            "RGB(1.0, 0.6, 0.0)",  # 30-40 (Arancio chiaro)
            "RGB(1.0, 0.4, 0.0)",  # 40-50 (Arancio scuro)
            "RGB(1.0, 0.2, 0.0)",  # 50-60 (Rosso/Arancio)
            "RGB(1.0, 0.2, 0.2)",  # 60-80 (Rosso chiaro)
            "RGB(0.7, 0.0, 0.0)",  # 80-100 (Rosso scuro)
            "RGB(0.8, 0.2, 1.0)",  # 100-150
            "RGB(0.5, 0.0, 0.8)",  # 150-200
            "RGB(0.3, 0.0, 0.5)"   # > 200
        ]
    )
    
    legend = mv.mlegend(
        legend_display_type="continuous", legend_box_mode="positional",
        legend_box_x_position=26.5, legend_box_y_position=3.0,   
        legend_box_x_length=1.5, legend_box_y_length=14.0, legend_text_font_size=0.4
    )

    # Ciclo di generazione per 10 giorni
    for i in range(10):
        target_start = indomani_00z + timedelta(days=i)
        target_end = target_start + timedelta(days=1)
        
        step_start = int((target_start - dt_run_utc).total_seconds() / 3600)
        step_end = int((target_end - dt_run_utc).total_seconds() / 3600)
        
        print(f"Elaborazione mappa: {target_start.strftime('%d/%m/%Y')} (Step +{step_start}h / +{step_end}h)")
        
        GRIB_FILE = f"tp_{step_start}_{step_end}.grib"
        PNG_OUTPUT = f"tp_map_{step_start}"
        
        try:
            client.retrieve(
                date=dt_run_utc.strftime("%Y%m%d"),
                time=dt_run_utc.hour,
                step=[step_start, step_end],
                stream="enfo", type="pf", levtype="sfc", param=['tp'],
                target=GRIB_FILE
            )
        except Exception as e:
            print(f"Errore API ECMWF Open Data per gli step {step_start}-{step_end}: {e}")
            continue

        if not os.path.exists(GRIB_FILE):
            continue

        data = mv.read(GRIB_FILE)
        tp_start = data.select(step=step_start)
        tp_end = data.select(step=step_end)
        
        tp_diff_mm = (tp_end - tp_start) * 1000
        tp_mean_mm = mv.mean(tp_diff_mm)

        str_run = dt_run_utc.strftime('%d/%m/%Y %H:%M')
        str_valida = f"{target_start.strftime('%d/%m/%Y')} - {target_end.strftime('%d/%m/%Y')}"

        title = mv.mtext(
            text_lines=[
                f"ECMWF ENS - precipitazioni 24 ore (Run: {str_run} UTC)", 
                str_valida
            ], 
            text_font_size=0.5, text_colour='black'
        )
        
        png = mv.png_output(output_name=PNG_OUTPUT, output_width=1200)
        mv.setoutput(png)
        mv.plot(view, tp_mean_mm, tp_style, capoluoghi, stile_capoluoghi, rivoli_point, stile_rivoli, legend, title)
        
        # Invio su Telegram
        file_generato = f"{PNG_OUTPUT}.1.png"
        caption = f"🌧 Precipitazioni 24h: {str_valida}\n⚙️ Run ENS: {str_run} UTC"
        invia_telegram(file_generato, caption)
        
        # Pulizia file temporanei
        os.remove(GRIB_FILE)
        if os.path.exists(file_generato):
            os.remove(file_generato)
        
        # Attesa per i limiti di Telegram
        if i < 9:
            print("⏳ Pausa di 15 secondi per i limiti di Telegram...")
            time.sleep(15)

def main():
    print("Verifica stato Run ECMWF via Open-Meteo...")
    data = fetch_dati_con_retry()
    if not data:
        sys.exit(0)
        
    hourly = data.get("hourly", {})
    utc_offset = data.get("utc_offset_seconds", 0)
    params_to_check = ["temperature_2m", "temperature_2m_spread", "temperature_500hPa_spread", "geopotential_height_500hPa"]
    
    is_new, nome_run, dt_run_utc = estrai_limiti_run(hourly, params_to_check, utc_offset)
    
    if is_new:
        print(f"🚀 Lancio generazione pluvio per il RUN {nome_run} ({dt_run_utc})")
        genera_mappe_metview(dt_run_utc, nome_run)
    else:
        print("Nessun nuovo run completo trovato. Uscita.")

if __name__ == "__main__":
    main()
