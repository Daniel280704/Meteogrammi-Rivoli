import os
import sys
import time
import json
import glob
import requests
import urllib3
import pytz
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
import warnings

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.shapereader as shpreader
from shapely.ops import unary_union

import earthkit.plots
from earthkit.plots.geo import bounds, domains
from earthkit.plots.styles import Style
from earthkit.data import config

from meteodatalab import ogd_api
from meteodatalab.operators import regrid
from rasterio.crs import CRS

warnings.filterwarnings('ignore')
urllib3.disable_warnings()
config.set("cache-policy", "temporary")

LATITUDE = 45.07
LONGITUDE = 7.54
FILE_LAST_HOUR = "ultima_ora_icon_ch2_hourly.txt"

def estrai_limiti_run(hourly_data: dict, ref_param: str) -> tuple[bool, str, datetime]:
    times = hourly_data.get("time", [])
    mean_vals = hourly_data.get(ref_param, [])
    if not times or not mean_vals: return False, "", None
    
    end_idx = -1
    for i in range(len(mean_vals) - 1, -1, -1):
        if mean_vals[i] is not None:
            end_idx = i
            break
            
    if end_idx == -1: return False, "", None
    
    rome_tz = pytz.timezone("Europe/Rome")
    ultima_ora_valida_str = times[end_idx]
    
    dt_end_local = rome_tz.localize(datetime.fromisoformat(ultima_ora_valida_str))
    dt_end_utc = dt_end_local.astimezone(timezone.utc)
    
    dt_run_utc = dt_end_utc - timedelta(hours=120)
    dt_start_local = (dt_run_utc + timedelta(hours=1)).astimezone(rome_tz)
    start_time_str = dt_start_local.strftime("%Y-%m-%dT%H:%M")
    
    try:
        start_idx = times.index(start_time_str)
    except ValueError:
        return False, "", None
        
    expected_points = 120
    actual_points = end_idx - start_idx + 1
    nome_run = dt_run_utc.strftime("%H") + "Z"
    
    if actual_points < expected_points:
        print(f"⏳ Run {nome_run} in caricamento... ({actual_points}/{expected_points} ore)")
        return False, "", None
        
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
    for _ in range(3):
        try:
            r = requests.get(URL, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            time.sleep(15)
    return {}

def invia_album_telegram(file_paths: list, caption: str):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return
    
    # Se c'è solo un'immagine, si usa l'endpoint standard sendPhoto
    if len(file_paths) == 1:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            with open(file_paths[0], "rb") as photo:
                requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"photo": photo})
        except Exception as e:
            print(f"Errore invio singola foto: {e}")
        return

    # Endpoint MediaGroup per l'Album (da 2 a 10 foto)
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    media = []
    files = {}
    
    for idx, path in enumerate(file_paths):
        media.append({
            "type": "photo",
            "media": f"attach://photo_{idx}",
            "caption": caption if idx == 0 else ""
        })
        files[f"photo_{idx}"] = open(path, "rb")

    try:
        requests.post(url, data={"chat_id": chat_id, "media": json.dumps(media)}, files=files)
        print(f"📸 Album Telegram inviato con successo ({len(file_paths)} mappe).")
    except Exception as e:
        print(f"Errore invio album Telegram: {e}")
    finally:
        for f in files.values():
            f.close()

def raggruppa_in_blocchi(dt_run_local: datetime) -> dict:
    """Raggruppa le 120 ore di previsione nei 4 blocchi di album locali."""
    blocchi = {}
    
    for h in range(1, 121):
        dt_target = dt_run_local + timedelta(hours=h)
        date_str = dt_target.date().strftime("%Y-%m-%d")
        hour = dt_target.hour
        
        # Gestione dell'ora 00:00 che appartiene al blocco 18-24 del giorno precedente
        if hour == 0:
            date_str = (dt_target.date() - timedelta(days=1)).strftime("%Y-%m-%d")
            b_name = "18-24"
        elif 1 <= hour <= 6: b_name = "00-06"
        elif 7 <= hour <= 12: b_name = "06-12"
        elif 13 <= hour <= 18: b_name = "12-18"
        else: b_name = "18-24"
            
        key = f"{date_str} (Fascia {b_name})"
        if key not in blocchi:
            blocchi[key] = []
        blocchi[key].append(h)
        
    return blocchi

def genera_album_orari(dt_run_utc: datetime, nome_run: str):
    rome_tz = pytz.timezone("Europe/Rome")
    dt_run_local = dt_run_utc.astimezone(rome_tz)
    
    blocchi = raggruppa_in_blocchi(dt_run_local)

    # 1. Configurazione Regridding e Stile (Ottimizzati per pioggia oraria)
    xmin, xmax, ymin, ymax = 6.0, 10.5, 43.5, 46.8
    nx, ny = 300, 300
    destination = regrid.RegularGrid(CRS.from_string("epsg:4326"), nx, ny, xmin, xmax, ymin, ymax)

    # Livelli ribassati per apprezzare piogge orarie deboli
    my_levels = [0.2, 0.5, 1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200]
    my_colors = ["#99ccff", "#004cff", "#66e666", "#009900", "#99cc00", "#ffe600", "#e6b300", "#ff9900", "#ff6600", "#ff3300", "#ff3333", "#b30000", "#cc33ff", "#8000cc", "#4d0080"]
    domain = domains.Domain.from_bbox(bbox=bounds.BoundingBox(xmin, xmax, ymin, ymax, ccrs.Geodetic()), name="Piemonte")

    # Elaborazione dinamica dei confini da Shapefile
    prov_geoms = []
    shp_list = glob.glob("**/*ProvCM*.shp", recursive=True)
    if shp_list:
        shp_path = shp_list[0]
        try:
            for record in shpreader.Reader(shp_path).records():
                if any("piemonte" in str(v).lower() for v in record.attributes.values()):
                    prov_geoms.append(record.geometry)
            if not prov_geoms:
                prov_geoms = [r.geometry for r in shpreader.Reader(shp_path).records()]
        except Exception: pass

    if not prov_geoms:
        ne_path = shpreader.natural_earth(resolution='10m', category='cultural', name='admin_1_states_provinces')
        for record in shpreader.Reader(ne_path).records():
            if record.attributes.get('name', '').lower() == 'piemonte':
                prov_geoms.append(record.geometry)

    prov_feature, regione_feature = None, None
    if prov_geoms:
        prov_feature = cfeature.ShapelyFeature(prov_geoms, ccrs.PlateCarree(), edgecolor='black', facecolor='none', linewidth=0.5, linestyle=':', zorder=10)
        regione_geom = unary_union(prov_geoms)
        regione_feature = cfeature.ShapelyFeature([regione_geom], ccrs.PlateCarree(), edgecolor='black', facecolor='none', linewidth=2.0, linestyle='-', zorder=11)

    lats = [45.07, 44.38, 44.90, 44.91, 45.32, 45.45, 45.56, 45.92]
    lons = [7.68,  7.55,  8.20,  8.61,  8.42,  8.61,  8.05,  8.55]
    sigle = ["TO", "CN", "AT", "AL", "VC", "NO", "BI", "VB"]

    # 2. Elaborazione ciclica per blocchi (Risparmio RAM)
    for block_name, ore_list in blocchi.items():
        print(f"\nGenerazione album: {block_name}")
        
        # Per calcolare la pioggia dell'ora H, serve il dato H e H-1.
        lead_times_needed = list(ore_list)
        if ore_list[0] > 1:
            lead_times_needed.insert(0, ore_list[0] - 1)
            
        lead_times_str = [f"P{l // 24}DT{l % 24}H" for l in lead_times_needed]

        req = ogd_api.Request(
            collection="ogd-forecasting-icon-ch2",
            variable="TOT_PREC",
            ref_time=dt_run_utc,
            perturbed=True,
            lead_time=lead_times_str,
        )
        
        try:
            tot_prec = ogd_api.get_from_ogd(req)
            prec_mean = tot_prec.mean(dim="eps")
        except Exception as e:
            print(f"Salto il blocco {block_name} causa errore download: {e}")
            continue

        percorsi_foto = []
        
        for h in ore_list:
            if h == 1:
                # Per la prima ora di forecast, il cumulato +1H è direttamente la pioggia oraria
                prec_diff = prec_mean.sel(lead_time=np.timedelta64(h, 'h'))
            else:
                prec_diff = prec_mean.sel(lead_time=np.timedelta64(h, 'h')) - prec_mean.sel(lead_time=np.timedelta64(h-1, 'h'))

            prec_geo = regrid.iconremap(prec_diff, destination)

            chart = earthkit.plots.Map(domain=domain)
            chart.grid_cells(prec_geo, x="lon", y="lat", style=Style(colors=my_colors, levels=my_levels))

            if regione_feature: chart.ax.add_feature(regione_feature)
            if prov_feature: chart.ax.add_feature(prov_feature)
            chart.coastlines(linewidth=0.5)

            chart.ax.plot(7.51, 45.07, marker='o', color='brown', markersize=6, transform=ccrs.PlateCarree(), zorder=12)
            for lon, lat, sigla in zip(lons, lats, sigle):
                chart.ax.plot(lon, lat, marker='o', color='black', markersize=3, transform=ccrs.PlateCarree(), zorder=12)
                chart.ax.text(lon + 0.05, lat + 0.05, sigla, color='black', fontsize=9, fontweight='bold', transform=ccrs.PlateCarree(), zorder=12)

            start_local = dt_run_local + timedelta(hours=h-1)
            end_local = dt_run_local + timedelta(hours=h)
            str_valida = f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M del %d/%m')}"

            title = f"ICON-CH2 EPS - Precipitazione Oraria (mm/h)\nRun: {dt_run_utc.strftime('%d/%m/%Y %H:%M UTC')} | {str_valida}"
            chart.title(title)
            chart.legend(label="Precipitazioni (mm/h)")

            filename = f"oraria_{h}.png"
            chart.save(filename)
            percorsi_foto.append(filename)
            
            plt.close(chart.fig)
        
        # Invio Album per questo blocco
        caption_album = f"🌧 ICON-CH2 EPS: Dettaglio Orario\n🗓 {block_name}\n⚙️ Run {nome_run}"
        invia_album_telegram(percorsi_foto, caption_album)
        
        # Pulizia RAM e File per passare al blocco successivo in sicurezza
        for f in percorsi_foto:
            if os.path.exists(f): os.remove(f)
        del tot_prec, prec_mean
        time.sleep(15)

def main():
    print("Cerco l'ultimo run completo ICON-CH2 via Open-Meteo...")
    data = fetch_dati_con_retry()
    if not data: sys.exit(0)
        
    hourly = data.get("hourly", {})
    is_new, nome_run, dt_run_utc = estrai_limiti_run(hourly, "temperature_2m")
    
    if is_new:
        print(f"🚀 Lancio generazione Album Orari ICON-CH2 per il RUN {nome_run} ({dt_run_utc})")
        genera_album_orari(dt_run_utc, nome_run)
    else:
        print("Nessun nuovo run completo trovato. Uscita.")

if __name__ == "__main__":
    main()