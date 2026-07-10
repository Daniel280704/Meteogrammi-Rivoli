#!/usr/bin/env python3
"""
Bot Agronomico per Ortive Estive
Modelli: ICON-Seamless (Fitosaniario/Termico/ET0) + ECMWF (Idrico/Suolo)
Versione: Anti-Crash (Gestione dei dati None)
"""

import os
import requests
from datetime import datetime
import sys

# Coordinate per Rivoli
LAT = 45.0716
LON = 7.5157

def fetch_data(url, params):
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"❌ Errore API: {e}")
        sys.exit(1)

def invia_messaggio_telegram(testo):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Credenziali Telegram mancanti. Stampa a video:")
        print(testo)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": testo,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload)
        print("✅ Bollettino agronomico inviato su Telegram!")
    except Exception as e:
        print(f"❌ Errore invio Telegram: {e}")

def main():
    print("🚀 Raccolta dati da ICON-Seamless e ECMWF...")
    
    # Dati per malattie, insetti ed Evapotraspirazione (ICON)
    icon_params = {
        "latitude": LAT, "longitude": LON,
        "models": "icon_seamless",
        "hourly": "temperature_2m,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration",
        "timezone": "Europe/Rome",
        "forecast_days": 3
    }
    icon_data = fetch_data("https://api.open-meteo.com/v1/forecast", icon_params)
    
    # Dati per umidità profonda del suolo (ECMWF)
    ecmwf_params = {
        "latitude": LAT, "longitude": LON,
        "models": "ecmwf_ifs04",
        "hourly": "soil_moisture_7_to_28cm",
        "timezone": "Europe/Rome",
        "forecast_days": 3
    }
    ecmwf_data = fetch_data("https://api.open-meteo.com/v1/forecast", ecmwf_params)

    # --- 1. MODULO FITOSANITARIO (FUNGHI) ---
    ore_rischio = 0
    temperature = icon_data["hourly"]["temperature_2m"][:48]
    umidita = icon_data["hourly"]["relative_humidity_2m"][:48]
    
    for t, rh in zip(temperature, umidita):
        if t is not None and rh is not None:
            if rh >= 88 and 15 <= t <= 25:
                ore_rischio += 1
            
    if ore_rischio > 8:
        stato_funghi = f"🔴 <b>ALTO ({ore_rischio}h di bagnatura fogliare)</b>\n<i>Attenzione per Cuori di bue e Datterini (Peronospora) e Zucchine (Oidio). Valutare trattamenti preventivi con rame/zolfo.</i>"
    elif ore_rischio > 3:
        stato_funghi = f"🟡 <b>MEDIO ({ore_rischio}h di bagnatura fogliare)</b>\n<i>Arieggiare la vegetazione dei pomodori sfemminellando la parte bassa.</i>"
    else:
        stato_funghi = f"🟢 <b>BASSO ({ore_rischio}h di bagnatura fogliare)</b>\n<i>Condizioni asciutte, basso rischio fungino.</i>"

    # --- 2. MODULO IRRIGAZIONE ---
    # Estrazione con ICON per ET0, ECMWF per suolo
    et_oggi_raw = icon_data["daily"]["et0_fao_evapotranspiration"][0]
    et_domani_raw = icon_data["daily"]["et0_fao_evapotranspiration"][1]
    umidita_raw = ecmwf_data["hourly"]["soil_moisture_7_to_28cm"][12]
    
    et_oggi = et_oggi_raw if et_oggi_raw is not None else 0.0
    et_domani = et_domani_raw if et_domani_raw is not None else 0.0
    umidita_suolo_radici = umidita_raw if umidita_raw is not None else 0.0
    
    consiglio_idrico = ""
    if et_oggi > 5.0:
        consiglio_idrico = "L'evaporazione è molto alta. Zucchine e melanzane richiederanno un forte apporto idrico. Per i pomodori (specie i cuori di bue, soggetti a marciume apicale), assicurare bagnature profonde e regolari, ma evitare ristagni."
    elif et_oggi > 3.0:
        consiglio_idrico = "Evaporazione nella norma estiva. Mantenere irrigazione regolare senza eccessi per evitare spaccature sui pomodorini (ciliegini/datterini)."
    else:
        consiglio_idrico = "Evaporazione bassa. Sospendere irrigazione se il terreno risulta già umido al tatto a 10cm di profondità."

    # --- 3. MODULO INSETTI (Gradi Giorno - GDD) ---
    t_max_raw = icon_data["daily"]["temperature_2m_max"][0]
    t_min_raw = icon_data["daily"]["temperature_2m_min"][0]
    
    t_max = t_max_raw if t_max_raw is not None else 25.0
    t_min = t_min_raw if t_min_raw is not None else 15.0
    
    # Calcolo semplificato GDD base 10 (Popillia / Afidi)
    gdd_oggi = max(0, ((t_max + t_min) / 2) - 10)
    
    if gdd_oggi > 14:
        stato_insetti = f"🔴 <b>ELEVATA ({gdd_oggi:.1f} GDD oggi)</b>\n<i>Temperature ottimali per picco di attività e alimentazione di Popillia japonica e afidi.</i>"
    else:
        stato_insetti = f"🟢 <b>MODERATA ({gdd_oggi:.1f} GDD oggi)</b>\n<i>Attività degli insetti nella norma.</i>"

    # --- COSTRUZIONE BOLLETTINO ---
    data_oggi = datetime.now().strftime("%d/%m/%Y")
    
    messaggio = (
        f"🌱 <b>BOLLETTINO AGRONOMICO RIVOLI</b>\n"
        f"📅 <i>{data_oggi}</i>\n\n"
        
        f"💧 <b>IRRIGAZIONE E SUOLO (0-30cm)</b>\n"
        f"• Evapotraspirazione oggi: <b>{et_oggi} mm</b>\n"
        f"• Evapotraspirazione domani: <b>{et_domani} mm</b>\n"
        f"• Umidità media radici (ECMWF): <b>{umidita_suolo_radici:.2f} m³/m³</b>\n"
        f"💡 <i>{consiglio_idrico}</i>\n\n"
        
        f"🦠 <b>ALLERTA FUNGHI (Prossime 48h)</b>\n"
        f"• Rischio: {stato_funghi}\n\n"
        
        f"🪲 <b>PRESSIONE INSETTI (Sfarfallamento)</b>\n"
        f"• Attività stimata: {stato_insetti}"
    )

    invia_messaggio_telegram(messaggio)

if __name__ == "__main__":
    main()
