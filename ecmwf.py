import os
import sys
import hashlib
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Coordinate
LATITUDE = 45.069
LONGITUDE = 7.517

FILE_HASH = "ultimo_hash_ecmwf.txt"
FILENAME = "ecmwf_thermal_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica se i dati scaricati sono cambiati rispetto all'ultima esecuzione."""
    # Creiamo un hash basato sulla temperatura del membro 0 per rilevare se il run è nuovo
    stringa_dati = str(hourly_data.get("temperature_2m_member_0", [])).encode('utf-8')
    hash_attuale = hashlib.md5(stringa_dati).hexdigest()
    
    is_nuovo = True
    if os.path.exists(FILE_HASH):
        with open(FILE_HASH, "r") as f:
            hash_salvato = f.read().strip()
            # Se l'hash corrisponde a quello vecchio, i dati non sono cambiati
            if hash_attuale == hash_salvato:
                is_nuovo = False

    # Salviamo sempre il nuovo hash se i dati sono cambiati
    if is_nuovo:
        with open(FILE_HASH, "w") as f:
            f.write(hash_attuale)

    return is_nuovo

def main():
    print("Scaricamento dati ensemble ECMWF in corso...")
    VARIABLES = [
        "temperature_2m", "temperature_925hPa", "temperature_850hPa",
        "temperature_700hPa", "temperature_600hPa", "temperature_500hPa",
        "temperature_400hPa", "temperature_300hPa"
    ]

    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(VARIABLES),
        "models": "ecmwf_ifs025",
        "timezone": "Europe/Rome"
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter/1.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
    except Exception as e:
        print(f"❌ Errore durante il download dei dati: {e}", file=sys.stderr)
        sys.exit(1)

    # Verifica se i dati sono effettivamente nuovi
    is_nuovo = verifica_dati_nuovi(hourly)
    
    if not is_nuovo:
        print("ℹ️ Nessun aggiornamento trovato per ECMWF rispetto all'ultimo invio. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati per ECMWF. Generazione del grafico in corso...")

    times = pd.to_datetime(hourly.get("time"))

    def get_ensemble_stats(var_name):
        members_data = [hourly[f"{var_name}_member_{i}"] for i in range(51) if f"{var_name}_member_{i}" in hourly]
        if not members_data:
            return None, None, None
        arr = np.array(members_data)
        return np.mean(arr, axis=0), np.min(arr, axis=0), np.max(arr, axis=0)

    # --- CREAZIONE GRAFICO ---
    fig, axs = plt.subplots(4, 1, figsize=(12, 18), sharex=True)
    fig.suptitle("Analisi Ensemble ECMWF - Profilo Termico Verticale", fontsize=16, fontweight='bold', y=0.92)

    plot_groups = [
        ({"var": "temperature_2m", "label": "2 m", "color": "#d62728"},
         {"var": "temperature_925hPa", "label": "925 hPa", "color": "#ff7f0e"}),
        ({"var": "temperature_850hPa", "label": "850 hPa", "color": "#8c564b"},
         {"var": "temperature_700hPa", "label": "700 hPa", "color": "#e377c2"}),
        ({"var": "temperature_600hPa", "label": "600 hPa", "color": "#2ca02c"},
         {"var": "temperature_500hPa", "label": "500 hPa", "color": "#1f77b4"}),
        ({"var": "temperature_400hPa", "label": "400 hPa", "color": "#9467bd"},
         {"var": "temperature_300hPa", "label": "300 hPa", "color": "#17becf"})
    ]

    for ax, (line1, line2) in zip(axs, plot_groups):
        mean1, min1, max1 = get_ensemble_stats(line1["var"])
        if mean1 is not None:
            ax.plot(times, mean1, label=f'Media {line1["label"]}', color=line1["color"], linewidth=2)
            ax.fill_between(times, min1, max1, color=line1["color"], alpha=0.15, label=f'Spread {line1["label"]}')
            
        mean2, min2, max2 = get_ensemble_stats(line2["var"])
        if mean2 is not None:
            ax.plot(times, mean2, label=f'Media {line2["label"]}', color=line2["color"], linewidth=2)
            ax.fill_between(times, min2, max2, color=line2["color"], alpha=0.15, label=f'Spread {line2["label"]}')
            
        ax.set_ylabel("Temperatura (°C)", fontsize=11)
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.legend(loc='upper right', fontsize=9, ncol=2)

    axs[-1].set_xlabel("Data e Ora (Fuso Orario Locale)", fontsize=11)
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b %H:%M'))
    plt.xticks(rotation=45)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')
    print(f"Grafico salvato come {FILENAME}")

    # --- INVIO A TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        print("Invio grafico su Telegram...")
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        
        ora_esecuzione = datetime.now().strftime("%d/%m/%Y alle %H:%M")
        caption = (
            "📈 <b>Aggiornamento Profilo Termico Verticale ECMWF</b>\n"
            "Analisi ensemble (51 membri) da 2m a 300hPa.\n\n"
            f"<i>Aggiornamento del {ora_esecuzione}</i>"
        )
        
        with open(FILENAME, "rb") as photo:
            res = requests.post(
                url_telegram,
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": photo}
            )
            
            if res.status_code == 200:
                print("✅ Grafico inviato con successo su Telegram!")
            else:
                print(f"⚠️ Errore invio Telegram: {res.text}")
    else:
        print("Credenziali Telegram mancanti, skip invio.")

if __name__ == "__main__":
    main()