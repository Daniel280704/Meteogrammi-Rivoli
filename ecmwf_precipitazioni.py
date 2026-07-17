import os
import sys
import hashlib
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_ecmwf_precip_cape.txt"
FILENAME = "ecmwf_precip_cape_profile.png"

def verifica_dati_nuovi(daily_data: dict) -> bool:
    """Verifica l'hash basandosi sulle precipitazioni giornaliere."""
    stringa_dati = str(daily_data.get("rain_sum", [])).encode('utf-8')
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
    print("Scaricamento dati ECMWF a 14 giorni (Precipitazioni + CAPE Max) in corso...")
    
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": "rain_sum,snowfall_sum,cape_max",
        "models": "ecmwf_ifs025_ensemble_mean",
        "timezone": "Europe/Rome",
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter-Precip/3.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily", {})
    except Exception as e:
        print(f"❌ Errore durante il download dei dati: {e}", file=sys.stderr)
        sys.exit(1)

    is_nuovo = verifica_dati_nuovi(daily)
    if not is_nuovo:
        print("ℹ️ Nessun aggiornamento trovato per ECMWF. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati per ECMWF. Generazione del grafico in corso...")
    
    # Estrazione Asse Temporale
    # Aggiungiamo 12 ore per centrare il marker e la barra perfettamente a metà della giornata
    daily_times = pd.to_datetime(daily.get("time")) + pd.Timedelta(hours=12)

    # Estrazione Dati Giornalieri
    rain_sum = np.array([np.nan if v is None else v for v in daily.get("rain_sum", [])], dtype=float)
    snow_sum = np.array([np.nan if v is None else v for v in daily.get("snowfall_sum", [])], dtype=float)
    cape_max = np.array([np.nan if v is None else v for v in daily.get("cape_max", [])], dtype=float)

    # --- CONFIGURAZIONE GRAFICI ---
    # Due riquadri: 1 per Pioggia+CAPE, 1 per la Neve. 
    fig, axs = plt.subplots(2, 1, figsize=(13, 12), sharex=True, gridspec_kw={'height_ratios': [2, 1.2]})

    # ==========================================
    # 1. GRAFICO PIOGGIA (Barre) + CAPE MAX (Linea e Marker)
    # ==========================================
    ax_rain = axs[0]
    ax_cape = ax_rain.twinx()

    # Disegniamo la pioggia come istogramma
    ax_rain.bar(daily_times, rain_sum, color='#1f77b4', alpha=0.6, width=0.8, label='Pioggia Cumulata Giornaliera')
    
    # Calcolo tetto massimo asse Pioggia
    rain_max = np.nanmax(rain_sum) if not np.isnan(rain_sum).all() else 0
    ax_rain.set_ylim(bottom=0, top=max(rain_max * 1.3, 2.0))
    ax_rain.set_ylabel('Pioggia Giornaliera (mm)', fontsize=12, color='#1f77b4', fontweight='bold')
    ax_rain.tick_params(axis='y', labelcolor='#1f77b4')
    ax_rain.grid(True, linestyle='--', alpha=0.4)

    # Disegniamo il CAPE Max come linea continua con marker
    ax_cape.plot(daily_times, cape_max, color='purple', marker='o', markersize=6, linewidth=2.2, label='CAPE Max Medio')

    # Calcolo tetto massimo asse CAPE
    c_max = np.nanmax(cape_max) if not np.isnan(cape_max).all() else 0
    ax_cape.set_ylim(bottom=0, top=max(c_max * 1.3, 50.0))
    ax_cape.set_ylabel('CAPE Max (J/kg)', fontsize=12, color='purple', fontweight='bold')
    ax_cape.tick_params(axis='y', labelcolor='purple')

    # Unione Legende per il primo riquadro
    lines_r, labels_r = ax_rain.get_legend_handles_labels()
    lines_c, labels_c = ax_cape.get_legend_handles_labels()
    ax_rain.legend(lines_r + lines_c, labels_r + labels_c, loc='upper left', fontsize=10)


    # ==========================================
    # 2. GRAFICO NEVE (Barre)
    # ==========================================
    ax_snow = axs[1]
    
    ax_snow.bar(daily_times, snow_sum, color='#00bfff', alpha=0.7, width=0.8, label='Nevicata Cumulata Giornaliera')
    
    # Calcolo tetto massimo asse Neve con logica anti-errore per NaN
    s_max = np.nanmax(snow_sum) if not np.isnan(snow_sum).all() else 0
    ax_snow.set_ylim(bottom=0, top=max(s_max * 1.3, 0.5))
    
    ax_snow.set_ylabel('Neve Giornaliera (cm)', fontsize=12, color='#00bfff', fontweight='bold')
    ax_snow.tick_params(axis='y', labelcolor='#00bfff')
    ax_snow.grid(True, linestyle='--', alpha=0.4)
    ax_snow.legend(loc='upper left', fontsize=10)

    # --- FORMATTAZIONE ASSE X E TITOLO IN BASSO ---
    titolo_in_basso = "Analisi Precipitazioni & Setup Convettivo ECMWF (14 Giorni)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=13, fontweight='bold', labelpad=15)
    
    axs[-1].xaxis.set_major_locator(mdates.DayLocator())
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    axs[-1].grid(which="major", axis="x", alpha=0.3, linestyle=':')

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')
    print(f"Grafico salvato come {FILENAME}")

    # --- INVIO A TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        print("Invio grafico su Telegram in corso...")
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        ora_esecuzione = datetime.now().strftime("%d/%m/%Y alle %H:%M")
        
        caption = (
            "🌩 <b>Analisi Precipitativa & Convettiva ECMWF (14 Giorni)</b>\n"
            "• <b>Istogrammi:</b> Accumuli pluviometrici e nevosi totali giornalieri.\n"
            "• <b>Linea Viola:</b> CAPE Max Medio previsto nella giornata.\n\n"
            f"<i>Aggiornato il {ora_esecuzione}</i>"
        )
        
        try:
            with open(FILENAME, "rb") as photo:
                res = requests.post(
                    url_telegram,
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": photo}
                )
                
                if res.status_code == 200:
                    print("✅ Grafico inviato con successo su Telegram!")
                else:
                    print(f"⚠️ Errore API Telegram ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"❌ Eccezione durante l'invio a Telegram: {e}")
    else:
        print("ℹ️ Credenziali Telegram (Token o Chat ID) mancanti, skip invio.")

if __name__ == "__main__":
    main()
