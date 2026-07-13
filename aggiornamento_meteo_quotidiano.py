#!/usr/bin/env python3
import os
import sys
import time
import requests
from datetime import datetime, timedelta

# NUOVO SDK GEMINI
from google import genai
from google.genai import types

LAT = 45.07347491421504
LON = 7.543461388723449

GIORNI_IT = {0: "lunedì", 1: "martedì", 2: "mercoledì", 3: "giovedì", 4: "venerdì", 5: "sabato", 6: "domenica"}
MESI_IT = {1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno", 
           7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"}

def scarica_dati_con_retry(url, params, max_retries=3):
    for tentativo in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Errore connessione Open-Meteo (Tentativo {tentativo + 1}/{max_retries}): {e}")
            if tentativo < max_retries - 1:
                time.sleep(10)
            else:
                raise e

def formatta_data_it(dt):
    return f"{GIORNI_IT[dt.weekday()]} {dt.day} {MESI_IT[dt.month]}"

def gradi_a_direzione(gradi):
    if gradi is None: return "N/A"
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'N']
    return dirs[int(round(gradi / 45.0)) % 8]

def calcola_disagio_caldo(t_aria, dew_point):
    if t_aria >= 40 and dew_point >= 15: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 38 and dew_point >= 18: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 36 and dew_point >= 20: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 34 and dew_point >= 22: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 32 and dew_point >= 24: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 30 and dew_point >= 25: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 28 and dew_point >= 26: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    
    elif t_aria >= 38 and dew_point >= 12: return "(disagio forte 🔴)"
    elif t_aria >= 36 and dew_point >= 15: return "(disagio forte 🔴)"
    elif t_aria >= 34 and dew_point >= 18: return "(disagio forte 🔴)"
    elif t_aria >= 32 and dew_point >= 20: return "(disagio forte 🔴)"
    elif t_aria >= 30 and dew_point >= 22: return "(disagio forte 🔴)"
    elif t_aria >= 28 and dew_point >= 24: return "(disagio forte 🔴)"
    elif t_aria >= 26 and dew_point >= 25: return "(disagio forte 🔴)"
    
    elif t_aria >= 36 and dew_point >= 10: return "(disagio marcato 🟠)"
    elif t_aria >= 34 and dew_point >= 13: return "(disagio marcato 🟠)"
    elif t_aria >= 32 and dew_point >= 16: return "(disagio marcato 🟠)"
    elif t_aria >= 30 and dew_point >= 18: return "(disagio marcato 🟠)"
    elif t_aria >= 28 and dew_point >= 20: return "(disagio marcato 🟠)"
    elif t_aria >= 26 and dew_point >= 22: return "(disagio marcato 🟠)"
    elif t_aria >= 24 and dew_point >= 24: return "(disagio marcato 🟠)"
    
    elif t_aria >= 32 and dew_point >= 8: return "(disagio lieve 🟡)"
    elif t_aria >= 30 and dew_point >= 11: return "(disagio lieve 🟡)"
    elif t_aria >= 28 and dew_point >= 13: return "(disagio lieve 🟡)"
    elif t_aria >= 26 and dew_point >= 15: return "(disagio lieve 🟡)"
    elif t_aria >= 24 and dew_point >= 17: return "(disagio lieve 🟡)"
    elif t_aria >= 22 and dew_point >= 19: return "(disagio lieve 🟡)"
    
    else:
        return "(nessun disagio o caldo tollerabile)"

def calcola_disagio_freddo(windchill):
    if windchill < -40: return "(disagio estremo da freddo 🥶)"
    elif windchill < -25: return "(disagio forte da freddo 🥶)"
    elif windchill < -10: return "(disagio marcato da freddo 🥶)"
    elif windchill < 0: return "(disagio lieve da freddo 🥶)"
    else:
        return "(nessun disagio o freddo tollerabile)"

def media_lista(lista):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return int(round(sum(valori_validi) / len(valori_validi)))

def media_lista_float(lista):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0.0
    return round(sum(valori_validi) / len(valori_validi), 1)

def conta_superamenti(lista, soglia):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return sum(1 for v in valori_validi if v >= soglia)

def percentuale_superamento(lista, soglia):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return (sum(1 for v in valori_validi if v >= soglia) / len(valori_validi)) * 100

def interpella_gemini(dati_testuali, oggi_str, domani_str):
    api_key = os.getenv("GEMINI_API_KEY")
    # Inizializzazione nuovo client SDK
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    Sei un meteorologo professionista. Il tuo compito è scrivere un bollettino discorsivo, fluido ed elegante per Rivoli (TO) partendo dalla sintesi oraria fornita.
    
    REGOLE FERREE (PENA IL FALLIMENTO):
    1. TITOLO: Inizia ESATTAMENTE con: <b>Aggiornamento meteo di {oggi_str}</b>
    2. STRUTTURA: Scrivi esattamente due paragrafi: il primo per la giornata odierna, il secondo per domani.
    3. DIVIETO ASSOLUTO DI ELENCARE GLI ORARI: NON elencare MAI le temperature ora per ora.
    4. SINTESI DISCORSIVA: Sintetizza l'evoluzione usando fasi del giorno ("in mattinata", "nelle ore centrali", "nel pomeriggio", "in serata").
    5. TEMPERATURE DA CITARE: Cita solo la temperatura minima e la temperatura massima prevista.
    6. DISAGIO TERMICO: Quando citi la temperatura massima, affianca ESATTAMENTE la dicitura sul disagio fornita nei dati.
    7. TERMINOLOGIA CIELO: Quando descrivi la nuvolosità, DEVI integrare nel testo ESATTAMENTE le stesse diciture fornite dai dati in minuscolo.
    8. PROBABILISMO SULLE PRECIPITAZIONI ESTIVE: In caso di instabilità, usa un tono probabilistico (es. "un aumento dell'instabilità con possibili rovesci (60%)"). Se ci sono più orari instabili, prendi la percentuale più alta e ignora gli altri.
    9. GESTIONE MALTEMPO INVERNALE/AUTUNNALE: Se nei dati trovi "Perturbazione in transito", NON usare la parola "instabilità" o le percentuali. Invece, aggrega le fasce orarie indicando quando piove/nevica, l'intensità media (debole, moderata, forte) e individua SEMPRE l'orario del picco massimo e quanti mm/h sono previsti, citandoli nel testo.
    10. DIVIETO ASSOLUTO DI FORMATTAZIONE MARKDOWN: Telegram va in crash con caratteri spaiati. NON USARE MAI asterischi (*), underscore (_) o formattazioni simili in nessun punto del testo. Usa solo testo pulito e il tag HTML <b> per il titolo.
    
    ESEMPIO DI STILE ESTIVO DA IMITARE:
    "La giornata di domenica si apre con stabilità atmosferica. Le minime si assestano sui 19°C. Durante le ore di luce il cielo si manterrà in prevalenza sereno, portando la massima a 33°C (disagio marcato 🟠). Nel tardo pomeriggio si segnala un aumento dell'instabilità con possibili rovesci o temporali (40%). In serata situazione in miglioramento."
    
    ESEMPIO DI STILE INVERNALE DA IMITARE:
    "La giornata odierna vedrà un progressivo peggioramento. Le temperature oscilleranno tra una minima di 4°C e una massima di 8°C (nessun disagio). Dal pomeriggio è atteso il transito di una perturbazione con piogge deboli, che si intensificheranno in serata divenendo moderate. Il picco massimo delle precipitazioni è atteso intorno alle 21:00 con circa 4.5 mm/h. La ventilazione si manterrà modesta umida orientale."

    DATI GIORNALIERI DA TRASFORMARE IN TESTO:
    {dati_testuali}
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.25)
        )
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    mese_corrente = datetime.now().month
    inverno = mese_corrente in [10, 11, 12, 1, 2, 3, 4]
    estate = mese_corrente in [5, 6, 7, 8, 9]
    
    FILE_LOCK = "lock_quotidiano.txt"
    oggi_str_lock = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi_str_lock:
                print("✅ Bollettino quotidiano già inviato oggi. Esecuzione terminata.")
                sys.exit(0)
    
    try:
        dati_det = scarica_dati_con_retry("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "wind_direction_10m,cape,sunshine_duration,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
            "daily": "sunrise,sunset",
            "models": "icon_d2",
            "timezone": "Europe/Rome", "forecast_days": 2
        })

        dati_eps_d2 = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m,apparent_temperature",
            "models": "icon_d2",
            "timezone": "Europe/Rome", "forecast_days": 2
        })
        
        ch2_disponibile = True
        try:
            dati_eps_ch2 = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "precipitation",
                "models": "meteoswiss_icon_ch2_ensemble",
                "timezone": "Europe/Rome", "forecast_days": 2
            })
            
            dati_det_ch2 = scarica_dati_con_retry("https://api.open-meteo.com/v1/forecast", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "sunshine_duration",
                "models": "meteoswiss_icon_ch2",
                "timezone": "Europe/Rome", "forecast_days": 2
            })
            
            if 'hourly' not in dati_eps_ch2 or 'hourly' not in dati_det_ch2:
                ch2_disponibile = False
        except:
            ch2_disponibile = False
            
    except Exception as e:
        print(f"❌ Errore fatale nel recupero dati Open-Meteo: {e}")
        return

    h_det = dati_det.get('hourly', {})
    h_eps_d2 = dati_eps_d2.get('hourly', {})
    h_eps_ch2 = dati_eps_ch2.get('hourly', {}) if ch2_disponibile else {}
    h_det_ch2 = dati_det_ch2.get('hourly', {}) if ch2_disponibile else {}
    orari = h_det.get('time', [])
    
    if not orari:
        print("❌ Errore: Dati orari non disponibili.")
        return
        
    sunrise_str = dati_det.get('daily', {}).get('sunrise', [])
    sunset_str = dati_det.get('daily', {}).get('sunset', [])

    medie_sole = {0: {'mattino': [], 'pomeriggio': []}, 1: {'mattino': [], 'pomeriggio': []}}
    for i in range(len(orari)):
        ora_dt = datetime.fromisoformat(orari[i])
        giorno_idx = 0 if i < 24 else 1
        alba = datetime.fromisoformat(sunrise_str[giorno_idx])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx])
        alba_piu_2 = alba + timedelta(hours=2)
        tramonto_meno_2 = tramonto - timedelta(hours=2)
        
        if ch2_disponibile and h_det_ch2.get('sunshine_duration'):
            sun_sec = h_det_ch2['sunshine_duration'][i]
        else:
            sun_sec = h_det.get('sunshine_duration', [])[i] if i < len(h_det.get('sunshine_duration', [])) else 0
            
        sun_minuti = (sun_sec or 0) / 60
        
        if alba_piu_2 <= ora_dt and ora_dt.hour < 13:
            medie_sole[giorno_idx]['mattino'].append(sun_minuti)
        elif ora_dt.hour >= 13 and ora_dt <= tramonto_meno_2:
            medie_sole[giorno_idx]['pomeriggio'].append(sun_minuti)

    for g in [0, 1]:
        for p in ['mattino', 'pomeriggio']:
            lst = medie_sole[g][p]
            medie_sole[g][p] = sum(lst) / len(lst) if lst else 0

    sintesi_oggi = []
    sintesi_domani = []
    t_min_oggi, t_max_oggi = 100, -100
    t_min_domani, t_max_domani = 100, -100
    apparent_temperatures_medie = []
    
    dew_point_prev = None
    w_gst_prev = None
    w_spd_prev = None
    ur_prev = None

    for i in range(len(orari)):
        ora_dt = datetime.fromisoformat(orari[i])
        ora_solare = ora_dt.hour
        giorno_idx = 0 if i < 24 else 1
        
        t_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('temperature_2m_member')]
        t_media = media_lista(t_membri)
        
        dew_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('dew_point_2m_member')]
        dew_media = media_lista(dew_membri)

        app_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('apparent_temperature_member')]
        app_media = media_lista(app_membri)
        apparent_temperatures_medie.append(app_media)
        
        ur_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('relative_humidity_2m_member')]
        ur_media = media_lista(ur_membri)
        
        w_spd_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('wind_speed_10m_member')]
        w_spd_media = media_lista(w_spd_membri)
        
        w_gst_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('wind_gusts_10m_member')]
        w_gst_media = media_lista(w_gst_membri)
        
        w_dir = h_det.get('wind_direction_10m', [])[i]
        w_dir_str = gradi_a_direzione(w_dir)
        
        prec_eps_d2_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('precipitation_member')]
        prec_eps_ch2_membri = [h_eps_ch2[k][i] for k in h_eps_ch2 if k.startswith('precipitation_member')] if ch2_disponibile else []
        prec_media_d2 = media_lista_float(prec_eps_d2_membri)
        
        pct_d2_1mm = percentuale_superamento(prec_eps_d2_membri, 1.0)
        pct_d2_3mm = percentuale_superamento(prec_eps_d2_membri, 3.0)
        pct_d2_5mm = percentuale_superamento(prec_eps_d2_membri, 5.0)
        num_d2_1mm = conta_superamenti(prec_eps_d2_membri, 1.0)
        
        instabilita = "assente"
        perturbazione = False
        probabilita = 0

        if estate:
            if ch2_disponibile:
                pct_ch2_1mm = percentuale_superamento(prec_eps_ch2_membri, 1.0)
                pct_ch2_3mm = percentuale_superamento(prec_eps_ch2_membri, 3.0)
                pct_ch2_5mm = percentuale_superamento(prec_eps_ch2_membri, 5.0)
                num_ch2_1mm = conta_superamenti(prec_eps_ch2_membri, 1.0)
                if num_d2_1mm >= 2 and num_ch2_1mm >= 2:
                    instabilita = "un aumento dell'instabilità"
                    if pct_d2_5mm >= 75 and pct_ch2_5mm >= 75: probabilita = 95
                    elif pct_d2_5mm >= 50 and pct_ch2_5mm >= 50: probabilita = 80
                    elif pct_d2_5mm >= 25 and pct_ch2_5mm >= 25: probabilita = 70
                    elif pct_d2_3mm >= 50 and pct_ch2_3mm >= 50: probabilita = 60
                    elif pct_d2_3mm >= 25 and pct_ch2_3mm >= 25: probabilita = 50
                    elif pct_d2_1mm >= 50 and pct_ch2_1mm >= 50: probabilita = 40
                    elif pct_d2_1mm >= 25 and pct_ch2_1mm >= 25: probabilita = 30
                    else: probabilita = 15
            else:
                if num_d2_1mm >= 3:
                    instabilita = "un aumento dell'instabilità"
                    if pct_d2_5mm >= 75: probabilita = 95
                    elif pct_d2_5mm >= 50: probabilita = 80
                    elif pct_d2_5mm >= 25: probabilita = 70
                    elif pct_d2_3mm >= 50: probabilita = 60
                    elif pct_d2_3mm >= 25: probabilita = 50
                    elif pct_d2_1mm >= 50: probabilita = 40
                    elif pct_d2_1mm >= 25: probabilita = 30
                    else: probabilita = 15
        elif inverno:
            if ch2_disponibile:
                pct_ch2_1mm = percentuale_superamento(prec_eps_ch2_membri, 1.0)
                if pct_d2_1mm >= 50 and pct_ch2_1mm >= 50:
                    perturbazione = True
            else:
                if pct_d2_1mm >= 75:
                    perturbazione = True

        tipo_prec = ""
        int_prec = ""
        
        if estate and instabilita != "assente":
            cape = h_det.get('cape', [])[i] if i < len(h_det.get('cape', [])) else 0
            if cape is None: cape = 0
            if cape > 200: tipo_prec = "rovesci o temporali"
            else: tipo_prec = "rovesci"
            
        elif inverno and perturbazione:
            if prec_media_d2 > 5: int_prec = "forti"
            elif prec_media_d2 >= 2: int_prec = "moderate"
            else: int_prec = "deboli"
            
            if t_media < 2:
                strati_quota = [
                    h_det.get('temperature_1000hPa', [])[i], h_det.get('temperature_975hPa', [])[i],
                    h_det.get('temperature_950hPa', [])[i], h_det.get('temperature_925hPa', [])[i],
                    h_det.get('temperature_900hPa', [])[i], h_det.get('temperature_850hPa', [])[i],
                    h_det.get('temperature_800hPa', [])[i]
                ]
                inversione_presente = any(t > 1 for t in strati_quota if t is not None)
                if inversione_presente:
                    if t_media > 0: tipo_prec = "piogge (per inversione termica in quota)"
                    else: tipo_prec = "PERICOLO PIOGGIA CONGELANTE (Gelicidio)"
                else: tipo_prec = "neve"
            else: tipo_prec = "piogge"

        vento_evento = ""
        silenzia_vento = (estate and instabilita != "assente")
        
        if not silenzia_vento:
            if w_gst_media >= 75 or w_spd_media >= 40: int_vento = "tempestosa"
            elif w_gst_media >= 55 or w_spd_media >= 30: int_vento = "forte"
            elif w_gst_media >= 40 or w_spd_media >= 20: int_vento = "modesta"
            else: int_vento = "blanda"

            if dew_point_prev is not None and w_gst_prev is not None and ur_prev is not None and w_spd_prev is not None:
                aumento_spd = w_spd_media - w_spd_prev
                aumento_vento = (w_gst_media - w_gst_prev) >= 20
                crollo_dew = (dew_point_prev - dew_media) >= 5
                aumento_ur = (ur_media - ur_prev) >= 5
                
                if aumento_spd < 5 and w_gst_media < 30:
                    pass 
                else:
                    is_fohn = w_dir_str in ['NW', 'N', 'W'] and aumento_vento and crollo_dew
                    is_oriente = w_dir_str in ['E', 'NE', 'SE'] and aumento_ur
                    
                    if is_fohn:
                        vento_evento = f"ventilazione {int_vento} da probabile Föhn"
                    elif is_oriente:
                        vento_evento = f"ventilazione {int_vento} umida orientale"
                    else:
                        vento_evento = f"ventilazione {int_vento}"
            else:
                if w_gst_media >= 30 or w_spd_media >= 15:
                    vento_evento = f"ventilazione {int_vento}"
                            
        dew_point_prev = dew_media
        w_gst_prev = w_gst_media
        w_spd_prev = w_spd_media
        ur_prev = ur_media

        alba = datetime.fromisoformat(sunrise_str[giorno_idx])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx])
        alba_piu_2 = alba + timedelta(hours=2)
        tramonto_meno_2 = tramonto - timedelta(hours=2)
        
        cielo = ""
        if alba_piu_2 <= ora_dt <= tramonto_meno_2:
            if ora_dt.hour < 13:
                avg_sun = medie_sole[giorno_idx]['mattino']
            else:
                avg_sun = medie_sole[giorno_idx]['pomeriggio']
                
            if avg_sun < 10: cielo = "molto nuvoloso o coperto"
            elif avg_sun <= 25: cielo = "irregolarmente o molto nuvoloso"
            elif avg_sun <= 40: cielo = "parzialmente o irregolarmente nuvoloso"
            elif avg_sun <= 50: cielo = "parzialmente nuvoloso"
            elif avg_sun <= 57: cielo = "poco nuvoloso"
            else: cielo = "sereno"

        nebbia = ""
        if abs(dew_media - t_media) <= 1 and ur_media >= 95 and w_spd_media < 10:
            nebbia = "possibile formazione di nebbia"

        if giorno_idx == 0:
            t_min_oggi = min(t_min_oggi, t_media)
            t_max_oggi = max(t_max_oggi, t_media)
        else:
            t_min_domani = min(t_min_domani, t_media)
            t_max_domani = max(t_max_domani, t_media)

        record = f"Ore {ora_solare}: T={t_media}°C."
        if cielo: record += f" cielo {cielo}."
        
        if estate and instabilita != "assente":
            if tipo_prec in ["rovesci", "rovesci o temporali"]:
                record += f" Si segnala {instabilita} con possibili {tipo_prec} ({probabilita}%)."
            else:
                record += f" Si segnala {instabilita} con rischio di {tipo_prec} ({probabilita}%)."
        elif inverno and perturbazione:
            record += f" Perturbazione in transito con {tipo_prec} {int_prec} (media {prec_media_d2} mm/h)."
                
        if vento_evento: record += f" {vento_evento}."
        if nebbia: record += f" {nebbia}."
        
        if giorno_idx == 0: sintesi_oggi.append(record)
        else: sintesi_domani.append(record)

    disagio_oggi = ""
    disagio_domani = ""
    
    if estate:
        dew_max_oggi = media_lista([h_eps_d2[k][14] for k in h_eps_d2 if k.startswith('dew_point_2m_member')])
        dew_max_domani = media_lista([h_eps_d2[k][14+24] for k in h_eps_d2 if k.startswith('dew_point_2m_member')])
        disagio_oggi = calcola_disagio_caldo(t_max_oggi, dew_max_oggi)
        disagio_domani = calcola_disagio_caldo(t_max_domani, dew_max_domani)
    elif inverno:
        windchill_min_oggi = min(apparent_temperatures_medie[0:24])
        windchill_min_domani = min(apparent_temperatures_medie[24:48])
        disagio_oggi = calcola_disagio_freddo(windchill_min_oggi)
        disagio_domani = calcola_disagio_freddo(windchill_min_domani)

    dt_oggi = datetime.now()
    dt_domani = dt_oggi + timedelta(days=1)
    oggi_str = formatta_data_it(dt_oggi)
    domani_str = formatta_data_it(dt_domani)

    testo_per_ia = f"""
    GIORNO 1: {oggi_str}
    - Temperatura Minima: {t_min_oggi}°C
    - Temperatura Massima: {t_max_oggi}°C {disagio_oggi}
    CRONISTORIA DEGLI EVENTI DA SINTETIZZARE:
    {chr(10).join(sintesi_oggi)}

    GIORNO 2: {domani_str}
    - Temperatura Minima: {t_min_domani}°C
    - Temperatura Massima: {t_max_domani}°C {disagio_domani}
    CRONISTORIA DEGLI EVENTI DA SINTETIZZARE:
    {chr(10).join(sintesi_domani)}
    """

    bollettino_finale = interpella_gemini(testo_per_ia, oggi_str, domani_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        # PARSE_MODE MODIFICATO IN HTML PER PREVENIRE CRASH DI FORMATTAZIONE
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "HTML"})
        if risposta_tg.status_code == 200:
            print("Bollettino inviato con successo!")
            with open(FILE_LOCK, "w") as f:
                f.write(oggi_str_lock)
        else:
            print(f"Errore Telegram: {risposta_tg.text}")
    else:
        print("Errore: Token o Chat ID mancanti! Stampo a video:")
        print("-------------------------------------------------")
        print(bollettino_finale)

if __name__ == "__main__":
    main()
