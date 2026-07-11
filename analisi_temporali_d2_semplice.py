#!/usr/bin/env python3
"""
Analizzatore Meteo per Rivoli (TO) - Versione "Previsore Amichevole"
Analisi probabilistica dei rischi (pioggia, vento, grandine) senza orari.
"""

import os
import sys
import math
import requests
from datetime import datetime
from google import genai
from google.genai import types

# Coordinate esatte
LAT = 45.0734521841099
LON = 7.543386286825349

def get_pioggia_ens_media():
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "models": "icon_d2",
        "hourly": "precipitation",
        "timezone": "Europe/Rome",
        "forecast_days": 2
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        hourly = resp.json()['hourly']
        membri = [k for k in hourly.keys() if "precipitation_member" in k]
        if not membri: return {}

        pioggia_giornaliera = {}
        for i, time_str in enumerate(hourly['time']):
            dt = datetime.fromisoformat(time_str)
            giorno = dt.strftime("%Y-%m-%d")
            if giorno not in pioggia_giornaliera: pioggia_giornaliera[giorno] = []
            somma_ora = sum(hourly[m][i] for m in membri if hourly[m][i] is not None)
            pioggia_giornaliera[giorno].append(somma_ora / len(membri))
            
        for g in pioggia_giornaliera: pioggia_giornaliera[g] = sum(pioggia_giornaliera[g])
        return pioggia_giornaliera
    except: return {}

def fetch_dati_convezione():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "models": "icon_d2",
        "hourly": "temperature_2m,dew_point_2m,cape,lifted_index,freezing_level_height,"
                  "wind_speed_10m,wind_direction_10m,"
                  "temperature_850hPa,temperature_500hPa,"
                  "geopotential_height_850hPa,geopotential_height_500hPa,"
                  "wind_speed_850hPa,wind_direction_850hPa,"
                  "wind_speed_500hPa,wind_direction_500hPa,"
                  "relative_humidity_700hPa",
        "timezone": "Europe/Rome",
        "forecast_days": 2
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()['hourly']
    except: sys.exit(1)

def scomposizione_vettoriale(speed_kmh, direction_deg):
    if speed_kmh is None or direction_deg is None: return None, None
    speed_ms = speed_kmh / 3.6
    rad = math.radians(direction_deg)
    return -speed_ms * math.sin(rad), -speed_ms * math.cos(rad)

def magnitudo_shear(u1, v1, u2, v2):
    if None in (u1, v1, u2, v2): return None
    return math.sqrt((u2 - u1)**2 + (v2 - v1)**2)

def stima_grandine_semplice(cape, dls, lapse_rate, zero_termico):
    if None in (cape, dls, lapse_rate, zero_termico): return "Non valutabile"
    if cape < 500: return "nessuna grandine significativa"
    if zero_termico > 4200 and cape < 1200 and dls < 12: return "nessuna grandine, si scioglierebbe prima di arrivare a terra"
    if cape >= 1500 and (dls >= 20 or lapse_rate >= 7.0): return "grandine di dimensioni medio-grandi"
    if cape >= 1000 and dls >= 12: return "possibile grandine di medie dimensioni"
    if cape >= 500 and dls < 12: return "possibile grandine di piccole dimensioni"
    return "nessuna grandine significativa"

def interpella_gemini(report_tecnico, stima_grandine):
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    Sei un meteorologo esperto che scrive per i cittadini di Rivoli. 
    Analizza i dati che ti passo e scrivi un bollettino di allerta amichevole.
    
    DATI: {report_tecnico}
    STIMA GRANDINE: {stima_grandine}

    REGOLE RIGOROSE:
    1. NON usare orari, ore del giorno o riferimenti a "picchi".
    2. NON dare l'evento per certo. Usa sempre: "In caso di temporale", "Se dovessero svilupparsi fenomeni".
    3. Analizza le criticità in base ai dati:
       - Se l'energia (CAPE) è alta: menziona il rischio di nubifragi intensi.
       - Se l'umidità a 700hPa è bassa e c'è vento: menziona il rischio di forti raffiche (downburst).
       - Includi sempre la stima della grandine.
    4. Stile: semplice, discorsivo, rassicurante ma attento. Massimo 2 paragrafi.
    """
    
    response = client.models.generate_content(model='gemini-3-flash-preview', contents=prompt)
    return response.text

def main():
    pioggia_ens = get_pioggia_ens_media()
    hourly = fetch_dati_convezione()
    giorni = {}
    for i, t in enumerate(hourly['time']):
        g = datetime.fromisoformat(t).strftime("%Y-%m-%d")
        if g not in giorni: giorni[g] = []
        giorni[g].append(i)

    messaggio_finale = "🌩 **Analisi probabilità temporali (Rivoli)**\n\n"
    innesco = False

    for g, indici in giorni.items():
        if pioggia_ens.get(g, 0) < 0.05: continue
        
        idx = max((i for i in indici if 12 <= datetime.fromisoformat(hourly['time'][i]).hour <= 20), 
                  key=lambda i: hourly['cape'][i] or 0, default=-1)
        
        if idx == -1 or hourly['cape'][idx] < 300: continue
        
        innesco = True
        u1, v1 = scomposizione_vettoriale(hourly['wind_speed_10m'][idx], hourly['wind_direction_10m'][idx])
        u2, v2 = scomposizione_vettoriale(hourly['wind_speed_500hPa'][idx], hourly['wind_direction_500hPa'][idx])
        dls = magnitudo_shear(u1, v1, u2, v2)
        
        # Report senza orari
        report = f"CAPE: {hourly['cape'][idx]}, Shear: {dls}, Rh700: {hourly['relative_humidity_700hPa'][idx]}"
        stima_g = stima_grandine_semplice(hourly['cape'][idx], dls, 6.5, hourly['freezing_level_height'][idx])
        
        testo = interpella_gemini(report, stima_g)
        messaggio_finale += f"📅 **{g}**\n{testo}\n\n➖➖➖➖➖➖\n\n"

    if innesco:
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": messaggio_finale, "parse_mode": "Markdown"})
    else:
        print("Atmosfera non favorevole per segnalazioni.")

if __name__ == "__main__":
    main()
