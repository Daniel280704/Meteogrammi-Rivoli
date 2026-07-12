#!/usr/bin/env python3
import os
import requests
import sys
import google.generativeai as genai
from datetime import datetime, timedelta
import locale

# Tentativo di usare l'italiano per i giorni della settimana
try:
    locale.setlocale(locale.LC_TIME, 'it_IT.UTF-8')
except:
    pass

LAT = 45.073443
LON = 7.543472

def interpella_gemini(dati_meteo, info_giornaliere):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    
    # Modello ottimizzato per il testo
    model = genai.GenerativeModel('models/gemini-3-flash-preview')    

    oggi_str = datetime.now().strftime("%A %d %B")
    domani_str = (datetime.now() + timedelta(days=1)).strftime("%A %d %B")

    prompt = f"""
    Sei un meteorologo professionista. Scrivi un bollettino meteo discorsivo per Rivoli (TO) per le prossime 48 ore.
    Oggi è {oggi_str}, domani sarà {domani_str}.
    
    RIFERIMENTI UFFICIALI (Usa questi valori per le temperature min/max):
    {info_giornaliere}

    REGOLE DI SCRITTURA (BOLLETTINO AVANZATO):
    1. NON usare elenchi puntati. Scrivi paragrafi fluidi e professionali.
    2. Usa le temperature min/max fornite nei riferimenti ufficiali come base della narrazione.
    
    REGOLA PRECIPITAZIONI, STAGIONALITÀ E PROBABILITÀ (CRITICA):
    3. Analizza SEMPRE le colonne 'Prec.D2' e 'Probabilità'. Se vedi valori di precipitazione (>0), DEVI rispettare questi parametri:
       - STAGIONALITÀ: Tra MARZO e OTTOBRE avvisa del rischio di "rovesci" o "temporali sparsi". Tra NOVEMBRE e FEBBRAIO usa ESCLUSIVAMENTE termini come "piogge", "precipitazioni" o "pioviggini" (vietato menzionare i temporali in inverno).
       - FINESTRA ORARIA: Indica sempre l'intervallo temporale (es. "nel tardo pomeriggio", "nella prima mattinata"). Non elencare le singole ore.
       - PROBABILITÀ: Usa la colonna 'Probabilità' per calibrare le tue parole. Se è "Bassa" o "Medio-Bassa", parla di fenomeni "possibili", "locali" o "isolati". Se è "Medio-Alta" o "Alta", parla di fenomeni "molto probabili", "estesi" o "certi".
    
    REGOLA NEVE:
    4. Se le precipitazioni sono presenti (>0) e in quelle stesse ore la Temperatura (T) è <= 2°C, DEVI esplicitamente annunciare la possibilità di nevicate o pioggia mista a neve.
    
    REGOLE DI DISAGIO TERMICO (BIOMETEOROLOGIA):
    5. AFA E CALDO (Basato su indice Humidex usando T e Dew Point):
       - ASSENZA DI DISAGIO: Se non rientra nei casi sotto, non menzionare l'afa.
       - DISAGIO MODERATO: Se (T >= 28°C e Dew >= 15°C) OPPURE (T >= 25°C e Dew >= 20°C), segnala "afa" e "disagio termico moderato".
       - FORTE DISAGIO: Se (T >= 32°C e Dew >= 20°C) OPPURE (T >= 30°C e Dew >= 24°C), segnala "caldo opprimente", "afa intensa".
       
    6. WIND CHILL (Basato su T e Vento):
       - ASSENZA DI DISAGIO: Se Vento < 15 km/h o T > 8°C, non menzionare il freddo percepito.
       - DISAGIO MODERATO: Se (T <= 8°C e Vento >= 15 km/h), spiega che il vento renderà il freddo più pungente.
       - FORTE DISAGIO: Se (T <= 0°C e Vento >= 50 km/h) OPPURE (T <= -2°C e Vento >= 35 km/h) OPPURE (T <= -5°C e Vento >= 20 km/h), avvisa di condizioni "gelide".
    
    REGOLA NEBBIA/BRINA:
    7. Menziona foschie o nebbie SOLO in caso di inversione termica probabile: aria stagnante (Vento < 5 km/h), T notturna vicina o sotto lo 0°C, e UR% vicina al 100%.
    
    DIVIETO ASSOLUTO SUI TERMINI TECNICI (MOLTO IMPORTANTE):
    8. È severamente VIETATO menzionare nel testo finale i nomi delle colonne della tabella (come "Prec.D2", "UR%", "Dew", "T", "Probabilità"). Usa la tabella solo come "cervello", ma nel testo usa un linguaggio discorsivo (es. "umidità elevata", "alta probabilità di pioggia").

    DATI ANALITICI ORARI (Ora | T | UR% | Dew | Prec.D2 | Probabilità | Vento | Raffica):
    {dati_meteo}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.3})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    # Fetch dati deterministici (ICON-D2)
    dati = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 2
    }).json()

    # Fetch Ensemble (ICON-D2 EPS) - 20 scenari
    dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "precipitation",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 2
    }).json()

    daily = dati.get('daily', {})
    info_giornaliere = f"""
    {datetime.now().strftime("%A %d %B")}: Min {daily.get('temperature_2m_min', ['N/A'])[0]}°C, Max {daily.get('temperature_2m_max', ['N/A'])[0]}°C
    {(datetime.now() + timedelta(days=1)).strftime("%A %d %B")}: Min {daily.get('temperature_2m_min', ['N/A', 'N/A'])[1]}°C, Max {daily.get('temperature_2m_max', ['N/A', 'N/A'])[1]}°C
    """

    report = "Ora | T | UR% | Dew | Prec.D2 | Probabilità | Vento | Raffica\n"
    hourly = dati.get('hourly', {})
    orari = hourly.get('time', [])

    for i in range(48): 
        if i >= len(orari): break

        # Estrazione 20 membri EPS per quest'ora
        eps_vals = [dati_eps['hourly'].get(f"precipitation_member{m:02d}", [0]*48)[i] or 0 for m in range(1, 21)]
        
        # Calcolo Media e conteggio scenari significativi (> 1.0 mm)
        eps_mean = (sum(eps_vals) / len(eps_vals)) if eps_vals else 0.0
        scenari_over_1mm = sum(1 for v in eps_vals if v >= 1.0)

        t = hourly.get('temperature_2m', [0]*48)[i]
        ur = hourly.get('relative_humidity_2m', [0]*48)[i]
        dew = hourly.get('dew_point_2m', [0]*48)[i]
        p_d2 = float(hourly.get('precipitation', [0]*48)[i] or 0)
        v_vel = hourly.get('wind_speed_10m', [0]*48)[i]
        v_raf = hourly.get('wind_gusts_10m', [0]*48)[i]

        # =======================================================
        # FILTRO DI CONFIDENZA E CALCOLO PROBABILITÀ TESTUALE
        # =======================================================
        ce_riscontro = (p_d2 > 0 and eps_mean > 0)
        segnale_forte = (p_d2 > 0.5) or (eps_mean > 0.5) or (scenari_over_1mm >= 2)
        
        prob_testo = "Assente"
        
        # Se c'è almeno un segnale valido, classifichiamo la probabilità
        if ce_riscontro or segnale_forte:
            if scenari_over_1mm >= 15:
                prob_testo = "Alta"
            elif scenari_over_1mm >= 10:
                prob_testo = "Medio-Alta"
            elif scenari_over_1mm >= 5:
                prob_testo = "Medio-Bassa"
            elif scenari_over_1mm >= 2:
                prob_testo = "Bassa"
            elif p_d2 > 0:
                prob_testo = "Molto Bassa" # Segnale solo deterministico, non supportato dalle EPS
        else:
            p_d2 = 0.0 # Se il segnale è rumore di fondo, lo azzeriamo del tutto
        # =======================================================

        report += f"{orari[i][-5:]} | {t}°C | {ur}% | {dew}°C | {p_d2:.1f} | {prob_testo} | {v_vel}km/h | {v_raf}km/h\n"

    # Invia a Gemini
    bollettino = interpella_gemini(report, info_giornaliere)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino, "parse_mode": "Markdown"})

        if risposta_tg.status_code == 200:
            print("Bollettino inviato con successo al canale!")
        else:
            print(f"ERRORE TELEGRAM - Codice: {risposta_tg.status_code}")
            print(f"Motivo esatto: {risposta_tg.text}")
            print("\n--- TESTO CHE HA CAUSATO L'ERRORE ---\n")
            print(bollettino)
    else:
        print("Errore: Non trovo i Secrets (Token o Chat ID)!")

if __name__ == "__main__":
    main()