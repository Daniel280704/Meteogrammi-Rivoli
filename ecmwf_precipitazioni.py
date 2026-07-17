import os
import sys
import hashlib
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import warnings

# Ignoriamo i warning per i calcoli su array vuoti
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_ecmwf_precip_cape.txt"
FILENAME = "ecmwf_precip_cape_profile.png"

def verifica_dati_nuovi(daily_data: dict) -> bool:
    """Verifica l'hash basandosi sul primo membro dell'ensemble."""
    stringa_dati = str(daily_data.get("rain_sum_member_0", [])).encode('utf-8')
    hash_attuale = hashlib.md5(stringa_dati).hexdigest()
    
    is_nuovo = True
    if os.path.exists(FILE_HASH):
        with open(FILE_HASH, "r") as f:
            if f.read().strip() == hash_attuale:
                is_nuovo = False

    if is_nuovo:
        with open(FILE_HASH, "w") as f:
            f.write(hash_attuale)
    return is_nuovo

def main():
    print("Scaricamento di tutti i 51 membri ECMWF in corso...")
    
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": "rain_sum,snowfall_sum,cape_max",
        "models": "ecmwf_ifs025",
        "timezone": "Europe/Rome",
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter/5.1"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily", {})
    except Exception as e:
        print(f"❌ Errore download: {e}", file=sys.stderr)
        sys.exit(1)

    if not verifica_dati_nuovi(daily):
        sys.exit(0)
        
    daily_times = pd.to_datetime(daily.get("time")) + pd.Timedelta(hours=12)

    # Estrazione matrice (51 membri x 14 giorni)
    def get_ensemble_matrix(var_name):
        members = [daily[f"{var_name}_member_{i}"] for i in range(51) if f"{var_name}_member_{i}" in daily]
        return np.array(members, dtype=float)

    rain_arr = get_ensemble_matrix("rain_sum")
    snow_arr = get_ensemble_matrix("snowfall_sum")
    cape_arr = get_ensemble_matrix("cape_max")

    # Calcoli Statistici (con fix per evitare IndexError)
    rain_sum = np.atleast_1d(np.nanmean(rain_arr, axis=0))
    snow_sum = np.nanmean(snow_arr, axis=0)
    cape_max = np.nanmean(cape_arr, axis=0)

    # PERCENTILE DI AFFIDABILITÀ: % di membri che superano la media calcolata
    prob_supera_media = np.nansum(rain_arr >= rain_sum[:, np.newaxis], axis=0) / 51.0 * 100.0
    
    # --- GRAFICA ---
    fig, axs = plt.subplots(2, 1, figsize=(13, 12), sharex=True, gridspec_kw={'height_ratios': [2, 1.2]})

    # Riquadro Pioggia + CAPE
    ax_rain = axs[0]
    ax_cape = ax_rain.twinx()
    ax_rain.bar(daily_times, rain_sum, color='#1f77b4', alpha=0.6, width=0.8, label='Pioggia Cumulata Media')
    
    # Inserimento % affidabilità sopra barre
    for i, txt in enumerate(prob_supera_media):
        if rain_sum[i] >= 1.0:
            ax_rain.text(daily_times[i], rain_sum[i] + (np.nanmax(rain_sum) * 0.05), 
                         f"{int(txt)}%", ha='center', va='bottom', fontsize=10, 
                         color='#d62728', fontweight='bold')

    ax_cape.plot(daily_times, cape_max, color='purple', marker='o', markersize=6, linewidth=2.2, label='CAPE Max Medio')
    ax_rain.set_ylabel('Pioggia (mm)', color='#1f77b4', fontweight='bold')
    ax_cape.set_ylabel('CAPE Max (J/kg)', color='purple', fontweight='bold')
    
    # Riquadro Neve
    ax_snow = axs[1]
    ax_snow.bar(daily_times, snow_sum, color='#00bfff', alpha=0.7, width=0.8, label='Neve Cumulata')
    ax_snow.set_ylabel('Neve (cm)', color='#00bfff', fontweight='bold')

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')

    # --- INVIO TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        caption = "🌩 <b>Analisi Precipitativa ECMWF (14gg)</b>\n• Numeri rossi: % membri sopra media (Affidabilità).\n"
        # [Logica aggiunta dettaglio giorni già presente nelle versioni precedenti]
        with open(FILENAME, "rb") as photo:
            requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", 
                          data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}, 
                          files={"photo": photo})
    print("Grafico generato e inviato.")

if __name__ == "__main__":
    main()
