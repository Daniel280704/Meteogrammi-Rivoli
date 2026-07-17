import os
import sys
import hashlib
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Coordinate esatte estratte dalla chiamata API
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_ecmwf.txt"
FILENAME = "ecmwf_thermal_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica se i dati scaricati sono cambiati rispetto all'ultima esecuzione."""
    # La chiave base ora è direttamente 'temperature_2m' (che rappresenta la media)
    stringa_dati = str(hourly_data.get("temperature_2m", [])).encode('utf-8')
    hash_attuale = hashlib.md5(stringa_dati).hexdigest()
    
    is_nuovo = True
    if os.path.exists(FILE_HASH):
        with open(FILE_HASH, "r") as f:
            if f.read().strip() == hash_attuale:
                is_nuovo = False

    # Aggiorna sempre l'hash se ci sono dati freschi
    if is_nuovo:
        with open(FILE_HASH, "w") as f:
            f.write(hash_attuale)

    return is_nuovo

def main():
    print("Scaricamento dati ECMWF (Ensemble Mean & Spread) in corso...")
    
    # Elenco delle quote per automatizzare la costruzione dei parametri
    LEVELS = ["2m", "925hPa", "850hPa", "700hPa", "600hPa", "500hPa", "400hPa", "300hPa"]
    
    VARIABLES = []
    for lvl in LEVELS:
        VARIABLES.append(f"temperature_{lvl}")
        VARIABLES.append(f"temperature_{lvl}_spread")

    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(VARIABLES),
        "models": "ecmwf_ifs025_ensemble_mean",
        "timezone": "Europe/Rome"
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter/3.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
    except Exception as e:
        print(f"❌ Errore durante il download dei dati: {e}", file=sys.stderr)
        sys.exit(1)

    is_nuovo = verifica_dati_nuovi(hourly)
    
    if not is_nuovo:
        print("ℹ️ Nessun aggiornamento trovato per ECMWF rispetto all'ultimo invio. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati per ECMWF. Generazione del grafico in corso...")

    times = pd.to_datetime(hourly.get("time"))

    def get_stats(var_name):
        """Recupera la media e calcola i limiti dello spread per l'area ombreggiata."""
        mean_data = hourly.get(var_name)
        spread_data = hourly.get(f"{var_name}_spread")
        
        if not mean_data or not spread_data:
            print(f"⚠️ Dati mancanti nell'API per la variabile: {var_name}")
            return None, None, None
            
        # Convertiamo i None in NaN (per sicurezza) e creiamo gli array numpy
        mean_arr = np.array([np.nan if v is None else v for v in mean_data], dtype=float)
        spread_arr = np.array([np.nan if v is None else v for v in spread_data], dtype=float)
        
        # Lo spread calcolato da Open-Meteo è la deviazione standard.
        # Definiamo l'area di incertezza come Media ± Spread
        min_arr = mean_arr - spread_arr
        max_arr = mean_arr + spread_arr
        
        return mean_arr, min_arr, max_arr

    # --- CREAZIONE DEL GRAFICO ---
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

    plotted_something = False

    for ax, (line1, line2) in zip(axs, plot_groups):
        mean1, min1, max1 = get_stats(line1["var"])
        if mean1 is not None:
            ax.plot(times, mean1, label=f'Media {line1["label"]}', color=line1["color"], linewidth=2)
            ax.fill_between(times, min1, max1, color=line1["color"], alpha=0.15, label=f'Spread {line1["label"]}')
            plotted_something = True
            
        mean2, min2, max2 = get_stats(line2["var"])
        if mean2 is not None:
            ax.plot(times, mean2, label=f'Media {line2["label"]}', color=line2["color"], linewidth=2)
            ax.fill_between(times, min2, max2, color=line2["color"], alpha=0.15, label=f'Spread {line2["label"]}')
            plotted_something = True
            
        ax.set_ylabel("Temperatura (°C)", fontsize=11)
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.legend(loc='upper right', fontsize=9, ncol=2)

    if not plotted_something:
        print("❌ ERRORE CRITICO: Non ho potuto tracciare nessuna linea. Dati API non validi.")
        sys.exit(1)

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
            "Analisi ensemble da 2m a 300hPa.\n"
            "<i>Le aree colorate indicano lo spread (deviazione standard) attorno alla media.</i>\n\n"
            f"<i>Aggiornato il {ora_esecuzione}</i>"
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
