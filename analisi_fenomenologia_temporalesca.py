#!/usr/bin/env python3
"""
Analizzatore Termodinamico e Cinematico Avanzato per Rischio Temporali
*** VERSIONE DI TEST - TRIGGER FORZATO ***
- Il controllo Ensemble è disattivato.
- L'analisi viene eseguita forzatamente per la fascia oraria 17:00 - 20:00 del giorno corrente.
- Output ripristinato su Telegram.
"""

import os
import sys
import math
import requests
from datetime import datetime, timedelta

# SDK Ufficiale di Gemini
from google import genai
from google.genai import types

# Coordinate - Rivoli (TO)
LAT = 45.0734521841099
LON = 7.543386286825349

def scomposizione_vettoriale(speed_kmh, direction_deg):
    """Converte velocità e direzione in vettori U e V (m/s)."""
    if speed_kmh is None or direction_deg is None:
        return 0.0, 0.0
    speed_ms = speed_kmh / 3.6
    rad = math.radians(direction_deg)
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return u, v

def calcola_magnitudo_direzione(u, v):
    """Riconverte i vettori U e V in velocità (km/h) e direzione (gradi)."""
    speed_ms = math.sqrt(u**2 + v**2)
    speed_kmh = speed_ms * 3.6
    direction_deg = (math.degrees(math.atan2(-u, -v)) + 360) % 360
    return speed_kmh, direction_deg

def magnitudo_shear(u1, v1, u2, v2):
    """Calcola la magnitudo (m/s) della differenza vettoriale."""
    if None in (u1, v1, u2, v2):
        return None
    return math.sqrt((u2 - u1)**2 + (v2 - v1)**2)

def fetch_dati_convezione_d2():
    """Scarica il profilo verticale dal modello deterministico ICON-D2."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT, "longitude": LON, "models": "icon_d2",
        "hourly": "temperature_2m,dew_point_2m,cape,cin,lifted_index,freezing_level_height,"
                  "wind_speed_10m,wind_direction_10m,"
                  "temperature_850hPa,temperature_500hPa,"
                  "geopotential_height_850hPa,geopotential_height_500hPa,"
                  "wind_speed_850hPa,wind_direction_850hPa,"
                  "wind_speed_500hPa,wind_direction_500hPa,"
                  "relative_humidity_700hPa,surface_pressure",
        "timezone": "Europe/Rome", "forecast_days": 3
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()['hourly']

def formatta_sicuro(valore, template="{:.1f}"):
    return "N/D" if valore is None else template.format(valore)

def stima_grandine_python(cape, dls, lapse_rate, zero_termico):
    """Calcolo matematico della dimensione potenziale della grandine."""
    if None in (cape, dls, lapse_rate, zero_termico):
        return "N/D (Dati insufficienti per il calcolo)"
    if cape < 500: return "Assente o trascurabile."
    if zero_termico > 4200 and cape < 1200 and dls < 12:
        return "Rischio basso (Fusione prevalente in caduta dato lo zero termico alto)."
    if cape >= 1500 and (dls >= 20 or lapse_rate >= 7.0):
        return "GROSSA (> 3-4 cm) - Supportata da forti updraft e shear marcato."
    if cape >= 1000 and dls >= 12:
        return "MEDIA (1.5 - 3 cm) - Possibile in strutture multicellulari."
    if cape >= 500 and dls < 12:
        return "PICCOLA (< 1.5 cm) - Rapido collasso della colonna precipitante."
    return "Assente o di piccole dimensioni."

def interpella_gemini(report_tecnico, giorno_str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return "Errore: Manca la chiave API di Gemini."
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    Sei un meteorologo esperto in dinamiche convettive. Il tuo compito è stilare un bollettino di analisi 
    tecnica sul TIPO DI SETUP a disposizione dell'atmosfera per il giorno {giorno_str} a Rivoli (TO).

    DATI ESTRATTI NELLA FINESTRA PRECIPITATIVA FORZATA DI TEST (Media dei parametri):
    {report_tecnico}

    REGOLE RIGOROSE:
    1. INNESCabilità CONDIZIONATA: Non dare la precipitazione o i temporali per certi. L'inibizione convettiva (CIN) o l'assenza di trigger dinamici potrebbero annullare tutto. Inizia l'analisi esplicitando questo concetto (es. "Qualora il sistema riesca a superare l'inibizione convettiva...", "In caso di effettivo innesco...").
    2. LINGUAGGIO TECNICO MA CHIARO: Sei rivolto a un appassionato di meteorologia. Analizza i dati numerici forniti (Lapse Rate, DLS, LLS, LCL, Traslazione).
    3. TRASLAZIONE: Usa il parametro "Vettore Traslazione (CBL Wind)" per dedurre se il sistema sarà veloce (squall line) o stazionario/lento (rischio flash flood). Se < 20 km/h il rischio accumuli locali è alto.
    4. STRUTTURA CELLE: Usa DLS (Deep Layer Shear) per determinare la tipologia. < 12 m/s: Cella singola/Pulse storm. 12-20 m/s: Multicelle. > 20 m/s: Rischio Supercelle.
    5. FENOMENOLOGIA: Valuta il rischio Downburst incrociando l'umidità a 700 hPa (< 50% alta probabilità di raffiche secche) e il lapse rate. Includi la stima grandine del modello.
    6. Non superare i due/tre paragrafi ben scorrevoli. Non dare raccomandazioni di protezione civile.
    """

    response = client.models.generate_content(
        model='gemini-3.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3)
    )
    return response.text

def main():
    print("=== MODALITÀ TEST ATTIVA ===")
    print("Salto il controllo precipitazioni ENS. Scaricamento profili ICON-D2 in corso...")
    hourly = fetch_dati_convezione_d2()
    
    # --- BLOCCO FORZATURA FINESTRA ---
    # Cerchiamo la fascia 17:00 - 20:00 del giorno corrente.
    oggi_str = datetime.now().strftime("%Y-%m-%d")
    indici_forzati = []
    
    for i, time_str in enumerate(hourly['time']):
        dt = datetime.fromisoformat(time_str)
        if dt.strftime("%Y-%m-%d") == oggi_str and 17 <= dt.hour <= 20:
            indici_forzati.append(i)

    if not indici_forzati:
        print(f"Errore: Impossibile trovare la fascia 17-20 per {oggi_str} nei dati del modello.")
        return

    finestre_attive = {oggi_str: indici_forzati}
    print(f"⚠️ FORZATURA: Analisi impostata artificialmente su {oggi_str} fascia 17:00 - 20:00.")
    # --- FINE BLOCCO FORZATURA ---

    messaggio_telegram = "🌩 **[TEST] ANALISI SETUP CONVETTIVO CONDIZIONALE**\n\n"

    for data_str, indici_ore in finestre_attive.items():
        capes, cins, lrs = [], [], []
        u_10, v_10, u_850, v_850, u_500, v_500 = [], [], [], [], [], []
        lcls, rh700s, zts = [], [], []
        
        for idx in indici_ore:
            t2m = hourly['temperature_2m'][idx]
            tdew = hourly['dew_point_2m'][idx]
            t850, t500 = hourly['temperature_850hPa'][idx], hourly['temperature_500hPa'][idx]
            z850, z500 = hourly['geopotential_height_850hPa'][idx], hourly['geopotential_height_500hPa'][idx]
            
            if None not in (t2m, tdew): lcls.append(125 * (t2m - tdew))
            if None not in (t850, t500, z850, z500) and (z500 - z850) != 0:
                lrs.append((t850 - t500) / ((z500 - z850) / 1000.0))
                
            c_cape = hourly['cape'][idx]
            if c_cape is not None: capes.append(c_cape)
            c_cin = hourly.get('cin', [])[idx] if 'cin' in hourly else 0
            if c_cin is not None: cins.append(c_cin)
                
            rh = hourly['relative_humidity_700hPa'][idx]
            if rh is not None: rh700s.append(rh)
            
            zt = hourly['freezing_level_height'][idx]
            if zt is not None: zts.append(zt)

            # Vettori Vento
            u, v = scomposizione_vettoriale(hourly['wind_speed_10m'][idx], hourly['wind_direction_10m'][idx])
            u_10.append(u); v_10.append(v)
            u, v = scomposizione_vettoriale(hourly['wind_speed_850hPa'][idx], hourly['wind_direction_850hPa'][idx])
            u_850.append(u); v_850.append(v)
            u, v = scomposizione_vettoriale(hourly['wind_speed_500hPa'][idx], hourly['wind_direction_500hPa'][idx])
            u_500.append(u); v_500.append(v)

        # Nella versione di test, non blocchiamo l'esecuzione se c'è poco CAPE, 
        # altrimenti se oggi la colonna è stabile lo script si fermerebbe.
        max_cape = max(capes) if capes else 0
        if max_cape < 200:
            print(f"Nota: Il CAPE reale è molto basso ({max_cape} J/kg). Essendo un test, procedo comunque con l'analisi dei vettori.")

        media_cin = sum(cins)/len(cins) if cins else 0
        media_lr = sum(lrs)/len(lrs) if lrs else None
        media_lcl = sum(lcls)/len(lcls) if lcls else None
        media_rh700 = sum(rh700s)/len(rh700s) if rh700s else None
        media_zt = sum(zts)/len(zts) if zts else None
        
        avg_u10, avg_v10 = sum(u_10)/len(u_10) if u_10 else 0, sum(v_10)/len(v_10) if v_10 else 0
        avg_u850, avg_v850 = sum(u_850)/len(u_850) if u_850 else 0, sum(v_850)/len(v_850) if v_850 else 0
        avg_u500, avg_v500 = sum(u_500)/len(u_500) if u_500 else 0, sum(v_500)/len(v_500) if v_500 else 0
        
        dls = magnitudo_shear(avg_u10, avg_v10, avg_u500, avg_v500)
        lls = magnitudo_shear(avg_u10, avg_v10, avg_u850, avg_v850)
        
        # Calcolo Cloud Bearing Layer
        u_cbl = (avg_u850 + avg_u500) / 2
        v_cbl = (avg_v850 + avg_v500) / 2
        traslazione_kmh, traslazione_dir = calcola_magnitudo_direzione(u_cbl, v_cbl)

        stima_g = stima_grandine_python(max_cape, dls, media_lr, media_zt)

        report_dati = f"""
        Finestra FORZATA: Da {datetime.fromisoformat(hourly['time'][indici_ore[0]]).strftime('%H:%M')} a {datetime.fromisoformat(hourly['time'][indici_ore[-1]]).strftime('%H:%M')}
        Max CAPE: {formatta_sicuro(max_cape, "{:.0f}")} J/kg
        CIN Medio: {formatta_sicuro(media_cin, "{:.0f}")} J/kg
        LCL (Base Nubi): {formatta_sicuro(media_lcl, "{:.0f}")} m
        Lapse Rate Medio (850-500hPa): {formatta_sicuro(media_lr, "{:.1f}")} °C/km
        Deep Layer Shear (0-6km): {formatta_sicuro(dls, "{:.1f}")} m/s
        Low Level Shear (0-1.5km): {formatta_sicuro(lls, "{:.1f}")} m/s
        Vettore Traslazione (CBL Wind): {formatta_sicuro(traslazione_kmh, "{:.1f}")} km/h con provenienza da {formatta_sicuro(traslazione_dir, "{:.0f}")}°
        Umidità media 700hPa: {formatta_sicuro(media_rh700, "{:.0f}")}%
        Modello matematico grandine: {stima_g}
        """
        
        giorno_formattato = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        print(f"[{giorno_formattato}] Elaborazione responso diagnostico tramite Gemini per il setup forzato...")
        responso = interpella_gemini(report_dati, giorno_formattato)
        
        messaggio_telegram += f"📅 **Target: {giorno_formattato} (TEST)**\n\n{responso}\n\n➖➖➖➖➖➖➖➖➖➖\n\n"

    # Invio Telegram ripristinato
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": messaggio_telegram, "parse_mode": "Markdown"})
        if res.status_code == 200:
            print("Analisi convettiva (TEST) inviata con successo su Telegram!")
        else:
            print(f"Errore invio Telegram: {res.text}")
    else:
        print(messaggio_telegram)
        print("\n⚠️ Telegram Token o Chat ID non configurati nell'ambiente locale.")

if __name__ == "__main__":
    main()
