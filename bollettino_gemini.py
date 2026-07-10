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
    # Usiamo il modello confermato dal tuo test[cite: 1]
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
       - Eventuale Vento forte (se raffiche > 30km/h)
    4. Dalla tabella, estrai e indica in apertura: T-Min e T-Max previste.
    5. NON scrivere i mm di pioggia, usa solo il Rischio.
    6. Se l'umidità è molto alta e la T scende, menziona la possibilità di foschia/nebbia (se rilevante).

    TABELLA DATI (Ora | T | UR% | Dew | Prec.D2 | EPS-Max | Nubi | Vento | Raffica):
    {dati_meteo}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.1})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    # Fetch dati deterministici (ICON-D2)
    dati = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 1
    }).json()
    
    # Fetch EPS (Precipitazione)
    dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "precipitation",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 1
    }).json()

    # Preparazione report
    report = "Ora | T | UR% | Dew | Prec.D2 | EPS-Max | Nubi | Vento | Raffica\n"
    hourly = dati.get('hourly', {})
    orari = hourly.get('time', [])
    
    for i in range(24):
        if i >= len(orari): break
        
        eps_vals = [dati_eps['hourly'].get(f"precipitation_member{m:02d}", [0]*24)[i] or 0 for m in range(1,21)]
        eps_max = max(eps_vals) if eps_vals else 0.0
            
        t = hourly.get('temperature_2m', [0]*24)[i]
        ur = hourly.get('relative_humidity_2m', [0]*24)[i]
        dew = hourly.get('dew_point_2m', [0]*24)[i]
        p_d2 = hourly.get('precipitation', [0]*24)[i] or 0
        nubi = hourly.get('cloud_cover', [0]*24)[i]
        v_vel = hourly.get('wind_speed_10m', [0]*24)[i]
        v_raf = hourly.get('wind_gusts_10m', [0]*24)[i]
        
        report += f"{orari[i][-5:]} | {t}°C | {ur}% | {dew}°C | {p_d2} | {eps_max:.1f} | {nubi}% | {v_vel}km/h | {v_raf}km/h\n"

    # Invio
    bollettino = interpella_gemini(report)
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino, "parse_mode": "Markdown"})
    else:
        print(bollettino)

if __name__ == "__main__":
    main()
