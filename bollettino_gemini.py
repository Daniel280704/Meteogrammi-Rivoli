#!/usr/bin/env python3
import os
import requests
import sys
import google.generativeai as genai
from datetime import datetime

LAT = 45.0716
LON = 7.5157

def interpella_gemini(dati_meteo):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    # Usiamo il modello che hai trovato nel test
    model = genai.GenerativeModel('models/gemini-3.5-flash')
    
    today = datetime.now().strftime("%d/%m/%Y")
    
    prompt = f"""
    Sei un meteorologo professionista. Scrivi un bollettino sintetico per Rivoli (TO) per la data: {today}.
    
    REGOLE RIGIDE:
    1. ZERO chiacchiere, stile telegrafico.
    2. Usa SOLO queste 4 fasce: Mattino (06-12), Pomeriggio (12-18), Sera (18-24), Notte (00-06).
    3. Per ogni fascia indica: 
       - Rischio Pioggia (Nullo / Basso / Medio / Alto)
       - Condizioni cielo (es. Sereno, Variabile, Coperto)
       - Eventuale Vento forte (solo se raffiche > 30km/h)
    4. Includi in apertura o chiusura: T-Min e T-Max previste per oggi.
    5. IGNORA nebbia e brina (siamo a luglio).
    6. NON scrivere i millimetri di pioggia, usa solo il Rischio.

    DATI ANALITICI (Modelli: D2, AROME, EPS):
    {dati_meteo}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.1})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def fetch_api(url, params):
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Errore API: {e}")
        return None

def main():
    # Fetch dati orari (rischio, vento, nubi) e giornalieri (Tmin/max)
    dati = fetch_api("https://api.open-meteo.com/v1/forecast", {
        "latitude": LAT, "longitude": LON,
        "hourly": "precipitation,cloud_cover,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "models": "icon_d2,arome_france",
        "timezone": "Europe/Rome", "forecast_days": 1
    })
    
    dati_eps = fetch_api("https://ensemble-api.open-meteo.com/v1/ensemble", {
        "latitude": LAT, "longitude": LON,
        "hourly": "precipitation",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 1
    })

    if not dati or not dati_eps: sys.exit(1)

    # Preparazione stringa dati per l'AI
    report = f"Temp: Min {dati['daily']['temperature_2m_min'][0]}°C / Max {dati['daily']['temperature_2m_max'][0]}°C\n"
    report += "Fascia | Pioggia (D2/AROME/EPS-Max) | Nubi | Vento\n"
    
    orari = dati["hourly"]["time"]
    for i in range(24):
        # Media/Max semplificata per l'AI
        eps_vals = [dati_eps["hourly"][f"precipitation_member{m:02d}"][i] or 0 for m in range(1,21)]
        report += f"{orari[i][-5:]} | {dati['hourly']['precipitation_icon_d2'][i]}/{dati['hourly']['precipitation_arome_france'][i]}/{max(eps_vals):.1f} | {dati['hourly']['cloud_cover'][i]}% | {dati['hourly']['wind_speed_10m'][i]}km/h\n"

    # Invio e output
    bollettino = interpella_gemini(report)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                  data={"chat_id": chat_id, "text": bollettino, "parse_mode": "Markdown"})
    print("Bollettino inviato.")

if __name__ == "__main__":
    main()
