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

FILE_HASH = "ultimo_hash_ecmwf.txt"
FILENAME = "ecmwf_thermal_geopot_profile.png"

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
    print("Scaricamento dati ECMWF a 14 giorni (Temp + Geopotenziale + Dew Point) in corso...")
    
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    var_list = [
        "geopotential_height_925hPa", "geopotential_height_925hPa_spread",
        "geopotential_height_850hPa", "geopotential_height_850hPa_spread",
        "geopotential_height_700hPa", "geopotential_height_700hPa_spread",
        "geopotential_height_600hPa", "geopotential_height_600hPa_spread",
        "geopotential_height_500hPa", "geopotential_height_500hPa_spread",
        "temperature_2m", "temperature_2m_spread",
        "dew_point_2m", "dew_point_2m_spread",
        "temperature_925hPa", "temperature_925hPa_spread",
        "temperature_850hPa", "temperature_850hPa_spread",
        "temperature_700hPa", "temperature_700hPa_spread",
        "temperature_600hPa", "temperature_600hPa_spread",
        "temperature_500hPa", "temperature_500hPa_spread"
    ]

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "ecmwf_ifs025_ensemble_mean",
        "timezone": "Europe/Rome",
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter/6.3"}

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
        print("ℹ️ Nessun aggiornamento trovato per ECMWF. Elaborazione fermata.")
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

    # --- CONFIGURAZIONE GRAFICI ---
    fig, axs = plt.subplots(6, 1, figsize=(13, 26), sharex=True)

    levels_config = [
        {"lvl": "2m",     "color": "#d62728", "has_z": False, "has_dew": True}, 
        {"lvl": "925hPa", "color": "#ff7f0e", "has_z": True,  "has_dew": False},  
        {"lvl": "850hPa", "color": "#8c564b", "has_z": True,  "has_dew": False},  
        {"lvl": "700hPa", "color": "#e377c2", "has_z": True,  "has_dew": False},  
        {"lvl": "600hPa", "color": "#2ca02c", "has_z": True,  "has_dew": False},  
        {"lvl": "500hPa", "color": "#1f77b4", "has_z": True,  "has_dew": False}   
    ]

    plotted_something = False

    for ax, config in zip(axs, levels_config):
        lvl = config["lvl"]
        base_color = config["color"]
        
        # Liste per raccogliere i limiti di tutte le variabili su questo asse Y
        valid_y_mins = []
        valid_y_maxs = []
        
        # --- PLOT TEMPERATURA (Asse Y sinistro, Linea Continua) ---
        t_mean, t_min, t_max = get_stats(f"temperature_{lvl}")
        if t_mean is not None:
            l1 = ax.plot(times, t_mean, label=f'Temp {lvl}', color=base_color, linewidth=2.2, linestyle='-')
            ax.fill_between(times, t_min, t_max, color=base_color, alpha=0.15)
            plotted_something = True
            
            valid_y_mins.append(np.nanmin(t_min))
            valid_y_maxs.append(np.nanmax(t_max))
            
            # --- PLOT DEW POINT (Solo a 2m, stesso asse Y, Linea Tratteggiata) ---
            if config.get("has_dew"):
                d_mean, d_min, d_max = get_stats(f"dew_point_{lvl}")
                if d_mean is not None:
                    ax.plot(times, d_mean, label=f'Dew Point {lvl}', color=base_color, linewidth=2.2, linestyle='--')
                    ax.fill_between(times, d_min, d_max, color=base_color, alpha=0.08) 
                    
                    # Aggiungiamo i limiti del dew point alla lista per il calcolo dell'escursione termica totale
                    valid_y_mins.append(np.nanmin(d_min))
                    valid_y_maxs.append(np.nanmax(d_max))
            
            # Estraiamo i minimi e massimi assoluti combinati
            abs_y_min = min(valid_y_mins)
            abs_y_max = max(valid_y_maxs)
            y_range = abs_y_max - abs_y_min if (abs_y_max - abs_y_min) > 0 else 5.0
            
            # Adattamento scalabile: 
            # Se c'è l'altezza di geopotenziale (has_z), lasciamo il fondo del grafico vuoto (padding enorme: 1.3)
            # Se siamo a 2m (solo temperature), usiamo un padding di "respiro" del 15% simmetrico per far vedere bene i picchi
            if config["has_z"]:
                pad_bottom = y_range * 1.3
                pad_top = y_range * 0.15
            else:
                pad_bottom = y_range * 0.15
                pad_top = y_range * 0.15
                
            ax.set_ylim(abs_y_min - pad_bottom, abs_y_max + pad_top)
            
        ax.set_ylabel(f"Temperatura °C ({lvl})", fontsize=11, color=base_color)
        ax.tick_params(axis='y', labelcolor=base_color)
        ax.grid(True, linestyle='--', alpha=0.5)

        # --- PLOT GEOPOTENZIALE (Asse Y destro, in basso, Linea Tratteggiata) ---
        if config["has_z"]:
            ax2 = ax.twinx() 
            z_mean, z_min, z_max = get_stats(f"geopotential_height_{lvl}")
            
            if z_mean is not None:
                l2 = ax2.plot(times, z_mean, label=f'Geopotenziale {lvl}', color=base_color, linewidth=2.2, linestyle='--')
                ax2.fill_between(times, z_min, z_max, color=base_color, alpha=0.08)
                
                abs_z_min, abs_z_max = np.nanmin(z_min), np.nanmax(z_max)
                z_range = abs_z_max - abs_z_min if (abs_z_max - abs_z_min) > 0 else 50.0
                
                # Per il geopotenziale, spazio vuoto in alto per non sovrapporsi alle temperature
                ax2.set_ylim(abs_z_min - z_range * 0.1, abs_z_max + z_range * 1.8)
                
            ax2.set_ylabel(f"Altezza Geop. m ({lvl})", fontsize=11, color=base_color)
            ax2.tick_params(axis='y', labelcolor=base_color)
            
            lines_1, labels_1 = ax.get_legend_handles_labels()
            lines_2, labels_2 = ax2.get_legend_handles_labels()
            ax.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right', fontsize=9, ncol=2)
        else:
            ax.legend(loc='upper right', fontsize=9, ncol=2 if config.get("has_dew") else 1)

    if not plotted_something:
        print("❌ ERRORE CRITICO: Non ho potuto tracciare nessuna linea. Dati API non validi.")
        sys.exit(1)

    # Formattazione dell'asse X (14 Giorni) + TITOLO IN BASSO
    titolo_in_basso = "Analisi ECMWF (14 Giorni) - Profilo Termodinamico Verticale   |   Data e Ora (Fuso Orario Locale)"
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
        print("Invio grafico su Telegram...")
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        ora_esecuzione = datetime.now().strftime("%d/%m/%Y alle %H:%M")
        
        caption = (
            "📈 <b>Meteogramma Termodinamico ECMWF (14 Giorni)</b>\n"
            "Temperature (linea continua) e Altezze Geopotenziali / Dew Point (linea tratteggiata).\n"
            "<i>Aree colorate: spread dell'ensemble (IFS 0.25°).</i>\n\n"
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
