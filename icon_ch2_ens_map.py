import os
import requests
import cartopy.crs as ccrs
from datetime import datetime, timezone

import earthkit.plots
from earthkit.plots.geo import bounds, domains
from earthkit.plots.styles import Style
from earthkit.data import config

from meteodatalab import ogd_api
from meteodatalab.operators import regrid
from rasterio.crs import CRS

# Usa una cache temporanea per non intasare il runner
config.set("cache-policy", "temporary")

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

def genera_mappa_nativa():
    dt_run = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
    
    # 55 ore = 2 giorni e 7 ore (P2DT7H)
    # 101 ore = 4 giorni e 5 ore (P4DT5H)
    lead_times = ["P2DT7H", "P4DT5H"]

    print(f"Scaricamento dati ICON-CH2 EPS per il run {dt_run}...")
    req = ogd_api.Request(
        collection="ogd-forecasting-icon-ch2",
        variable="TOT_PREC",
        ref_time=dt_run,
        perturbed=True,
        lead_time=lead_times,
    )
    
    try:
        tot_prec = ogd_api.get_from_ogd(req)
    except Exception as e:
        print(f"Errore download OGD API: {e}")
        return

    print("Calcolo media ensemble e accumulo (55h -> 101h)...")
    # Calcoliamo la media di tutti gli 11 membri (dimensione 'eps')
    prec_mean = tot_prec.mean(dim="eps")
    
    # L'indice 1 corrisponde a 101h, l'indice 0 a 55h
    prec_diff = prec_mean.isel(lead_time=1) - prec_mean.isel(lead_time=0)

    print("Regridding da griglia icosaedrica a WGS84...")
    # Inquadriamo il Piemonte con risoluzione fine (~2km)
    xmin, xmax = 6.0, 10.5
    ymin, ymax = 43.5, 46.8
    nx, ny = 300, 300
    
    destination = regrid.RegularGrid(
        CRS.from_string("epsg:4326"), nx, ny, xmin, xmax, ymin, ymax
    )
    prec_geo = regrid.iconremap(prec_diff, destination)
    
    print("Generazione grafico con Earthkit-Plots...")
    my_levels = [1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200, 300]
    my_colors = [
        "#99ccff", "#004cff", "#66e666", "#009900", 
        "#99cc00", "#ffe600", "#e6b300", "#ff9900", 
        "#ff6600", "#ff3300", "#ff3333", "#b30000", 
        "#cc33ff", "#8000cc", "#4d0080"
    ]

    map_bbox = bounds.BoundingBox(xmin, xmax, ymin, ymax, ccrs.Geodetic())
    domain = domains.Domain.from_bbox(bbox=map_bbox, name="Piemonte")
    
    chart = earthkit.plots.Map(domain=domain)
    chart.grid_cells(prec_geo, x="lon", y="lat", style=Style(colors=my_colors, levels=my_levels))
    
    # Aggiungiamo Rivoli sulla mappa
    chart.ax.plot(7.51, 45.07, marker='o', color='brown', markersize=6, transform=ccrs.PlateCarree())
    chart.ax.text(7.55, 45.08, 'Rivoli', color='brown', fontsize=10, fontweight='bold', transform=ccrs.PlateCarree())

    chart.land()
    chart.coastlines()
    chart.borders()
    chart.gridlines()
    
    title = f"ICON-CH2 EPS - Accumulo Precipitazioni (Step 55h -> 101h)\nRun: {dt_run.strftime('%d/%m/%Y %H:%M UTC')}"
    chart.title(title)
    
    filename = "mappa_forzata.png"
    chart.save(filename)
    
    invia_telegram(filename, f"🌧 TEST OGD NATIVO: Mappa ICON-CH2 EPS\nAccumulo step 55-101.\n⚙️ Run {dt_run.strftime('%H')}Z")

if __name__ == "__main__":
    genera_mappa_nativa()
