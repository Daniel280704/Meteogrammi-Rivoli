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

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_seasonal_weekly.txt"
FILENAME = "seasonal_weekly_anomalies.png"

def verifica_dati_nuovi(data_dict: dict) -> bool:
    sample = data_dict.get("temperature_max6h_2m_anomaly", [])
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
    print("Scaricamento anomalie settimanali (45 giorni) in corso...")
    
    URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "weekly": "temperature_max6h_2m_anomaly,temperature_max6h_2m_mean,temperature_min6h_2m_anomaly,temperature_min6h_2m_mean,precipitation_anomaly,precipitation_mean",
        "timezone": "Europe/Rome",
        "forecast_days": 45
    }
    headers = {"User-Agent": "MeteoBot-Seasonal/1.1"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        weekly = data.get("weekly", {})
    except Exception as e:
        print(f"❌ Errore API: {e}", file=sys.stderr)
        sys.exit(1)

    if not verifica_dati_nuovi(weekly):
        print("ℹ️ Nessun aggiornamento trovato. Elaborazione fermata.")
        sys.exit(0)
        
    times = pd.to_datetime(weekly.get("time"))
    
    # Estrazione Dati
    tmax_anom = np.array(weekly.get("temperature_max6h_2m_anomaly"), dtype=float)
    tmin_anom = np.array(weekly.get("temperature_min6h_2m_anomaly"), dtype=float)
    prec_anom = np.array(weekly.get("precipitation_anomaly"), dtype=float)

    # Impostazione Grafici
    fig, axs = plt.subplots(3, 1, figsize=(12, 14), sharex=True)
    
    def plot_anomaly_bars(ax, times, anomalies, is_precip=False):
        if is_precip:
            colors = ['#2ca02c' if val >= 0 else '#8c564b' for val in anomalies]
            ylabel = "Anomalia Prec. (mm)"
        else:
            colors = ['#d62728' if val >= 0 else '#1f77b4' for val in anomalies]
            ylabel = "Anomalia Temp. (°C)"
            
        # FIX ALLINEAMENTO E LARGHEZZA: 
        # width=7 assicura che copra l'intera settimana
        # align='edge' assicura che parta esattamente dal punto (il lunedì)
        ax.bar(times, anomalies, color=colors, width=7, align='edge', alpha=0.8, edgecolor='black', linewidth=0.5)
        ax.axhline(0, color='black', linewidth=1.5, linestyle='--') 
        ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
        ax.grid(True, linestyle=':', alpha=0.6)
        
        # FIX OFFSET TESTO: Calcolo dinamico in base al valore massimo, così non esce mai dal grafico
        v_max = np.nanmax(np.abs(anomalies)) if not np.isnan(anomalies).all() else 1
        if v_max == 0: v_max = 1
        
        for i, val in enumerate(anomalies):
            if not np.isnan(val):
                offset = v_max * 0.05 # L'offset è sempre il 5% del valore massimo presente
                y_pos = val + offset if val >= 0 else val - offset
                va = 'bottom' if val >= 0 else 'top'
                
                # Visto che la barra parte dal lunedì (edge), calcoliamo il centro per mettere il testo (lunedì + 3.5 giorni)
                center_x = times[i] + pd.Timedelta(days=3.5)
                
                ax.text(center_x, y_pos, f"{val:+.1f}", ha='center', va=va, fontsize=9, fontweight='bold', color=colors[i])
                
        pad = v_max * 0.25
        ax.set_ylim(-v_max - pad, v_max + pad)

    # 1. T-Max Anomaly
    plot_anomaly_bars(axs[0], times, tmax_anom, is_precip=False)
    axs[0].set_title("Anomalia Settimanale Temperatura MASSIMA", fontsize=12, fontweight='bold')

    # 2. T-Min Anomaly
    plot_anomaly_bars(axs[1], times, tmin_anom, is_precip=False)
    axs[1].set_title("Anomalia Settimanale Temperatura MINIMA", fontsize=12, fontweight='bold')

    # 3. Precipitation Anomaly
    plot_anomaly_bars(axs[2], times, prec_anom, is_precip=True)
    axs[2].set_title("Anomalia Settimanale PRECIPITAZIONI", fontsize=12, fontweight='bold')

    axs[-1].set_xlabel("Settimana di riferimento (da Lunedì a Lunedì)", fontsize=12, fontweight='bold', labelpad=10)
    
    # FIX GRIGLIA: Forziamo i tick verticali esattamente sui Lunedì
    axs[-1].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    
    # Forziamo i limiti visivi in modo che l'ultima barra da 7 giorni si veda tutta
    axs[-1].set_xlim(times[0], times[-1] + pd.Timedelta(days=7))
    
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
            "📊 <b>Anomalie Settimanali (Proiezione 45 Giorni)</b>\n"
            "Scostamenti previsti rispetto alla media climatologica.\n"
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
