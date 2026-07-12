#!/usr/bin/env python3
import os
import requests
from datetime import datetime, timedelta

import google.generativeai as genai

LAT = 45.073443
LON = 7.543472

GIORNI_IT = {0: "lunedì", 1: "martedì", 2: "mercoledì", 3: "giovedì", 4: "venerdì", 5: "sabato", 6: "domenica"}
MESI_IT = {1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno", 
           7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"}

def formatta_data_it(dt):
    return f"{GIORNI_IT[dt.weekday()]} {dt.day} {MESI_IT[dt.month]}"

def gradi_a_direzione(gradi):
    if gradi is None: return "N/A"
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'N']
    return dirs[int(round(gradi / 45.0)) % 8]

def calcola_disagio_caldo(t_aria, dew_point):
    if t_aria >= 36 or dew_point >= 24: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 34 or dew_point >= 22: return "(disagio forte 🔴)"
    elif t_aria >= 30 or dew_point >= 20: return "(disagio marcato 🟠)"
    elif t_aria >= 27 or dew_point >= 18: return "(disagio lieve 🟡)"
    return "(assenza di disagio 🟢)"

def calcola_disagio_freddo(windchill):
    if windchill < -10: return "(disagio estremo da freddo 🥶)"
    elif windchill < -5: return "(disagio forte da freddo 🔵)"
    elif windchill < 0: return "(disagio marcato da freddo 🧊)"
    elif windchill < 5: return "(disagio lieve da freddo ❄️)"
    return "(assenza di disagio 🟢)"

def media_lista(lista):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return int(round(sum(valori_validi) / len(valori_validi)))

def interpella_gemini(dati_testuali, oggi_str, giorni_str):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-1.5-flash')
    
    prompt = f"""
    Sei un meteorologo professionista. Il tuo compito è scrivere un bollettino discorsivo, fluido ed elegante per Rivoli (TO) a MEDIO TERMINE, partendo dalla sintesi oraria fornita.
    
    REGOLE FERREE (PENA IL FALLIMENTO):
    1. TITOLO: Inizia ESATTAMENTE con: **Aggiornamento meteo a medio termine di {oggi_str}**
    2. STRUTTURA: Scrivi esattamente tre paragrafi:
       - Il primo paragrafo dedicato a {giorni_str[2]}
       - Il secondo paragrafo dedicato a {giorni_str[3]}
       - Il terzo paragrafo dedicato a {giorni_str[4]}
    3. DIVIETO ASSOLUTO DI ELENCARE GLI ORARI: NON elencare MAI le temperature ora per ora (è severamente vietato scrivere cose come "alle 8 ci saranno 25 gradi, alle 9 ci saranno 26 gradi...").
    4. SINTESI DISCORSIVA: Sintetizza l'evoluzione usando fasi del giorno ("in mattinata", "nelle ore centrali", "nel pomeriggio", "in serata"). Usa la cronistoria fornita solo per capire l'andamento del cielo e dei fenomeni meteo, ma raccontali in modo narrativo.
    5. TEMPERATURE DA CITARE: Cita solo la temperatura minima (solitamente mattutina) e la temperatura massima prevista.
    6. DISAGIO TERMICO: Quando citi la temperatura massima, affianca ESATTAMENTE la dicitura sul disagio che trovi nei dati (es. inserisci testualmente "(disagio marcato 🟠)").
    
    ESEMPIO DI STILE DA IMITARE ALLA PERFEZIONE:
    "La giornata di {giorni_str[2]} si aprirà con condizioni di stabilità atmosferica. Le temperature minime si assesteranno sui 19°C. Durante le ore di luce il cielo si manterrà in prevalenza sereno, favorendo un ampio soleggiamento che porterà la massima a 33°C (disagio marcato 🟠). Nel tardo pomeriggio parziale aumento della nuvolosità ma senza fenomeni di rilievo."
    
    DATI GIORNALIERI DA TRASFORMARE IN TESTO:
    {dati_testuali}
    """
    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.25})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    mese_corrente = datetime.now().month
    inverno = mese_corrente in [11, 12, 1, 2, 3]
    estate = mese_corrente in [5, 6, 7, 8, 9, 10]
    
    try:
        # Richiesta a 5 giorni, forzando ICON-CH2
        dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "wind_direction_10m,cape,sunshine_duration,apparent_temperature,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
            "daily": "sunrise,sunset",
            "models": "icon_ch2",
            "timezone": "Europe/Rome", "forecast_days": 5
        }, timeout=10).json()

        dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m",
            "models": "icon_ch2",
            "timezone": "Europe/Rome", "forecast_days": 5
        }, timeout=10).json()
            
    except Exception as e:
        print(f"Errore fatale nel recupero dati Open-Meteo: {e}")
        return

    h_det = dati_det.get('hourly', {})
    h_eps = dati_eps.get('hourly', {})
    orari = h_det.get('time', [])
    
    # Salvataggio se ICON-CH2 restituisce solo 48 ore (spesso accade coi modelli ad alta risoluzione)
    if len(orari) <= 48:
        print("Attenzione: Open-Meteo ha restituito solo 48h per ICON-CH2. Il medio termine non è disponibile con questo modello.")
        # Se capita, nel file potresti sostituire "icon_ch2" con "icon_eu" per garantire la profondità a 5 giorni.
        return

    sunrise_str = dati_det.get('daily', {}).get('sunrise', [])
    sunset_str = dati_det.get('daily', {}).get('sunset', [])

    # Strutture per i Giorni 3 (indice 2), 4 (indice 3), 5 (indice 4)
    sintesi = {2: [], 3: [], 4: []}
    t_min = {2: 100, 3: 100, 4: 100}
    t_max = {2: -100, 3: -100, 4: -100}
    dew_max = {2: -100, 3: -100, 4: -100}
    windchill_min = {2: 100, 3: 100, 4: 100}
    
    # Pre-carichiamo il dew point della 47esima ora per il controllo Föhn sulla 48esima
    dew_point_prev = None
    if len(orari) > 47:
        dew_membri_47 = [h_eps[k][47] for k in h_eps if k.startswith('dew_point_2m_member')]
        dew_point_prev = media_lista(dew_membri_47)

    # LOOP DALLE 48 ORE FINO ALLE 120 (Giorno 3, 4, 5)
    for i in range(48, min(120, len(orari))):
        ora_dt = datetime.fromisoformat(orari[i])
        ora_solare = ora_dt.hour
        giorno_idx = i // 24 # 2 = Dopodomani, 3 = Tra 3 giorni, 4 = Tra 4 giorni
        
        t_membri = [h_eps[k][i] for k in h_eps if k.startswith('temperature_2m_member')]
        t_media = media_lista(t_membri)
        
        dew_membri = [h_eps[k][i] for k in h_eps if k.startswith('dew_point_2m_member')]
        dew_media = media_lista(dew_membri)
        
        ur_membri = [h_eps[k][i] for k in h_eps if k.startswith('relative_humidity_2m_member')]
        ur_media = media_lista(ur_membri)
        
        w_spd_membri = [h_eps[k][i] for k in h_eps if k.startswith('wind_speed_10m_member')]
        w_spd_media = media_lista(w_spd_membri)
        
        w_gst_membri = [h_eps[k][i] for k in h_eps if k.startswith('wind_gusts_10m_member')]
        w_gst_media = media_lista(w_gst_membri)
        
        w_dir = h_det.get('wind_direction_10m', [])[i] if i < len(h_det.get('wind_direction_10m', [])) else None
        w_dir_str = gradi_a_direzione(w_dir)
        
        # INSTABILITÀ BASATA *SOLO* SULLE ENS DI ICON-CH2
        prec_membri = [h_eps[k][i] for k in h_eps if k.startswith('precipitation_member')]
        prec_media = sum([v for v in prec_membri if v is not None]) / len(prec_membri) if prec_membri else 0
        
        instabilita = "assente"
        if prec_media >= 1:
            if prec_media >= 5: instabilita = "spiccata instabilità"
            elif prec_media >= 3: instabilita = "marcata instabilità"
            else: instabilita = "possibile instabilità"

        tipo_prec = ""
        if instabilita != "assente":
            if inverno:
                if t_media < 2:
                    strati_quota = [
                        h_det.get('temperature_1000hPa', [])[i] if i < len(h_det.get('temperature_1000hPa', [])) else None,
                        h_det.get('temperature_975hPa', [])[i] if i < len(h_det.get('temperature_975hPa', [])) else None,
                        h_det.get('temperature_950hPa', [])[i] if i < len(h_det.get('temperature_950hPa', [])) else None,
                        h_det.get('temperature_925hPa', [])[i] if i < len(h_det.get('temperature_925hPa', [])) else None,
                        h_det.get('temperature_900hPa', [])[i] if i < len(h_det.get('temperature_900hPa', [])) else None,
                        h_det.get('temperature_850hPa', [])[i] if i < len(h_det.get('temperature_850hPa', [])) else None,
                        h_det.get('temperature_800hPa', [])[i] if i < len(h_det.get('temperature_800hPa', [])) else None
                    ]
                    inversione_presente = any(t > 1 for t in strati_quota if t is not None)
                    if inversione_presente:
                        if t_media > 0: tipo_prec = "pioggia (a causa di inversione termica in quota)"
                        else: tipo_prec = "PERICOLO PIOGGIA CONGELANTE (Gelicidio per inversione termica)"
                    else: tipo_prec = "neve"
                else: tipo_prec = "pioggia"
            else:
                cape = h_det.get('cape', [])[i] if i < len(h_det.get('cape', [])) else 0
                if cape is None: cape = 0
                if cape > 400: tipo_prec = "temporale"
                else: tipo_prec = "rovesci"

        vento_evento = ""
        if dew_point_prev is not None:
            crollo_dew = dew_point_prev - dew_media >= 2
            if w_dir_str in ['NW', 'N', 'W'] and w_gst_media > 25 and crollo_dew:
                vento_evento = "improvviso rinforzo per probabile Föhn"
            elif w_dir_str in ['E', 'NE', 'SE'] and w_gst_media > 20 and not crollo_dew:
                vento_evento = "ventilazione umida orientale"
                
        if not inverno and instabilita == "assente" and w_gst_media > 40:
            vento_evento = "improvvise raffiche (possibile outflow da temporali vicini)"
        elif not inverno and instabilita != "assente" and w_gst_media > 40:
            vento_evento = f"raffiche che accompagnano il {tipo_prec}"
            
        dew_point_prev = dew_media

        alba = datetime.fromisoformat(sunrise_str[giorno_idx])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx])
        alba_piu_2 = alba + timedelta(hours=2)
        tramonto_meno_2 = tramonto - timedelta(hours=2)
        
        cielo = ""
        if alba_piu_2 <= ora_dt <= tramonto_meno_2:
            sun_sec = h_det.get('sunshine_duration', [])[i] if i < len(h_det.get('sunshine_duration', [])) else None
            sun_minuti = (sun_sec or 0) / 60
            if sun_minuti < 5: cielo = "molto nuvoloso o coperto"
            elif sun_minuti <= 15: cielo = "irregolarmente o molto nuvoloso"
            elif sun_minuti <= 30: cielo = "parzialmente o irregolarmente nuvoloso"
            elif sun_minuti <= 45: cielo = "parzialmente nuvoloso"
            elif sun_minuti <= 55: cielo = "poco nuvoloso"
            else: cielo = "sereno"

        nebbia = ""
        if abs(dew_media - t_media) <= 1 and ur_media >= 95 and w_spd_media < 10:
            nebbia = "possibile formazione di nebbia"

        # AGGIORNAMENTO ESTREMI TERMICI
        t_min[giorno_idx] = min(t_min[giorno_idx], t_media)
        t_max[giorno_idx] = max(t_max[giorno_idx], t_media)
        if estate: dew_max[giorno_idx] = max(dew_max[giorno_idx], dew_media)
        elif inverno:
            app_t = h_det.get('apparent_temperature', [])[i] if i < len(h_det.get('apparent_temperature', [])) else t_media
            if app_t is not None: windchill_min[giorno_idx] = min(windchill_min[giorno_idx], app_t)

        record = f"Ore {ora_solare}: T={t_media}°C."
        if cielo: record += f" Cielo {cielo}."
        if instabilita != "assente": record += f" Rilevata {instabilita} con {tipo_prec}."
        if vento_evento: record += f" {vento_evento}."
        if nebbia: record += f" {nebbia}."
        
        sintesi[giorno_idx].append(record)

    # CALCOLO DISAGI
    disagio = {2: "", 3: "", 4: ""}
    for g in [2, 3, 4]:
        if estate and t_max[g] != -100:
            disagio[g] = calcola_disagio_caldo(t_max[g], dew_max[g])
        elif inverno and windchill_min[g] != 100:
            disagio[g] = calcola_disagio_freddo(windchill_min[g])

    dt_oggi = datetime.now()
    oggi_str = formatta_data_it(dt_oggi)
    
    giorni_str = {
        2: formatta_data_it(dt_oggi + timedelta(days=2)),
        3: formatta_data_it(dt_oggi + timedelta(days=3)),
        4: formatta_data_it(dt_oggi + timedelta(days=4))
    }

    # ASSEMBLAGGIO TESTO
    testo_per_ia = ""
    for g in [2, 3, 4]:
        if not sintesi[g]: continue
        testo_per_ia += f"GIORNO: {giorni_str[g]}\n"
        testo_per_ia += f"- Temperatura Minima: {t_min[g]}°C\n"
        testo_per_ia += f"- Temperatura Massima: {t_max[g]}°C {disagio[g]}\n"
        testo_per_ia += "CRONISTORIA DEGLI EVENTI:\n"
        testo_per_ia += "\n".join(sintesi[g]) + "\n\n"

    bollettino_finale = interpella_gemini(testo_per_ia, oggi_str, giorni_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "Markdown"})
        if risposta_tg.status_code == 200:
            print("Bollettino a medio termine inviato con successo!")
        else:
            print(f"Errore Telegram: {risposta_tg.text}")
    else:
        print("Errore: Token o Chat ID mancanti! Stampo a video:")
        print("-------------------------------------------------")
        print(bollettino_finale)

if __name__ == "__main__":
    main()