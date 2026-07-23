import os
import sys
import time
import json
import requests
import subprocess
import metview as mv
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_LAST_HOUR = "ultima_ora_icon_ch2_giornaliero.txt"
RUN_DURATION = 120
START_DELAY = 1

def estrai_limiti_run(hourly_data: dict, ref_param: str, utc_offset_sec: int):
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
    dt_start_utc = dt_run_utc + timedelta(hours=START_DELAY)

    nome_run = dt_run_utc.strftime("%H") + "Z"
    expected_points = RUN_DURATION - START_DELAY + 1
    
    dt_start_local = dt_start_utc + timedelta(seconds=utc_offset_sec)
    start_time_str = dt_start_local.strftime("%Y-%m-%dT%H:%M")
    
    try:
        start_idx = times.index(start_time_str)
        actual_points = end_idx - start_idx + 1
    except ValueError:
        actual_points = 0

    if actual_points < expected_points:
        print(f"⏳ Run ICON-CH2 {nome_run} in caricamento... ({actual_points}/{expected_points} ore)")
        return False, "", None

    if os.path.exists(FILE_LAST_HOUR):
        with open(FILE_LAST_HOUR, "r") as f:
            ultima_ora_salvata = f.read().strip()
        if ultima_ora_valida_str <= ultima_ora_salvata:
            print(f"✅ Run ICON-CH2 {nome_run} giornaliero già elaborato.")
            return False, "", None

    with open(FILE_LAST_HOUR, "w") as f:
        f.write(ultima_ora_valida_str)

    return True, nome_run, dt_run_utc

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
    headers = {"User-Agent": "MeteoBot-ICONCH2-Daily/4.0"}

    for tentativo in range(3):
        try:
            response = requests.get(URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Errore API Open-Meteo: {e}", file=sys.stderr)
            time.sleep(15)
    return {}

def scarica_grib_per_orari(dt_run_utc: datetime, orari_utc_set: set):
    base_url = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-forecasting-icon-ch2/items"
    grib_files = []
    
    for target in sorted(list(orari_utc_set)):
        target_str_z = target.strftime('%Y-%m-%dT%H:%M:%SZ')
        print(f"\n🔍 Ricerca STAC mirata per validità: {target_str_z}...")
        
        features = []
        current_url = base_url
        params = {"datetime": target_str_z, "limit": 1000} 
        
        while current_url:
            try:
                res = requests.get(current_url, params=params, timeout=30)
                res.raise_for_status()
                data = res.json()
                features.extend(data.get("features", []))
                
                next_link = next((link.get("href") for link in data.get("links", []) if link.get("rel") == "next"), None)
                if next_link:
                    current_url = next_link
                    params = {} 
                else:
                    current_url = None 
            except Exception as e:
                print(f"⚠️ Errore API STAC durante la paginazione: {e}")
                break

        str_run_iso = dt_run_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        trovato = False
        
        for feat in features:
            if str_run_iso in feat.get("properties", {}).get("forecast:reference_datetime", "") or str_run_iso in str(feat):
                for key, asset in feat.get("assets", {}).items():
                    key_upper = key.upper()
                    href = asset.get("href", "")
                    if href.upper().endswith(".GRIB2") and "CONSTANTS" not in key_upper:
                        if "TOT_PR" in key_upper or "TOT_PREC" in key_upper or "PRECIP" in key_upper or "TP" in key_upper:
                            grib_files.append((target, href))
                            trovato = True
                            print(f" -> OK: Pioggia individuata [{key}]")
                            break
                if not trovato:
                    for key, asset in feat.get("assets", {}).items():
                        href = asset.get("href", "")
                        if href.upper().endswith(".GRIB2") and "CONSTANTS" not in key_upper:
                            grib_files.append((target, href))
                            trovato = True
                            print(f" -> OK: GRIB generico [{key}]")
                            break
            if trovato:
                break
                
        if not trovato:
            if target == dt_run_utc:
                print(" -> Step +0h: Precipitazione assente (partenza a zero confermata).")
            else:
                print(f" -> Nessun file trovato per {target_str_z}.")

    scaricati = []
    print(f"\n📥 Inizio download dei file GRIB2 necessari da AWS...")
    for i, (target, file_url) in enumerate(grib_files):
        local_filename = f"icon_ch2_precip_T{i}.grib2"
        try:
            r = requests.get(file_url, stream=True, timeout=60)
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            scaricati.append(local_filename)
        except Exception as e:
            print(f"Errore download GRIB: {e}")

    return scaricati

def invia_album_telegram(file_paths, caption_testo):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("\nCredenziali Telegram mancanti. Saltato invio.")
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

    if not media: return

    payload = {"chat_id": chat_id, "media": json.dumps(media)}
    try:
        response = requests.post(url, data=payload, files=files)
        if response.status_code == 200:
            print(f"📸 Album di {len(media)} foto inviato con successo su Telegram!")
        else:
            print(f"Errore invio album: {response.text}")
    except Exception as e:
        print(f"Errore connessione Telegram: {e}")
    finally:
        for f in opened_files:
            f.close()

def genera_mappe_metview(dt_run_utc, nome_run, grib_files, intervalli):
    print(f"\nVerifica integrità e decodifica di {len(grib_files)} file GRIB...")
    valid_gribs = []
    for f in grib_files:
        if os.path.exists(f) and os.path.getsize(f) > 5000:
            try:
                subprocess.run(['grib_ls', f], check=True, capture_output=True)
                valid_gribs.append(f)
            except subprocess.CalledProcessError:
                print(f"❌ ERRORE ecCodes: File corrotto -> {f}")
    
    if not valid_gribs:
        print("❌ Nessun GRIB valido dopo il controllo. Uscita.")
        return

    data = None
    for f in valid_gribs:
        try:
            fs = mv.read(f)
            data = fs if data is None else data + fs
        except Exception:
            pass

    if data is None or len(data) == 0: return

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

    file_generati = []

    for i, intervallo in enumerate(intervalli):
        start_utc = intervallo['start_utc']
        end_utc = intervallo['end_utc']
        data_str = intervallo['local_date']
        
        step_start = int((start_utc - dt_run_utc).total_seconds() / 3600)
        step_end = int((end_utc - dt_run_utc).total_seconds() / 3600)
        
        tp_end = data.select(step=step_end)
        if len(tp_end) == 0: continue
            
        tp_start = data.select(step=step_start)
        
        if len(tp_start) == 0:
            if step_start == 0:
                tp_diff = tp_end
            else:
                continue
        else:
            tp_diff = tp_end - tp_start
            
        tp_mean = mv.mean(tp_diff)
        
        max_val = mv.maxvalue(tp_mean)
        if max_val < 5.0 and max_val > 0.001:
            tp_mean_mm = tp_mean * 1000
        else:
            tp_mean_mm = tp_mean

        png_name = f"icon_ch2_day_{i}"
        
        titolo_riga_1 = f"{data_str} (Accumulo calcolato dalle 00:00 alle 23:59 Locali)"
        titolo_riga_2 = f"Limiti UTC effettivi per questa mappa: {start_utc.strftime('%H:%M')} - {end_utc.strftime('%H:%M')} UTC"

        title = mv.mtext(text_lines=[titolo_riga_1, titolo_riga_2], text_font_size=0.5, text_colour='black')
        
        png = mv.png_output(output_name=png_name, output_width=1200)
        mv.setoutput(png)
        mv.plot(view, tp_mean_mm, tp_style, capoluoghi, stile_capoluoghi, rivoli_point, stile_rivoli, legend, title)
        
        file_generati.append(f"{png_name}.1.png")

    if file_generati:
        str_run_finale = dt_run_utc.strftime('%d/%m/%Y %H:%M')
        caption_album = f"🌧 Precipitazioni Giornaliere\n📅 Da mezzanotte a mezzanotte (ora locale)\n⚙️ Media Ensemble MeteoSvizzera\n🕒 Run: {str_run_finale} UTC"
        invia_album_telegram(file_generati, caption_album)

    # Pulizia disco
    for f in file_generati:
        if os.path.exists(f): os.remove(f)
    for f in grib_files:
        if os.path.exists(f): os.remove(f)

def main():
    print("Verifica stato Run ICON-CH2 via Open-Meteo...")
    openmeteo_data = fetch_dati_openmeteo()
    if not openmeteo_data: sys.exit(0)
        
    hourly = openmeteo_data.get("hourly", {})
    utc_offset = openmeteo_data.get("utc_offset_seconds", 0)
    
    is_new, nome_run, dt_run_utc = estrai_limiti_run(hourly, "temperature_2m", utc_offset)
    
    if is_new:
        dt_run_local = dt_run_utc + timedelta(seconds=utc_offset)
        
        intervalli = []
        orari_necessari = set()
        
        print("\nCalcolo delle fasce temporali (Mezzanotte-Mezzanotte locale):")
        # Ciclo sui 6 giorni coperti dal modello (fino a 120h)
        for i in range(6):
            start_local = (dt_run_local + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_local = start_local + timedelta(days=1)
            
            start_utc = start_local - timedelta(seconds=utc_offset)
            end_utc = end_local - timedelta(seconds=utc_offset)
            
            # Taglio dei paletti se sforano l'inizio del run o la fine delle 120h
            start_utc = max(start_utc, dt_run_utc)
            end_utc = min(end_utc, dt_run_utc + timedelta(hours=120))
            
            if start_utc >= end_utc:
                continue
                
            intervalli.append({
                "local_date": start_local.strftime('%d/%m/%Y'),
                "start_utc": start_utc,
                "end_utc": end_utc
            })
            orari_necessari.add(start_utc)
            orari_necessari.add(end_utc)
            
            print(f" -> {start_local.strftime('%d/%m/%Y')} | Dalle {start_utc.strftime('%H:%M')} alle {end_utc.strftime('%H:%M')} UTC")
            
        grib_files = scarica_grib_per_orari(dt_run_utc, orari_necessari)
        if grib_files:
            genera_mappe_metview(dt_run_utc, nome_run, grib_files, intervalli)
    else:
        print("Uscita.")

if __name__ == "__main__":
    main()