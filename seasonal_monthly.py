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

warnings.filterwarnings('ignore', category=RuntimeWarning)

LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_seasonal_monthly.txt"
FILENAME = "seasonal_monthly_anomalies.png"

def verifica_dati_nuovi(data_dict: dict) -> bool:
    sample = data_dict.get("temperature_max24h_2m_anomaly", [])
    stringa_dati = str(sample).encode('utf-8')
    hash_attuale = hashlib.md5(stringa_dati).hexdigest()
    
    if os.path.exists(FILE_HASH):
        with open(FILE_HASH, "r") as f:
            if f.read().strip() == hash_attuale:
                return False

    with open(FILE_HASH, "w") as f:
        f.write(hash_attuale)
    return True

def main():
    print("Scaricamento anomalie mensili (217 giorni) in corso...")
    
    URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "monthly": "temperature_max24h_2m_mean,temperature_max24h_2m_anomaly,temperature_min24h_2m_mean,temperature_min24h_2m_anomaly,precipitation_mean,precipitation_anomaly",
        "timezone": "Europe/Rome",
        "forecast_days": 217
    }
    headers = {"User-Agent": "MeteoBot-Seasonal/2.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        monthly = data.get("monthly", {})
    except Exception as e:
        print(f"❌ Errore API: {e}", file=sys.stderr)
        sys.exit(1)

    if not verifica_dati_nuovi(monthly):
        print("ℹ️ Nessun aggiornamento trovato. Elaborazione fermata.")
        sys.exit(0)
        
    times = pd.to_datetime(monthly.get("time"))
    
    tmax_anom = np.array(monthly.get("temperature_max24h_2m_anomaly"), dtype=float)
    tmin_anom = np.array(monthly.get("temperature_min24h_2m_anomaly"), dtype=float)
    prec_anom = np.array(monthly.get("precipitation_anomaly"), dtype=float)

    fig, axs = plt.subplots(3, 1, figsize=(12, 14), sharex=True)
    
    def plot_anomaly_bars(ax, times, anomalies, is_precip=False):
        if is_precip:
            colors = ['#2ca02c' if val >= 0 else '#8c564b' for val in anomalies]
            ylabel = "Anomalia Prec. (mm)"
        else:
            colors = ['#d62728' if val >= 0 else '#1f77b4' for val in anomalies]
            ylabel = "Anomalia Temp. (°C)"
            
        # Larghezza barre aumentata a 20 giorni perché i dati sono aggregati per mese
        ax.bar(times, anomalies, color=colors, width=20, alpha=0.8, edgecolor='black', linewidth=0.5)
        ax.axhline(0, color='black', linewidth=1.5, linestyle='--')
        ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
        ax.grid(True, linestyle=':', alpha=0.6)
        
        for i, val in enumerate(anomalies):
            if not np.isnan(val):
                offset = 0.5 if not is_precip else 10
                y_pos = val + offset if val >= 0 else val - offset
                va = 'bottom' if val >= 0 else 'top'
                ax.text(times[i], y_pos, f"{val:+.1f}", ha='center', va=va, fontsize=10, fontweight='bold', color=colors[i])
                
        v_max = np.nanmax(np.abs(anomalies)) if not np.isnan(anomalies).all() else 1
        pad = v_max * 0.3 if v_max != 0 else 1
        ax.set_ylim(-v_max - pad, v_max + pad)

    plot_anomaly_bars(axs[0], times, tmax_anom, is_precip=False)
    axs[0].set_title("Anomalia Mensile Temperatura MASSIMA", fontsize=12, fontweight='bold')

    plot_anomaly_bars(axs[1], times, tmin_anom, is_precip=False)
    axs[1].set_title("Anomalia Mensile Temperatura MINIMA", fontsize=12, fontweight='bold')

    plot_anomaly_bars(axs[2], times, prec_anom, is_precip=True)
    axs[2].set_title("Anomalia Mensile PRECIPITAZIONI", fontsize=12, fontweight='bold')

    axs[-1].set_xlabel("Mese di riferimento", fontsize=12, fontweight='bold', labelpad=10)
    axs[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%B %Y'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')

    # --- INVIO A TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        ora = datetime.now().strftime("%d/%m/%Y alle %H:%M")
        caption = (
            "🌍 <b>Anomalie Climatiche Mensili (Proiezione 6+ Mesi)</b>\n"
            "Scostamenti aggregati rispetto alla media storica.\n"
            "• <b>Temperature:</b> Rosso (sopra media) / Blu (sotto media).\n"
            "• <b>Precipitazioni:</b> Verde (surplus) / Marrone (deficit).\n\n"
            f"<i>Aggiornato il {ora}</i>"
        )
        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}, files={"photo": photo})
        except Exception as e:
            print(f"❌ Eccezione Telegram: {e}")

if __name__ == "__main__":
    main()