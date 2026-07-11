#!/usr/bin/env python3
"""
Analizzatore Termodinamico e Cinematico per Rischio Temporali (Stile ESTOFEX)
Modello: ICON-D2 (Copertura 48h)
- Integrazione Filtro Precipitazioni ENS (Media Spaghi > 0.05mm)
- Calcolo esplicito dimensione grandine
- Integrazione col nuovo SDK google.genai
- Focus fenomenologico: analisi condizionata all'innesco
"""

import os
import sys
import math
import requests
from datetime import datetime

# Nuovo SDK Ufficiale di Gemini
from google import genai
from google.genai import types

# Coordinate aggiornate
LAT = 45.0734521841099
LON = 7.543386286825349

def get_pioggia_ens_media():
    """Scarica i 20 membri EPS di D2 e calcola la media precipitativa giornaliera"""
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
        
        # Estraiamo le chiavi di tutti i membri EPS
        membri = [k for k in hourly.keys() if "precipitation_member" in k]
        if not membri:
            return {}

        pioggia_giornaliera = {}
        for i, time_str in enumerate(hourly['time']):
            dt = datetime.fromisoformat(time_str)
            giorno = dt.strftime("%Y-%m-%d")
            
            if giorno not in pioggia_giornaliera:
                pioggia_giornaliera[giorno] = []
                
            somma_ora = 0
            valori_validi = 0
            for m in membri:
                val = hourly[m][i]
                if val is not None:
                    somma_ora += val
                    valori_validi += 1
            
            media_ora = somma_ora / valori_validi if valori_validi > 0 else 0
            pioggia_giornaliera[giorno].append(media_ora)
            
        # Sommiamo le medie orarie per avere l'accumulo medio totale del giorno
        for g in pioggia_giornaliera:
            pioggia_giornaliera[g] = sum(pioggia_giornaliera[g])
            
        return pioggia_giornaliera
    except Exception as e:
        print(f"⚠️ Errore nel calcolo delle ENS Pioggia: {e}")
        return {}


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
    """Calcola la magnitudo della differenza vettoriale."""
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

def stima_grandine_python(cape, dls, lapse_rate, zero_termico):
    """Calcolo matematico della dimensione potenziale della grandine."""
    if None in (cape, dls, lapse_rate, zero_termico):
        return "N/D (Dati insufficienti)"
        
    if cape < 500:
        return "Assente o pioggia forte."
        
    # Se fa caldissimo e manca ventilazione forte in quota, la grandine fonde in caduta
    if zero_termico > 4200 and cape < 1200 and dls < 12:
        return "Assente (Fusione prima dell'impatto al suolo dovuta allo zero termico elevato)."
        
    # Grandine Grossa
    if cape >= 1500 and (dls >= 20 or lapse_rate >= 7.0):
        return "GROSSA (> 3-4 cm) - Elevato rischio di supercelle o EML."
        
    # Grandine Media
    if cape >= 1000 and dls >= 12:
        return "MEDIA (1.5 - 3 cm) - Possibili multicelle organizzate."
        
    # Grandine Piccola
    if cape >= 500 and dls < 12:
        return "PICCOLA (< 1.5 cm) - Celle a inviluppo breve (Pulse Storms)."
        
    return "Assente o di piccole dimensioni."

def interpella_gemini(report_tecnico, giorno_str, stima_grandine):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Errore: Manca la chiave API di Gemini."
        
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Sei un meteorologo esperto in convezione profonda (livello ESTOFEX).
        Il tuo compito è analizzare i seguenti parametri calcolati per {giorno_str} a Rivoli (TO) nel momento di picco, 
        e fornire un bollettino sul TIPO DI TEMPORALE atteso; senza tecnicismi (non menzionare shear, cape, flusso discendente, ascendente e tutti gli altri parametri utili in sede previsionale).
        
        NOTA FONDAMENTALE: Non devi dare l'innesco del temporale per certo. Usa formule come "In caso di innesco", "Qualora si attivasse la convezione" o simili, e poi prosegui con l'analisi fenomenologica.

        DATI ICON-D2:
        {report_tecnico}
        
        STIMA GRANDINE PRE-CALCOLATA DAL MODELLO MATEMATICO:
        {stima_grandine}

        REGOLE DI INTERPRETAZIONE:
        1. Concentrati sulla fenomenologia severa (vento e tipologia di cella).
        2. Per la grandine, USA ESATTAMENTE la stima pre-calcolata che ti ho fornito qui sopra.
        3. UMIDITÀ A 700 hPa: Se < 50%, segnala il rischio di forti Downburst (aria secca che accelera i moti discendenti).
        4. LCL < 1000m e LLS > 10m/s = Rischio rotazione nei bassi strati (Funnel/Tornado).
        6. NON usare orari o riferimenti a picchi/momenti del giorno.
        7. NON dare l'evento per certo. Usa: "In caso di temporali", "Possibili fenomeni", "Qualora si attivassero".
        8. Descrivi in un unico paragrafo fluido: nubifragi (rischio allagamenti), raffiche di vento (downburst), grandine e durata stimata.
        9. Stile: calmo, professionale, non allarmistico, divulgativo.

        REGOLE DI SCRITTURA:
        - Scrivi 2 paragrafi tecnici ma comprensibili per appassionati.
        - Non fare raccomandazioni generiche di sicurezza ("restate in casa"), fornisci solo un'analisi atmosferica.
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
    print("Analisi in corso: scaricamento medie ensemble precipitazioni...")
    pioggia_ens = get_pioggia_ens_media()
    
    print("Scaricamento profili termodinamici ICON-D2...")
    hourly = fetch_dati_convezione()
    
    giorni = {}
    for i, time_str in enumerate(hourly['time']):
        dt = datetime.fromisoformat(time_str)
        data_chiave = dt.strftime("%Y-%m-%d")
        
        if data_chiave not in giorni:
            giorni[data_chiave] = []
        giorni[data_chiave].append(i)

    messaggio_telegram = "🌩 **ANALISI RISCHIO TEMPORALESCO**\n\n"
    innesco_trovato = False

    for data_str, indici in giorni.items():
        
        # 1. CONTROLLO PIOGGIA: Filtro per rumore di fondo matematico.
        # Deve esserci almeno una vera traccia (es. 0.05mm medi significa almeno 1mm su 1 spago).
        media_pioggia_giorno = pioggia_ens.get(data_str, 0)
        if media_pioggia_giorno < 0.05:
            print(f"[{data_str}] Analisi saltata: Assenza o rumore di fondo precipitativo nelle ENS (Media: {media_pioggia_giorno:.3f} mm).")
            continue

        # 2. RICERCA ORA DI PICCO (Max CAPE tra le 12 e le 20)
        idx_max_cape = -1
        max_cape = -1
        
        for idx in indici:
            dt = datetime.fromisoformat(hourly['time'][idx])
            if 12 <= dt.hour <= 20: 
                cape_val = hourly['cape'][idx]
                if cape_val is not None and cape_val > max_cape:
                    max_cape = cape_val
                    idx_max_cape = idx
        
        # Se c'è pioggia ma zero energia termica, saltiamo l'analisi temporalesca
        if max_cape < 300 or idx_max_cape == -1:
            print(f"[{data_str}] Analisi saltata: Prevista pioggia ma debole instabilità (CAPE < 300 J/kg).")
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
        lcl_m = 125 * (t2m - tdew) if (t2m is not None and tdew is not None) else None
        
        if None not in (t_850, t_500, z_850, z_500) and (z_500 - z_850) != 0:
            lapse_rate = (t_850 - t_500) / ((z_500 - z_850) / 1000.0)
        else:
            lapse_rate = None
        
        u_10m, v_10m = scomposizione_vettoriale(hourly['wind_speed_10m'][idx_max_cape], hourly['wind_direction_10m'][idx_max_cape])
        u_850, v_850 = scomposizione_vettoriale(hourly['wind_speed_850hPa'][idx_max_cape], hourly['wind_direction_850hPa'][idx_max_cape])
        u_500, v_500 = scomposizione_vettoriale(hourly['wind_speed_500hPa'][idx_max_cape], hourly['wind_direction_500hPa'][idx_max_cape])
        
        deep_layer_shear = magnitudo_shear(u_10m, v_10m, u_500, v_500) 
        low_level_shear = magnitudo_shear(u_10m, v_10m, u_850, v_850) 
        
        # ESECUZIONE ALGORITMO GRANDINE
        stima_g = stima_grandine_python(max_cape, deep_layer_shear, lapse_rate, zero_termico)

        report_dati = f"""
        Ora picco: {ora_picco}
        CAPE: {formatta_sicuro(max_cape, "{:.0f}")} J/kg
        LCL (Base Nubi): {formatta_sicuro(lcl_m, "{:.0f}")} m
        Zero Termico: {formatta_sicuro(zero_termico, "{:.0f}")} m
        Lapse Rate: {formatta_sicuro(lapse_rate, "{:.1f}")} °C/km
        Shear 0-6km: {formatta_sicuro(deep_layer_shear, "{:.1f}")} m/s
        Shear 0-1.5km: {formatta_sicuro(low_level_shear, "{:.1f}")} m/s
        Umidità a 700hPa: {formatta_sicuro(rh_700, "{:.0f}")}%
        """
        
        print(f"[{giorno_formattato}] Energia e Pioggia confermate. Generazione responso AI...")
        responso = interpella_gemini(report_dati, giorno_formattato, stima_g)
        
        messaggio_telegram += f"📅 **Previsione {giorno_formattato}\n"
        messaggio_telegram += f"🧊 **Potenziale Grandine:** {stima_g}\n\n"
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
        print("Analisi terminata. Nessuna forzante precipitativa associata ad instabilità per i prossimi 2 giorni.")

if __name__ == "__main__":
    main()
