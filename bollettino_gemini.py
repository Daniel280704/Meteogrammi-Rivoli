#!/usr/bin/env python3
import os
import requests
from datetime import datetime
import sys

LAT = 45.0716
LON = 7.5157

def fetch_weather_data():
    # Usiamo i modelli ad alta risoluzione disponibili su Open-Meteo per l'Europa/Alpi
    # (D2 tedesco, AROME francese, e i due COSMO svizzeri)
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": "precipitation",
        "models": "icon_d2,arome_france,meteoswiss_cosmo_1e,meteoswiss_cosmo_2e",
        "timezone": "Europe/Rome",
        "forecast_days": 1
    }
    try:
        resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"❌ Errore API Meteo: {e}")
        sys.exit(1)

def interpella_gemini(dati_meteo):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY mancante!")
        sys.exit(1)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    # Costruiamo il prompt per istruire Gemini
    prompt = f"""
    Sei un meteorologo esperto e un divulgatore scientifico. Scrivi il bollettino meteo di nowcasting per oggi a Rivoli.
    Il testo deve essere discorsivo, professionale ma accessibile, perfetto per essere letto da una community di decine di migliaia di appassionati. 
    Usa le emoji in modo appropriato.

    Dividi la cronaca in 4 fasce orarie:
    - Mattino (06-12)
    - Pomeriggio (12-18)
    - Sera (18-24)
    - Notte (00-06)

    Ecco i millimetri di pioggia previsti ora per ora dai 4 modelli ad alta risoluzione (ICON-D2, AROME, COSMO-1E, COSMO-2E).
    Analizza i dati: se tutti i modelli prevedono pioggia in una fascia oraria, dichiara una probabilità altissima (es. 100%).
    Se solo alcuni la vedono (es. temporali termici isolati), parla di "previsione incerta" o "possibilità al X%".
    Menziona i modelli per nome per dare autorevolezza tecnica.

    DATI GREZZI DEI MODELLI:
    {dati_meteo}
    """

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        # Regoliamo la "fantasia" di Gemini. 0.2 significa molto analitico e ancorato ai dati.
        "generationConfig": {"temperature": 0.2} 
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        risultato = resp.json()
        return risultato["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"❌ Errore API Gemini: {e}")
        sys.exit(1)

def invia_telegram(testo):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": testo, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def main():
    print("📥 Scaricamento modelli meteo...")
    dati_grezzi = fetch_weather_data()
    
    # Estraiamo solo le precipitazioni per non sovraccaricare Gemini di numeri inutili
    orari = dati_grezzi["hourly"]["time"]
    pioggia_d2 = dati_grezzi["hourly"]["precipitation_icon_d2"]
    pioggia_arome = dati_grezzi["hourly"]["precipitation_arome_france"]
    pioggia_ch1 = dati_grezzi["hourly"]["precipitation_meteoswiss_cosmo_1e"]
    pioggia_ch2 = dati_grezzi["hourly"]["precipitation_meteoswiss_cosmo_2e"]
    
    riassunto_dati = "Ora | ICON-D2 | AROME | COSMO-1E | COSMO-2E\n"
    for i in range(24):
        riassunto_dati += f"{orari[i][-5:]} | {pioggia_d2[i]}mm | {pioggia_arome[i]}mm | {pioggia_ch1[i]}mm | {pioggia_ch2[i]}mm\n"
    
    print("🧠 Elaborazione analisi tramite Gemini...")
    bollettino_narrativo = interpella_gemini(riassunto_dati)
    
    print("✈️ Invio su Telegram...")
    invia_telegram(bollettino_narrativo)
    print("✅ Finito!")

if __name__ == "__main__":
    main()
