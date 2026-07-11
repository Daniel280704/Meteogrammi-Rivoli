#!/usr/bin/env python3
"""
Analizzatore Termodinamico e Cinematico per Rischio Temporali (Stile ESTOFEX)
Modello: ICON-D2 (Copertura 48h)
- Integrazione col nuovo SDK google.genai
- Gestione sicura dei valori null (NoneType) restituiti dall'API
"""

import os
import sys
import math
import requests
from datetime import datetime

# Nuovo SDK Ufficiale di Gemini
from google import genai
from google.genai import types

LAT = 45.0716  # Rivoli
LON = 7.5157

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
    except Exception as e:
        print(f"Errore API Open-Meteo: {e}")
        sys.exit(1)

def scomposizione_vettoriale(speed_kmh, direction_deg):
    """Converte velocità e direzione in vettori U e V. Ritorna None se mancano dati."""
    if speed_kmh is None or direction_deg is None:
        return None, None
    speed_ms = speed_kmh / 3.6
    rad = math.radians(direction_deg)
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return u, v

def magnitudo_shear(u1, v1, u2, v2):
    """Calcola la magnitudo della differenza vettoriale. Ritorna None se mancano dati."""
    if None in (u1, v1, u2, v2):
        return None
    return math.sqrt((u2 - u1)**2 + (v2 - v1)**2)

def formatta_sicuro(valore, template="{:.1f}"):
    """Evita i crash se il server meteo non fornisce un dato (None)"""
    if valore is None:
        return "N/D"
    try:
        return template.format(valore)
    except:
        return "N/D"

def interpella_gemini(report_tecnico, giorno_str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Errore: Manca la chiave API di Gemini."
        
    try:
        # Inizializzazione del nuovo client SDK
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Sei un meteorologo esperto in convezione profonda (livello ESTOFEX).
        Il tuo compito è analizzare i seguenti parametri termodinamici e cinematici calcolati per {giorno_str} a Rivoli (TO) 
        nel momento di picco dell'instabilità, e fornire un bollettino sul TIPO DI TEMPORALE atteso in caso di innesco.

        DATI ESTRATTI DAL MODELLO ICON-D2:
        {report_tecnico}

        REGOLE DI INTERPRETAZIONE (USA QUESTE SOGLIE):
        1. WIND SHEAR PROFONDO (DLS 0-6 km):
           - < 10 m/s: Celle singole (Pulse storms). Rischio nubifragi molto localizzati e stazionari.
           - 10-20 m/s: Multicelle o Squall Lines (se c'è forzante lineare). Rischio colpi di vento (downburst) e grandine media.
           - > 20 m/s: Possibilità di Supercelle. Rischio grandine grossa e tornado.
        2. GRADIENTE TERMICO (Lapse Rate 850-500hPa):
           - > 6.5 °C/km: Forte instabilità verticale (correnti ascensionali molto violente).
           - > 7.0 °C/km: Condizioni estreme (EML - Elevated Mixed Layer), altissimo rischio grandine grossa.
        3. LCL (Livello di Condensazione):
           - < 1000 m: Base nubi molto bassa. Se il Low Level Shear (LLS) > 10 m/s, c'è rischio di tornado/funnel clouds.
           - > 1500 m: Base nubi alta. Aumenta drasticamente il rischio di Downburst (microburst secchi/evaporazione).
        4. UMIDITÀ A 700 hPa:
           - Se < 50%, c'è intrusione di aria secca in quota. Questo aumenta l'evaporazione della pioggia in caduta, rinforzando l'aria fredda discendente e causando violentissimi Downburst.

        REGOLE DI SCRITTURA:
        - Scrivi 2 o 3 paragrafi al massimo.
        - Usa un tono tecnico, chirurgico, ma comprensibile.
        - NON parlare delle probabilità di innesco. Dai per scontato che l'innesco avvenga.
        - Se mancano alcuni parametri (N/D), elabora la previsione basandoti su quelli presenti.
        """

        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
            )
        )
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    print("Scaricando profili termodinamici ICON-D2...")
    hourly = fetch_dati_convezione()
    
    giorni = {}
    for i, time_str in enumerate(hourly['time']):
        dt = datetime.fromisoformat(time_str)
        data_chiave = dt.strftime("%Y-%m-%d")
        
        if data_chiave not in giorni:
            giorni[data_chiave] = []
        giorni[data_chiave].append(i)

    messaggio_telegram = "🌩 **ANALISI RISCHIO CONVETTIVO (ICON-D2)**\n\n"
    innesco_trovato = False

    for data_str, indici in giorni.items():
        idx_max_cape = -1
        max_cape = -1
        
        for idx in indici:
            dt = datetime.fromisoformat(hourly['time'][idx])
            if 12 <= dt.hour <= 20: 
                cape_val = hourly['cape'][idx]
                if cape_val is not None and cape_val > max_cape:
                    max_cape = cape_val
                    idx_max_cape = idx
        
        if max_cape < 300 or idx_max_cape == -1:
            continue

        innesco_trovato = True
        
        ora_picco = datetime.fromisoformat(hourly['time'][idx_max_cape]).strftime("%H:%M")
        giorno_formattato = datetime.fromisoformat(hourly['time'][idx_max_cape]).strftime("%d/%m/%Y")
        
        # Estrazione Dati Grezzi
        t2m = hourly['temperature_2m'][idx_max_cape]
        tdew = hourly['dew_point_2m'][idx_max_cape]
        li = hourly['lifted_index'][idx_max_cape]
        zero_termico = hourly['freezing_level_height'][idx_max_cape]
        rh_700 = hourly['relative_humidity_700hPa'][idx_max_cape]
        
        t_850 = hourly['temperature_850hPa'][idx_max_cape]
        t_500 = hourly['temperature_500hPa'][idx_max_cape]
        z_850 = hourly['geopotential_height_850hPa'][idx_max_cape]
        z_500 = hourly['geopotential_height_500hPa'][idx_max_cape]
        
        # --- CALCOLI DERIVATI IN SICUREZZA ---
        
        # 1. LCL (Formula di Espy)
        lcl_m = 125 * (t2m - tdew) if (t2m is not None and tdew is not None) else None
        
        # 2. Lapse Rate
        if None not in (t_850, t_500, z_850, z_500) and (z_500 - z_850) != 0:
            lapse_rate = (t_850 - t_500) / ((z_500 - z_850) / 1000.0)
        else:
            lapse_rate = None
        
        # 3. Vettori Vento
        u_10m, v_10m = scomposizione_vettoriale(hourly['wind_speed_10m'][idx_max_cape], hourly['wind_direction_10m'][idx_max_cape])
        u_850, v_850 = scomposizione_vettoriale(hourly['wind_speed_850hPa'][idx_max_cape], hourly['wind_direction_850hPa'][idx_max_cape])
        u_500, v_500 = scomposizione_vettoriale(hourly['wind_speed_500hPa'][idx_max_cape], hourly['wind_direction_500hPa'][idx_max_cape])
        
        # 4. Shear
        deep_layer_shear = magnitudo_shear(u_10m, v_10m, u_500, v_500) 
        low_level_shear = magnitudo_shear(u_10m, v_10m, u_850, v_850) 
        
        # --- PREPARAZIONE REPORT TRAMITE FUNZIONE SCUDO ---
        report_dati = f"""
        Ora stimata di massima instabilità: {ora_picco}
        CAPE: {formatta_sicuro(max_cape, "{:.0f}")} J/kg
        Lifted Index: {formatta_sicuro(li, "{:.1f}")}
        LCL (Base Nubi stimata): {formatta_sicuro(lcl_m, "{:.0f}")} m
        Zero Termico: {formatta_sicuro(zero_termico, "{:.0f}")} m
        Lapse Rate (850-500hPa): {formatta_sicuro(lapse_rate, "{:.1f}")} °C/km
        Deep Layer Shear (0-6km): {formatta_sicuro(deep_layer_shear, "{:.1f}")} m/s
        Low Level Shear (0-1.5km): {formatta_sicuro(low_level_shear, "{:.1f}")} m/s
        Umidità Relativa a 700hPa: {formatta_sicuro(rh_700, "{:.0f}")}%
        """
        
        print(f"Dati elaborati per il {giorno_formattato}. Generazione responso AI...")
        responso = interpella_gemini(report_dati, giorno_formattato)
        
        messaggio_telegram += f"📅 **Previsione per il {giorno_formattato} (Picco ore {ora_picco})**\n"
        messaggio_telegram += f"🌡 **Parametri:** CAPE {formatta_sicuro(max_cape, '{:.0f}')} J/kg | Shear 0-6km {formatta_sicuro(deep_layer_shear, '{:.1f}')} m/s | LCL {formatta_sicuro(lcl_m, '{:.0f}')} m\n\n"
        messaggio_telegram += f"{responso}\n\n➖➖➖➖➖➖➖➖➖➖\n\n"

    if innesco_trovato:
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if token and chat_id:
            res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={"chat_id": chat_id, "text": messaggio_telegram, "parse_mode": "Markdown"})
            if res.status_code == 200:
                print("Analisi convettiva inviata con successo su Telegram!")
            else:
                print(f"Errore invio Telegram: {res.text}")
        else:
            print(messaggio_telegram)
            print("\n⚠️ Telegram Token o Chat ID non configurati nell'ambiente.")
    else:
        print("Atmosfera stabile (CAPE < 300) per i prossimi 2 giorni. Nessun avviso inviato.")

if __name__ == "__main__":
    main()
