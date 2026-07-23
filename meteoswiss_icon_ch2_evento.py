import os
import sys
import time
import requests
import subprocess
import metview as mv
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_LAST_HOUR = "ultima_ora_icon_ch2_evento.txt"
PNG_OUTPUT = "icon_ch2_evento"

RUN_DURATION = 120
START_DELAY = 1

def estrai_limiti_run(hourly_data: dict, ref_param: str, utc_offset_sec: int):
    times = hourly_data.get("time", [])
    mean_vals = hourly_data.get(ref_param, [])

    if not times or not mean_vals: return False, "", None, ""

    end_idx = -1
    for i in range(len(mean_vals) - 1, -1, -1):
        if mean_vals[i] is not None:
            end_idx = i
            break

    if end_idx == -1: return False, "", None, ""

    ultima_ora_valida_str = times[end_idx]
    dt_end_local = datetime.fromisoformat(ultima_ora_valida_str)
    dt_end_utc = dt_end_local - timedelta(seconds=utc_offset_sec)
    
    dt_run_utc = dt_end_utc - timedelta(hours=RUN_DURATION)
    dt_start_utc = dt_run_utc + timedelta(hours=START_DELAY)

    nome_run = dt_run_utc.strftime("%H") + "Z"
    
    # Controlliamo se abbiamo già tracciato l'elaborazione
    if os.path.exists(FILE_LAST_HOUR):
        with open(FILE_LAST_HOUR, "r") as f:
            ultima_ora_salvata = f.read().strip()
        if ultima_ora_valida_str <= ultima_ora_salvata:
            print(f"✅ Run ICON-CH2 {nome_run} già elaborato per l'evento.")
            return False, "", None, ""

    # Restituiamo i dati, ma non salviamo il file .txt qui!
    return True, nome_run, dt_run_utc, ultima_ora_valida_str

def fetch_dati_openmeteo() -> dict:
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
    headers = {"User-Agent": "MeteoBot-ICONCH2-Evento/11.0"}

    for tentativo in range(3):
        try:
            response = requests.get(URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Errore API Open-Meteo: {e}", file=sys.stderr)
            time.sleep(15)
    return {}

def scarica_grib_stac(dt_run_utc: datetime, target_start: datetime, target_end: datetime):
    base_url = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-forecasting-icon-ch2/items"
    grib_urls = []
    
    str_run_iso_z = dt_run_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    str_run_flat = dt_run_utc.strftime('%Y%m%d%H')
    
    for target in [target_start, target_end]:
        target_str_z = target.strftime('%Y-%m-%dT%H:%M:%SZ')
        print(f"\n🔍 Ricerca STAC mirata per validità: {target_str_z}...")
        
        features = []
        current_url = base_url
        params = {"datetime": target_str_z, "limit": 1000} 
        
        # LOOP DI PAGINAZIONE
        while current_url:
            try:
                res = requests.get(current_url, params=params, timeout=30)
                res.raise_for_status()
                data = res.json()
                
                features.extend(data.get("features", []))
                
                next_link = next((link.get("href") for link in data.get("links", []) if link.get("rel") == "next"), None)
                if next_link:
                    current_url = next_link
                    params = {} # Svuotiamo i parametri per evitare query doppie
                else:
                    current_url = None
            except Exception as e:
                print(f"⚠️ Errore API STAC durante la paginazione: {e}")
                break

        trovato = False
        for feat in features:
            props = feat.get("properties", {})
            ref_time = props.get("forecast:reference_datetime", "")
            feat_str = str(feat)
            
            # Controllo ultra-flessibile sul Run di riferimento
            if str_run_iso_z in ref_time or ref_time.startswith(str_run_iso_z[:-1]) or str_run_flat in feat_str:
                for key, asset in feat.get("assets", {}).items():
                    key_upper = key.upper()
                    href = asset.get("href", "")
                    
                    # Usa "in" per evitare problemi con firme AWS a fine link
                    if ".GRIB2" in href.upper() and "CONSTANTS" not in key_upper:
                        if "TOT_PR" in key_upper or "TOT_PREC" in key_upper or "PRECIP" in key_upper or "tot_pr" in href.lower() or "tot_prec" in href.lower():
                            if "-perturb" in href.lower():
                                grib_urls.append(href)
                                trovato = True
                                print(f" -> OK: Variabile Pioggia EPS individuata [{key}]")
                                break
                            
                if not trovato:
                    # Fallback robusto
                    for key, asset in feat.get("assets", {}).items():
                        href = asset.get("href", "")
                        if ".GRIB2" in href.upper() and "-perturb" in href.lower() and ("pr" in href.lower() or "prec" in href.lower()):
                            grib_urls.append(href)
                            trovato = True
                            print(f" -> OK: Selezionato GRIB precipitazione EPS per fallback [{key}]")
                            break
                            
            if trovato:
                break
                
        if not trovato:
            print(f" -> Nessun file di precipitazione trovato per {target_str_z}.")

    if len(grib_urls) < 2:
        return []

    grib_files = []
    print(f"\n📥 Inizio download streaming da AWS...")
    for i, file_url in enumerate(grib_urls):
        local_filename = f"icon_ch2_precip_{i}.grib2"
        try:
            r = requests.get(file_url, stream=True, timeout=90)
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # CONTROLLO SICUREZZA 1: Peso minimo
            if os.path.getsize(local_filename) < 1000000:
                print(f"❌ File scartato: dimensione troppo piccola (AWS potrebbe aver inviato un errore XML).")
                os.remove(local_filename)
                continue
                
            # CONTROLLO SICUREZZA 2: Magic Bytes GRIB
            with open(local_filename, 'rb') as f:
                header = f.read(4)
                if header != b'GRIB':
                    print(f"❌ File scartato: Non è un GRIB valido. Trovato header: {header}")
                    os.remove(local_filename)
                    continue

            grib_files.append(local_filename)
        except Exception as e:
            print(f"Errore download GRIB: {e}")

    return grib_files

def invia_telegram(file_path, caption):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("\nCredenziali Telegram mancanti. Saltato invio.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": caption}
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as photo:
                resp = requests.post(url, data=payload, files={"photo": photo})
                if resp.status_code == 200:
                    print("\n📸 Mappa dell'Evento inviata con successo su Telegram!")
                    return True
                else:
                    print(f"Errore invio Telegram: {resp.text}")
        except Exception as e:
            print(f"Errore di connessione Telegram: {e}")
    else:
        print(f"File {file_path} non trovato per l'invio.")
    return False

def genera_mappe_metview(dt_run_utc, nome_run, grib_files, target_start, target_end):
    step_start = int((target_start - dt_run_utc).total_seconds() / 3600)
    step_end = int((target_end - dt_run_utc).total_seconds() / 3600)
    
    print(f"\nControllo di integrità anti-crash (Step: +{step_start}h / +{step_end}h)...")
    
    valid_gribs = []
    for f in grib_files:
        try:
            # Controllo con grib_ls prima di passarlo a Metview
            res = subprocess.run(['grib_ls', f], capture_output=True, text=True)
            if "ERROR" in res.stdout or "ERROR" in res.stderr or "mismatch" in res.stderr:
                print(f"❌ ERRORE ecCodes: Il file {f} è troncato a metà. Scartato.")
            elif res.returncode != 0:
                print(f"❌ ERRORE ecCodes: Decodifica fallita (Return code {res.returncode}).")
            else:
                print(f"✅ File {f} perfettamente integro.")
                valid_gribs.append(f)
        except Exception as e:
            print(f"❌ Impossibile validare il file {f}: {e}")

    if len(valid_gribs) < 2:
        print("❌ GRIB validi insufficienti. Uscita sicura annullata per impedire il crash.")
        return False

    data = None
    for f in valid_gribs:
        try:
            temp_fs = mv.read(f)
            data = temp_fs if data is None else data + temp_fs
        except Exception as e:
            print(f"⚠️ Errore interno di Metview nella lettura: {e}")
            return False

    if data is None or len(data) == 0:
        return False
    
    coast = mv.mcoast(
        map_coastline_colour="brown", map_coastline_thickness=2, map_coastline_resolution="high",
        map_boundaries="on", map_boundaries_colour="brown", map_boundaries_thickness=2,
        map_administrative_boundaries="on", map_administrative_boundaries_colour="brown",
        map_administrative_boundaries_thickness=1, map_coastline_land_shade="off", 
        map_coastline_sea_shade="off", map_grid="off", map_label="off"
    )
    
    view = mv.geoview(
        map_area_definition="corners", area=[43.5, 6.0, 46.8, 10.5], coastlines=coast,
        subpage_x_position=5, subpage_y_position=12, subpage_x_length=75, subpage_y_length=80     
    )

    lats = [45.07, 44.38, 44.90, 44.91, 45.32, 45.45, 45.56, 45.92]
    lons = [7.68,  7.55,  8.20,  8.61,  8.42,  8.61,  8.05,  8.55]
    sigle = ["TO", "CN", "AT", "AL", "VC", "NO", "BI", "VB"]

    capoluoghi = mv.input_visualiser(
        input_plot_type="geo_points", input_longitude_values=lons, input_latitude_values=lats
    )
    stile_capoluoghi = mv.msymb(
        legend="off", symbol_type="text", symbol_text_list=sigle,
        symbol_text_font_colour="brown", symbol_text_font_size=0.5, symbol_text_font_style="bold"
    )

    rivoli_point = mv.input_visualiser(
        input_plot_type="geo_points", input_longitude_values=[7.51], input_latitude_values=[45.07]
    )
    stile_rivoli = mv.msymb(
        legend="off", symbol_type="marker", symbol_colour="brown", symbol_height=0.4, symbol_marker_index=15     
    )

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
    
    legend = mv.mlegend(
        legend_display_type="continuous", legend_box_mode="positional",
        legend_box_x_position=26.5, legend_box_y_position=3.0,   
        legend_box_x_length=1.5, legend_box_y_length=14.0, legend_text_font_size=0.4
    )

    tp_start = data.select(step=step_start)
    tp_end = data.select(step=step_end)
    
    if len(tp_start) == 0 or len(tp_end) == 0:
        print(f"❌ Errore: GRIB incompleti. Passati a Metview {len(tp_start)} e {len(tp_end)} membri.")
        return False
        
    tp_diff = tp_end - tp_start
    tp_mean = mv.mean(tp_diff)

    max_val = mv.maxvalue(tp_mean)
    if max_val < 5.0 and max_val > 0.001:
        tp_mean_mm = tp_mean * 1000
    else:
        tp_mean_mm = tp_mean

    str_run = dt_run_utc.strftime('%d/%m/%Y %H:%M')
    str_valida = f"{target_start.strftime('%d/%m/%Y %H:00')} - {target_end.strftime('%d/%m/%Y %H:00')} UTC"

    title = mv.mtext(
        text_lines=[
            f"ICON-CH2-EPS - Accumulo Precipitativo (Run: {str_run} UTC)", 
            str_valida
        ], 
        text_font_size=0.5, text_colour='black'
    )
    
    png = mv.png_output(output_name=PNG_OUTPUT, output_width=1200)
    mv.setoutput(png)
    mv.plot(view, tp_mean_mm, tp_style, capoluoghi, stile_capoluoghi, rivoli_point, stile_rivoli, legend, title)
    
    file_generato = f"{PNG_OUTPUT}.1.png"
    caption_foto = f"🌧 FOCUS EVENTO 24H\n📅 Sab 12:00 - Dom 12:00 (UTC)\n⚙️ Media Ensemble MeteoSvizzera\n🕒 Run: {str_run} UTC"
    
    esito = invia_telegram(file_generato, caption_foto)

    if os.path.exists(file_generato):
        os.remove(file_generato)
    for f in grib_files:
        if os.path.exists(f):
            os.remove(f)
            
    return esito

def main():
    print("Verifica stato Run ICON-CH2 via Open-Meteo...")
    openmeteo_data = fetch_dati_openmeteo()
    
    if not openmeteo_data:
        sys.exit(0)
        
    hourly = openmeteo_data.get("hourly", {})
    utc_offset = openmeteo_data.get("utc_offset_seconds", 0)
    
    is_new, nome_run, dt_run_utc, str_to_save = estrai_limiti_run(hourly, "temperature_2m", utc_offset)
    
    if is_new:
        target_start = datetime(2026, 7, 25, 12, 0)
        target_end = datetime(2026, 7, 26, 12, 0)
        
        step_end = int((target_end - dt_run_utc).total_seconds() / 3600)
        step_start = int((target_start - dt_run_utc).total_seconds() / 3600)
        
        if step_end > 120:
            print(f"L'evento esce dalla coda di previsione a 120h (+{step_end}h). Uscita.")
            sys.exit(0)
            
        if step_start < 0:
            print("L'inizio dell'evento è già passato rispetto al run attuale. Uscita.")
            sys.exit(0)
        
        grib_files = scarica_grib_stac(dt_run_utc, target_start, target_end)
        
        if len(grib_files) == 2:
            print(f"\n🚀 Avvio mapping in Metview per l'evento")
            success = genera_mappe_metview(dt_run_utc, nome_run, grib_files, target_start, target_end)
            
            # Salvataggio nel file solo se l'invio è andato a buon fine
            if success:
                with open(FILE_LAST_HOUR, "w") as f:
                    f.write(str_to_save)
                print("Dati tracciati con successo.")
        else:
            print("\n⚠️ I dati necessari non sono ancora disponibili su AWS.")
            print("Il run è in fase di upload o il link è scaduto. Riprova al prossimo ciclo.")
    else:
        print("Uscita.")

if __name__ == "__main__":
    main()
