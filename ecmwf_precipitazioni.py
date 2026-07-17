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

# File hash e nome immagine dedicati per non sovrascrivere lo script termico
FILE_HASH = "ultimo_hash_ecmwf_precip.txt"
FILENAME = "ecmwf_precip_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica se i dati scaricati sono cambiati rispetto all'ultima esecuzione."""
    stringa_dati = str(hourly_data.get("rain", [])).encode('utf-8')
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
    print("Scaricamento dati ECMWF a 14 giorni (Precipitazioni) in corso...")
    
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    var_list = [
        "rain", "rain_spread",
        "snowfall", "snowfall_spread",
        "snow_depth", "snow_depth_spread"
    ]

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "ecmwf_ifs025_ensemble_mean",
        "timezone": "Europe/Rome",
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter-Precip/1.0"}

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
        print("ℹ️ Nessun aggiornamento trovato per le precipitazioni ECMWF. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati per ECMWF (Precipitazioni). Generazione del grafico in corso...")
    times = pd.to_datetime(hourly.get("time"))

    def get_stats(var_name):
        mean_data = hourly.get(var_name)
        if not mean_data:
            return None, None, None
            
        mean_arr = np.array([np.nan if v is None else v for v in mean_data], dtype=float)
        
        if f"{var_name}_spread" in hourly:
            spread_data = hourly.get(f"{var_name}_spread")
            spread_arr = np.array([np.nan if v is None else v for v in spread_data], dtype=float)
            
            # REGOLE FISICHE: Le precipitazioni non possono essere inferiori a 0.
            # Clip taglia i valori negativi e li fissa a 0.
            min_arr = np.clip(mean_arr - spread_arr, 0, None)
            max_arr = mean_arr + spread_arr
            return mean_arr, min_arr, max_arr
        else:
            return mean_arr, mean_arr, mean_arr

    # --- CONFIGURAZIONE GRAFICI ---
    # 3 subplot (Pioggia, Nevicata, Manto Nevoso). Altezza 14 pollici.
    fig, axs = plt.subplots(3, 1, figsize=(13, 14), sharex=True)

    levels_config = [
        {"var": "rain",       "label": "Pioggia (mm)",         "color": "#1f77b4", "ylim_min_ceil": 1.0},
        {"var": "snowfall",   "label": "Nevicata (cm/h)",      "color": "#00bfff", "ylim_min_ceil": 0.5},
        {"var": "snow_depth", "label": "Manto Nevoso (m)",     "color": "#708090", "ylim_min_ceil": 0.1}
    ]

    plotted_something = False

    for ax, config in zip(axs, levels_config):
        var_name = config["var"]
        base_color = config["color"]
        label_text = config["label"]
        
        mean_val, min_val, max_val = get_stats(var_name)
        
        if mean_val is not None:
            # Tracciamo la linea e riempiamo lo spread
            ax.plot(times, mean_val, label=f'Media {label_text}', color=base_color, linewidth=2.2, linestyle='-')
            ax.fill_between(times, min_val, max_val, color=base_color, alpha=0.25)
            plotted_something = True
            
            # Troviamo il picco massimo assoluto
            abs_max = np.nanmax(max_val)
            
            # Se la previsione è 0 assoluto per 14 giorni, usiamo un tetto minimo di sicurezza
            # altrimenti l'asse si schiaccia tra 0 e 0 dando errore visivo.
            y_top = max(abs_max * 1.2, config["ylim_min_ceil"])
            
            ax.set_ylim(bottom=0, top=y_top)
            
        ax.set_ylabel(label_text, fontsize=11, color=base_color, fontweight='bold')
        ax.tick_params(axis='y', labelcolor=base_color)
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.legend(loc='upper right', fontsize=10)

    if not plotted_something:
        print("❌ ERRORE CRITICO: Non ho potuto tracciare nessuna linea. Dati API non validi.")
        sys.exit(1)

    # --- FORMATTAZIONE ASSE X E TITOLO IN BASSO ---
    titolo_in_basso = "Analisi Precipitazioni ECMWF (14 Giorni)   |   Data e Ora (Fuso Orario Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=13, fontweight='bold', labelpad=15)
    
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
            "🌧 <b>Meteogramma Precipitazioni ECMWF (14 Giorni)</b>\n"
            "Previsione precipitativa: Pioggia, Neve oraria e Accumulo al suolo.\n"
            "<i>Le aree colorate indicano l'incertezza (spread) dell'ensemble.</i>\n\n"
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