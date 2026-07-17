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

# Disabilitiamo i warning per i calcoli su array temporaneamente vuoti
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_ecmwf_spaghetti.txt"
FILENAME = "ecmwf_spaghetti_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica l'hash usando il membro 1 come campione."""
    sample = hourly_data.get("temperature_850hPa_member01", [])
    if not sample and hourly_data:
        sample = list(hourly_data.values())[0]
        
    stringa_dati = str(sample).encode('utf-8')
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
    print("Scaricamento dati ECMWF (51 membri Ensemble) a 14 giorni in corso...")
    
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    # Le variabili base che vogliamo tracciare
    base_vars = [
        "temperature_850hPa",
        "temperature_500hPa",
        "geopotential_height_850hPa",
        "geopotential_height_500hPa",
        "precipitation"
    ]

    # --- FIX: Generazione automatica dei 51 membri per ogni variabile ---
    hourly_vars = []
    for var in base_vars:
        for i in range(1, 52): # Da member01 a member51
            hourly_vars.append(f"{var}_member{i:02d}")

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(hourly_vars), # Unisce le ~255 variabili in una singola stringa
        "models": "ecmwf_ifs025_ensemble",
        "timezone": "Europe/Rome",
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-Spaghetti/2.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
    except Exception as e:
        print(f"❌ Errore durante il download dei dati: {e}", file=sys.stderr)
        sys.exit(1)

    if not verifica_dati_nuovi(hourly):
        print("ℹ️ Nessun aggiornamento trovato per ECMWF Spaghetti. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati per ECMWF Ensemble. Generazione del grafico in corso...")
    times = pd.to_datetime(hourly.get("time"))

    # Funzione per estrarre tutti i membri in una singola matrice
    def extract_members(var_name):
        member_keys = [k for k in hourly.keys() if k.startswith(f"{var_name}_member")]
        if not member_keys:
            return None
        member_keys.sort()
        members_data = [hourly[k] for k in member_keys]
        return np.array(members_data, dtype=float)

    # Estrazione matrici
    t850_members = extract_members("temperature_850hPa")
    z850_members = extract_members("geopotential_height_850hPa")
    t500_members = extract_members("temperature_500hPa")
    z500_members = extract_members("geopotential_height_500hPa")
    precip_members = extract_members("precipitation")

    # Creazione dei 3 Subplot
    fig, axs = plt.subplots(3, 1, figsize=(14, 18), sharex=True)

    # ====================================================
    # 1. SUBPLOT 850 hPa (Temperatura & Geopotenziale)
    # ====================================================
    ax1 = axs[0]
    ax1_z = ax1.twinx()
    color_850 = "#d62728" 

    if t850_members is not None:
        for i in range(t850_members.shape[0]):
            ax1.plot(times, t850_members[i], color=color_850, alpha=0.15, linewidth=0.8, linestyle='-')
        t850_mean = np.nanmean(t850_members, axis=0)
        ax1.plot(times, t850_mean, color=color_850, linewidth=2.8, linestyle='-', label='Media Temp 850 hPa (°C)')

    if z850_members is not None:
        for i in range(z850_members.shape[0]):
            ax1_z.plot(times, z850_members[i], color=color_850, alpha=0.12, linewidth=0.8, linestyle='--')
        z850_mean = np.nanmean(z850_members, axis=0)
        ax1_z.plot(times, z850_mean, color=color_850, linewidth=2.8, linestyle='--', label='Media Geop 850 hPa (m)')

    ax1.set_ylabel("Temperatura 850 hPa (°C)", fontsize=11, color=color_850, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor=color_850)
    ax1.grid(True, linestyle='--', alpha=0.5)

    ax1_z.set_ylabel("Altezza Geopotenziale 850 hPa (m)", fontsize=11, color=color_850, fontweight='bold')
    ax1_z.tick_params(axis='y', labelcolor=color_850)

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_1_z, labels_1_z = ax1_z.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_1_z, labels_1 + labels_1_z, loc='upper left', fontsize=10)
    ax1.set_title("Profilo 850 hPa - Tutti i 51 Membri Ensemble ECMWF", fontsize=13, fontweight='bold')

    # ====================================================
    # 2. SUBPLOT 500 hPa (Temperatura & Geopotenziale)
    # ====================================================
    ax2 = axs[1]
    ax2_z = ax2.twinx()
    color_500 = "#1f77b4" 

    if t500_members is not None:
        for i in range(t500_members.shape[0]):
            ax2.plot(times, t500_members[i], color=color_500, alpha=0.15, linewidth=0.8, linestyle='-')
        t500_mean = np.nanmean(t500_members, axis=0)
        ax2.plot(times, t500_mean, color=color_500, linewidth=2.8, linestyle='-', label='Media Temp 500 hPa (°C)')

    if z500_members is not None:
        for i in range(z500_members.shape[0]):
            ax2_z.plot(times, z500_members[i], color=color_500, alpha=0.12, linewidth=0.8, linestyle='--')
        z500_mean = np.nanmean(z500_members, axis=0)
        ax2_z.plot(times, z500_mean, color=color_500, linewidth=2.8, linestyle='--', label='Media Geop 500 hPa (m)')

    ax2.set_ylabel("Temperatura 500 hPa (°C)", fontsize=11, color=color_500, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor=color_500)
    ax2.grid(True, linestyle='--', alpha=0.5)

    ax2_z.set_ylabel("Altezza Geopotenziale 500 hPa (m)", fontsize=11, color=color_500, fontweight='bold')
    ax2_z.tick_params(axis='y', labelcolor=color_500)

    lines_2, labels_2 = ax2.get_legend_handles_labels()
    lines_2_z, labels_2_z = ax2_z.get_legend_handles_labels()
    ax2.legend(lines_2 + lines_2_z, labels_2 + labels_2_z, loc='upper left', fontsize=10)
    ax2.set_title("Profilo 500 hPa - Tutti i 51 Membri Ensemble ECMWF", fontsize=13, fontweight='bold')

    # ====================================================
    # 3. SUBPLOT PRECIPITAZIONI
    # ====================================================
    ax3 = axs[2]
    color_precip = "#2ca02c" 

    if precip_members is not None:
        for i in range(precip_members.shape[0]):
            ax3.plot(times, precip_members[i], color=color_precip, alpha=0.2, linewidth=0.8, linestyle='-')
        precip_mean = np.nanmean(precip_members, axis=0)
        ax3.plot(times, precip_mean, color="#0a5c0a", linewidth=2.5, linestyle='-', label='Media Precipitazioni Orarie (mm/h)')

    ax3.set_ylabel("Precipitazioni (mm/h)", fontsize=11, color=color_precip, fontweight='bold')
    ax3.tick_params(axis='y', labelcolor=color_precip)
    ax3.set_ylim(bottom=0)
    ax3.grid(True, linestyle='--', alpha=0.5)
    ax3.legend(loc='upper left', fontsize=10)
    ax3.set_title("Precipitazioni Orarie - Tutti i 51 Membri Ensemble ECMWF", fontsize=13, fontweight='bold')

    # Formattazione Asse X
    titolo_in_basso = "Meteogramma Spaghetti ECMWF Ensemble IFS 0.25° (14 Giorni)   |   Data e Ora (Fuso Orario Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=12, fontweight='bold', labelpad=15)

    axs[-1].xaxis.set_major_locator(mdates.DayLocator())
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    axs[-1].xaxis.set_minor_locator(mdates.HourLocator(byhour=[12]))
    axs[-1].grid(which="minor", axis="x", alpha=0.3, linestyle=':')

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
            "🍝 <b>Meteogramma Spaghetti ECMWF IFS (51 Membri - 14 Giorni)</b>\n"
            "• <b>850 hPa & 500 hPa:</b> Temp (continua) e Geopotenziale (tratteggiata).\n"
            "• <b>Tratti sottili:</b> tutti i 51 scenari dell'Ensemble.\n"
            "• <b>Linea spessa:</b> Media dell'Ensemble (ENS Mean).\n\n"
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
        print("ℹ️ Credenziali Telegram mancanti, skip invio.")

if __name__ == "__main__":
    main()
