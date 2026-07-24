import os
import time
import json
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
FILE_LAST_HOUR = "ultima_ora_icon_ch2_master.txt"

# Funzioni di trasformazione
to_celsius = lambda x: x - 273.15
to_kmh = lambda x: x * 3.6
to_hpa = lambda x: x / 100
identity = lambda x: x

# Configurazione MASTER di tutte le variabili richieste
VARS_CONFIG = {
    # --- TERMODINAMICA E INDICI CONVETTIVI ---
    "MUCAPE": {"var": "CAPE_MU", "name": "MUCAPE", "unit": "J/kg", "cmap": "plasma", "transform": identity},
    "MLCAPE": {"var": "CAPE_ML", "name": "MLCAPE", "unit": "J/kg", "cmap": "plasma", "transform": identity},
    "CINMU": {"var": "CIN_MU", "name": "MUCIN", "unit": "J/kg", "cmap": "viridis_r", "transform": identity},
    "CINML": {"var": "CIN_ML", "name": "MLCIN", "unit": "J/kg", "cmap": "viridis_r", "transform": identity},
    "LCL_ML": {"var": "LCL_ML", "name": "Lifting Condensation Level", "unit": "m", "cmap": "viridis_r", "transform": identity},
    "LFC_ML": {"var": "LFC_ML", "name": "Level of Free Convection", "unit": "m", "cmap": "plasma_r", "transform": identity},
    "SLI": {"var": "SLI", "name": "Surface Lifted Index", "unit": "K", "cmap": "Spectral", "transform": identity},
    "SDI_2": {"var": "SDI_2", "name": "Supercell Detection Index 2", "unit": "", "cmap": "magma", "transform": identity},
    
    # --- FULMINAZIONI E GRANDINE ---
    "LPI": {"var": "LPI", "name": "Lightning Potential Index", "unit": "J/kg", "cmap": "inferno", "transform": identity},
    "LPI_MAX": {"var": "LPI_MAX", "name": "Max Lightning Potential Index", "unit": "J/kg", "cmap": "inferno", "transform": identity},
    "HAIL": {"var": "DHAIL_MAX", "name": "Dimensione Max Grandine", "unit": "mm", "cmap": "Purples", "transform": identity},
    
    # --- NUBI E VISIBILITÀ ---
    "CLCL": {"var": "CLCL", "name": "Cloud Cover (Low)", "unit": "%", "cmap": "Blues", "transform": lambda x: x * 100},
    "CLCM": {"var": "CLCM", "name": "Cloud Cover (Medium)", "unit": "%", "cmap": "Blues", "transform": lambda x: x * 100},
    "CLCH": {"var": "CLCH", "name": "Cloud Cover (High)", "unit": "%", "cmap": "Blues", "transform": lambda x: x * 100},
    "CB_SC": {"var": "CB_SC", "name": "Cloud Base (Shallow Conv.)", "unit": "m", "cmap": "cividis", "transform": identity},
    "CT_SC": {"var": "CT_SC", "name": "Cloud Top (Shallow Conv.)", "unit": "m", "cmap": "cividis", "transform": identity},
    "VIS": {"var": "VIS", "name": "Visibilità", "unit": "m", "cmap": "Greys_r", "transform": identity},
    
    # --- RADIAZIONE E SUPERFICIE ---
    "DURSUN": {"var": "DURSUN", "name": "Sunshine Duration", "unit": "s", "cmap": "Wistia", "transform": identity},
    "PMSL": {"var": "PMSL", "name": "Pressione MSL", "unit": "hPa", "cmap": "coolwarm", "transform": to_hpa},
    
    # --- UMIDITÀ, PRECIPITAZIONI E NEVE ---
    "QV_2M": {"var": "QV_2M", "name": "Specific Humidity 2m", "unit": "kg/kg", "cmap": "GnBu", "transform": identity},
    "TQV": {"var": "TQV", "name": "Total Column Water Vapour", "unit": "kg/m2", "cmap": "YlGnBu", "transform": identity},
    "GRAUPEL": {"var": "GRAUPEL_GSP", "name": "Graupel", "unit": "kg/m2", "cmap": "PuBu", "transform": identity},
    "HZEROCL": {"var": "HZEROCL", "name": "Zero termico (0°C Isotherm)", "unit": "m", "cmap": "jet", "transform": identity},
    "SNOWLMT": {"var": "SNOWLMT", "name": "Quota Neve", "unit": "m", "cmap": "cool", "transform": identity},
    "H_SNOW": {"var": "H_SNOW", "name": "Snow Depth", "unit": "m", "cmap": "Blues", "transform": identity},
    "RHO_SNOW": {"var": "RHO_SNOW", "name": "Snow Density", "unit": "kg/m3", "cmap": "BuPu", "transform": identity},
    
    # --- TEMPERATURE (Superficie) ---
    "T_2M": {"var": "T_2M", "name": "Temperatura 2m", "unit": "°C", "cmap": "Spectral_r", "transform": to_celsius},
    "TD_2M": {"var": "TD_2M", "name": "Dew Point 2m", "unit": "°C", "cmap": "Spectral_r", "transform": to_celsius},
    
    # --- VENTO ---
    "VMAX_10M": {"var": "VMAX_10M", "name": "Raffica Max 10m", "unit": "km/h", "cmap": "hot_r", "transform": to_kmh}
}

# Aggiunta dinamica delle temperature ai vari piani isobarici
pressure_levels = [975, 950, 925, 900, 850, 800, 700, 500]
for pl in pressure_levels:
    key = f"T_{pl}"
    VARS_CONFIG[key] = {
        "var": "T",
        "collection": "ogd-forecasting-icon-ch2-pl",
        "level": pl,
        "name": f"Temperatura {pl} hPa",
        "unit": "°C",
        "cmap": "Spectral_r",
        "transform": to_celsius
    }

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
    start_time_str = (dt_run_utc + timedelta(hours=1)).astimezone(rome_tz).strftime("%Y-%m-%dT%H:%M")
    
    try:
        start_idx = times.index(start_time_str)
    except ValueError:
        return False, "", None
        
    expected_points = 120
    actual_points = end_idx - start_idx + 1
    nome_run = dt_run_utc.strftime("%H") + "Z"
    
    if actual_points < expected_points:
        print(f"⏳ Run {nome_run} in caricamento... ({actual_points}/{expected_points})")
        return False, "", None
        
    if os.path.exists(FILE_LAST_HOUR):
        with open(FILE_LAST_HOUR, "r") as f:
            if ultima_ora_valida_str <= f.read().strip():
                print(f"✅ Run {nome_run} già elaborato.")
                return False, "", None

    with open(FILE_LAST_HOUR, "w") as f:
        f.write(ultima_ora_valida_str)

    return True, nome_run, dt_run_utc

def fetch_verifica() -> dict:
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {"latitude": LATITUDE, "longitude": LONGITUDE, "hourly": "temperature_2m", "models": "meteoswiss_icon_ch2_ensemble_mean", "timezone": "Europe/Rome", "past_days": 1, "forecast_days": 6}
    for attempt in range(3):
        try:
            r = requests.get(URL, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except:
            time.sleep(15)
    return {}

def invia_album_telegram(file_paths: list, caption: str):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id or not file_paths: return
    
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    media, files = [], {}
    
    for idx, path in enumerate(file_paths):
        if not os.path.exists(path): continue
        media.append({"type": "photo", "media": f"attach://photo_{idx}", "caption": caption if idx == 0 else ""})
        files[f"photo_{idx}"] = open(path, "rb")

    if not files: return
    try:
        requests.post(url, data={"chat_id": chat_id, "media": json.dumps(media)}, files=files)
        print(f"📸 Album inviato con successo ({len(files)} mappe).")
    except Exception as e:
        print(f"❌ Errore invio album: {e}")
    finally:
        for f in files.values(): f.close()

def genera_mappe(dt_run_utc: datetime, nome_run: str):
    rome_tz = pytz.timezone("Europe/Rome")
    dt_run_local = dt_run_utc.astimezone(rome_tz)
    
    # Per limitare l'enorme tempo di calcolo di 35 variabili, raggruppiamo a step di 3 ore (0, 3, 6...)
    # Se vuoi step orari cambia range(1, 121, 3) in range(1, 121)
    ore_list = list(range(3, 121, 3)) 
    lead_times_str = [f"P{l // 24}DT{l % 24}H" for l in ore_list]

    xmin, xmax, ymin, ymax = 6.0, 10.5, 43.5, 46.8
    nx, ny = 300, 300
    destination = regrid.RegularGrid(CRS.from_string("epsg:4326"), nx, ny, xmin, xmax, ymin, ymax)
    domain = domains.Domain.from_bbox(bbox=bounds.BoundingBox(xmin, xmax, ymin, ymax, ccrs.Geodetic()), name="Piemonte")

    regions_feature = cfeature.NaturalEarthFeature('cultural', 'admin_1_states_provinces', '10m', edgecolor='black', facecolor='none', linewidth=1.5)
    
    for key, cfg in VARS_CONFIG.items():
        print(f"\n🔄 Elaborazione variabile: {cfg['name']} ({cfg['var']})")
        
        # Imposta la collection (surface vs pressure levels)
        collection = cfg.get("collection", "ogd-forecasting-icon-ch2")
        
        req_params = {
            "collection": collection,
            "variable": cfg["var"],
            "ref_time": dt_run_utc,
            "perturbed": True,
            "lead_time": lead_times_str
        }
        
        # Aggiungi il livello se è una variabile in quota
        if "level" in cfg:
            req_params["level"] = cfg["level"]
            
        req = ogd_api.Request(**req_params)
        
        try:
            data_raw = ogd_api.get_from_ogd(req)
            data_mean = data_raw.mean(dim="eps")
        except Exception as e:
            print(f"⚠️ Variabile {key} non trovata o errore API: {e}. Salto.")
            continue

        percorsi_foto = []
        
        # Suddividiamo l'invio in pacchetti da 10 foto (limite Telegram per gli album)
        chunk_size = 10
        chunks = [ore_list[i:i + chunk_size] for i in range(0, len(ore_list), chunk_size)]
        
        for chunk in chunks:
            for h in chunk:
                try:
                    data_step = data_mean.sel(lead_time=np.timedelta64(h, 'h'))
                    data_geo = regrid.iconremap(data_step, destination)
                    data_geo = cfg["transform"](data_geo)

                    chart = earthkit.plots.Map(domain=domain)
                    # Usiamo il cmap dinamico; senza levels definiti earthkit adatta la scala min/max automaticamente
                    chart.grid_cells(data_geo, x="lon", y="lat", style=Style(colors=cfg["cmap"]))

                    chart.ax.add_feature(regions_feature)
                    chart.borders()
                    
                    # Riferimenti geografici (Torino)
                    chart.ax.plot(7.68, 45.07, marker='o', color='black', markersize=4, transform=ccrs.PlateCarree(), zorder=12)

                    dt_valida = dt_run_local + timedelta(hours=h)
                    str_valida = dt_valida.strftime('%H:%M del %d/%m')

                    chart.title(f"ICON-CH2 EPS - {cfg['name']} ({cfg['unit']})\nRun: {nome_run} | Valida: {str_valida}")
                    chart.legend(label=f"{cfg['name']} ({cfg['unit']})")
                    
                    f_name = f"{key}_{h}.png"
                    chart.save(f_name)
                    percorsi_foto.append(f_name)
                    plt.close(chart.fig)
                except Exception as step_err:
                    print(f"Errore nello step {h}h per {key}: {step_err}")

            if percorsi_foto:
                caption = f"📊 ICON-CH2 EPS: {cfg['name']} ({cfg['unit']})\n⚙️ Run {nome_run} | Step: +{chunk[0]}h a +{chunk[-1]}h"
                invia_album_telegram(percorsi_foto, caption)
                for f in percorsi_foto:
                    if os.path.exists(f): os.remove(f)
                percorsi_foto = []
                
        del data_raw, data_mean
        time.sleep(10) # Pausa critica per evitare ban da parte di MeteoSwiss

def main():
    data = fetch_verifica()
    if not data: return
    hourly = data.get("hourly", {})
    is_new, nome_run, dt_run_utc = estrai_limiti_run(hourly, "temperature_2m")
    if is_new:
        genera_mappe(dt_run_utc, nome_run)

if __name__ == "__main__":
    main()