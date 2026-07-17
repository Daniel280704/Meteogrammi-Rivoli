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
    print("Scaricamento dati AIFS (Ensemble Mean) in corso...")
    
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    var_list = [
        "temperature_2m", "temperature_2m_spread",
        "dew_point_2m",
        "temperature_925hPa", "temperature_925hPa_spread",
        "temperature_850hPa", "temperature_850hPa_spread",
        "temperature_700hPa", "temperature_700hPa_spread",
        "temperature_600hPa", "temperature_600hPa_spread",
        "temperature_500hPa", "temperature_500hPa_spread",
        "geopotential_height_925hPa", "geopotential_height_925hPa_spread",
        "geopotential_height_850hPa", "geopotential_height_850hPa_spread",
        "geopotential_height_700hPa", "geopotential_height_700hPa_spread",
        "geopotential_height_600hPa", "geopotential_height_600hPa_spread",
        "geopotential_height_500hPa", "geopotential_height_500hPa_spread"
    ]

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "ecmwf_aifs025_ensemble_mean",
        "timezone": "Europe/Rome",
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter/7.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
    except Exception as e:
        print(f"❌ Errore durante il download dei dati: {e}", file=sys.stderr)
        sys.exit(1)

    if not verifica_dati_nuovi(hourly):
        print("ℹ️ Nessun aggiornamento trovato per AIFS. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati. Generazione del grafico...")
    times = pd.to_datetime(hourly.get("time"))

    def get_stats(var_name):
        mean_data = hourly.get(var_name)
        if not mean_data: return None, None, None
        mean_arr = np.array([np.nan if v is None else v for v in mean_data], dtype=float)
        if f"{var_name}_spread" in hourly:
            spread_data = hourly.get(f"{var_name}_spread")
            spread_arr = np.array([np.nan if v is None else v for v in spread_data], dtype=float)
            return mean_arr, mean_arr - spread_arr, mean_arr + spread_arr
        else:
            return mean_arr, mean_arr, mean_arr

    fig, axs = plt.subplots(6, 1, figsize=(13, 26), sharex=True)

    levels_config = [
        {"lvl": "2m",     "color": "#d62728", "has_z": False, "has_dew": True}, 
        {"lvl": "925hPa", "color": "#ff7f0e", "has_z": True,  "has_dew": False},  
        {"lvl": "850hPa", "color": "#8c564b", "has_z": True,  "has_dew": False},  
        {"lvl": "700hPa", "color": "#e377c2", "has_z": True,  "has_dew": False},  
        {"lvl": "600hPa", "color": "#2ca02c", "has_z": True,  "has_dew": False},  
        {"lvl": "500hPa", "color": "#1f77b4", "has_z": True,  "has_dew": False}   
    ]

    for ax, config in zip(axs, levels_config):
        lvl, base_color = config["lvl"], config["color"]
        all_y_vals = []
        
        # Temp + Dew Point (2m)
        t_mean, t_min, t_max = get_stats(f"temperature_{lvl}")
        if t_mean is not None:
            ax.plot(times, t_mean, label=f'Temp {lvl}', color=base_color, linewidth=2.2)
            ax.fill_between(times, t_min, t_max, color=base_color, alpha=0.15)
            all_y_vals.extend([np.nanmin(t_min), np.nanmax(t_max)])
            
            if config.get("has_dew"):
                d_mean, _, _ = get_stats("dew_point_2m")
                ax.plot(times, d_mean, label='Dew Point 2m', color=base_color, linewidth=2.2, linestyle='--')
                all_y_vals.extend([np.nanmin(d_mean), np.nanmax(d_mean)])
            
            ax.set_ylim(np.nanmin(all_y_vals) - 2, np.nanmax(all_y_vals) + 2)
            
        ax.set_ylabel(f"Temp °C ({lvl})", color=base_color, fontweight='bold')
        ax.grid(True, linestyle='--', alpha=0.5)

        # Geopotenziale
        if config["has_z"]:
            ax2 = ax.twinx() 
            z_mean, z_min, z_max = get_stats(f"geopotential_height_{lvl}")
            ax2.plot(times, z_mean, label=f'Geop {lvl}', color=base_color, linewidth=2.2, linestyle='--')
            ax2.fill_between(times, z_min, z_max, color=base_color, alpha=0.08)
            ax2.set_ylabel(f"Altezza m ({lvl})", color=base_color, fontweight='bold')
            ax2.set_ylim(np.nanmin(z_min) - 20, np.nanmax(z_max) + 20)
            ax.legend(loc='upper right', ncol=2)
        else:
            ax.legend(loc='upper right', ncol=2 if config.get("has_dew") else 1)

    axs[-1].set_xlabel("Data (Fuso Orario Locale)   |   Analisi ECMWF AIFS (14gg)", fontsize=13, fontweight='bold', labelpad=15)
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
            "📈 <b>Meteogramma Termodinamico ECMWF (14 Giorni)</b>\n"
            "Temperature (linea continua) e Altezze Geopotenziali / Dew Point (linea tratteggiata).\n"
            "<i>Aree colorate: deviazione standard (spread) dell'ensemble.</i>\n\n"
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
