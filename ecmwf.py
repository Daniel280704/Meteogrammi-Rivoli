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
    stringa_dati = str(hourly_data.get("temperature_2m", [])).encode('utf-8')
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
    print("Scaricamento dati ECMWF a 14 giorni (Ensemble Mean & Spread) in corso...")
    
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
        "timezone": "Europe/Rome",
        "forecast_days": 14  # Orizzonte esteso a 14 giorni
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter/4.0"}

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
        mean_data = hourly.get(var_name)
        spread_data = hourly.get(f"{var_name}_spread")
        
        if not mean_data or not spread_data:
            return None, None, None
            
        mean_arr = np.array([np.nan if v is None else v for v in mean_data], dtype=float)
        spread_arr = np.array([np.nan if v is None else v for v in spread_data], dtype=float)
        
        min_arr = mean_arr - spread_arr
        max_arr = mean_arr + spread_arr
        
        return mean_arr, min_arr, max_arr

    # --- CREAZIONE DEL GRAFICO ---
    # Aumentato il numero di subplot a 5 e l'altezza complessiva dell'immagine (figsize) a 22
    fig, axs = plt.subplots(5, 1, figsize=(12, 22), sharex=True)
    fig.suptitle("Analisi Ensemble ECMWF (14 Giorni) - Profilo Termico Verticale", fontsize=16, fontweight='bold', y=0.91)

    # Struttura modulare: ogni lista interna rappresenta i dati da stampare su un singolo subplot
    plot_groups = [
        # Plot 1: Solo 2 metri
        [{"var": "temperature_2m", "label": "2 m", "color": "#d62728"}],
        # Plot 2: Solo 925 hPa
        [{"var": "temperature_925hPa", "label": "925 hPa", "color": "#ff7f0e"}],
        # Plot 3: 850 hPa e 700 hPa
        [{"var": "temperature_850hPa", "label": "850 hPa", "color": "#8c564b"},
         {"var": "temperature_700hPa", "label": "700 hPa", "color": "#e377c2"}],
        # Plot 4: 600 hPa e 500 hPa
        [{"var": "temperature_600hPa", "label": "600 hPa", "color": "#2ca02c"},
         {"var": "temperature_500hPa", "label": "500 hPa", "color": "#1f77b4"}],
        # Plot 5: 400 hPa e 300 hPa
        [{"var": "temperature_400hPa", "label": "400 hPa", "color": "#9467bd"},
         {"var": "temperature_300hPa", "label": "300 hPa", "color": "#17becf"}]
    ]

    plotted_something = False

    for ax, group in zip(axs, plot_groups):
        for line in group:
            mean_val, min_val, max_val = get_stats(line["var"])
            if mean_val is not None:
                ax.plot(times, mean_val, label=f'Media {line["label"]}', color=line["color"], linewidth=2)
                ax.fill_between(times, min_val, max_val, color=line["color"], alpha=0.15, label=f'Spread {line["label"]}')
                plotted_something = True
                
        ax.set_ylabel("Temperatura (°C)", fontsize=11)
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.legend(loc='upper right', fontsize=9, ncol=2)

    if not plotted_something:
        print("❌ ERRORE CRITICO: Non ho potuto tracciare nessuna linea. Dati API non validi.")
        sys.exit(1)

    # Formattazione dell'asse X ottimizzata per 14 giorni
    axs[-1].set_xlabel("Data (Fuso Orario Locale)", fontsize=11)
    
    # Imposta una tacca principale ogni giorno a mezzanotte
    axs[-1].xaxis.set_major_locator(mdates.DayLocator())
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    
    # Imposta tacche secondarie ogni 12 ore (mezzogiorno) per guidare l'occhio senza sovraffollare
    axs[-1].xaxis.set_minor_locator(mdates.HourLocator(byhour=[12]))
    axs[-1].grid(which="minor", axis="x", alpha=0.3, linestyle=':')

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
            "📈 <b>Aggiornamento Profilo Termico Verticale ECMWF (14 Giorni)</b>\n"
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
