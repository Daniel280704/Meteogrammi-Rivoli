#!/usr/bin/env python3
import os
import sys
import time
import requests
from datetime import datetime, timedelta
from groq import Groq

LAT = 45.073443
LON = 7.543472

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

def interpella_groq(dati_testuali, oggi_str, giorni_str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "Errore: GROQ_API_KEY non trovata."
        
    client = Groq(api_key=api_key)
    
   prompt = f"""
    Sei un meteorologo professionista, esperto del microclima piemontese e della zona di Rivoli (TO). Il tuo compito è redigere un bollettino di tendenza a MEDIO TERMINE, elegante, fluido e coeso, analizzando la striscia di dati orari e gli estremi forniti per i tre giorni considerati.

    LINEE GUIDA PER L'ANALISI METEOROLOGICA (RAGIONA DA ESPERTO):
    1. Dinamiche delle Precipitazioni:
       - Instabilità Convettiva (Temporali di calore): Se noti piogge pomeridiane o serali repentine associate a CAPE > 150-200 J/kg, inquadra la tendenza come instabilità termo-convettiva. Usa un approccio probabilistico (es. "possibili spunti temporaleschi pomeridiani (40%)") prendendo come riferimento la percentuale massima (Prob) di quella fascia.
       - Perturbazioni Frontali (Maltempo strutturato): Se le precipitazioni coprono molte ore di fila con CAPE nullo, descrivi il passaggio del fronte perturbato, indicando in quale fase del giorno si concentreranno i fenomeni più intensi e indicando l'ora del picco con i relativi mm/h massimi rilevati.
2. Filtro della Ventilazione: Ignora completamente il vento se è debole. Segnalalo solo se le raffiche superano i 30 km/h o se noti dinamiche chiare di Föhn (vento forte da NW/N/W associato a un crollo del Dew Point e aria molto secca).
    3. Sintesi del Cielo: Esamina l'andamento dei minuti di soleggiamento orario (Sole) per ricavare un quadro d'insieme sull'evoluzione della copertura nuvolosa nel corso della giornata (es. da parzialmente nuvoloso a sereno), senza fare una cronistoria ora per ora.

    REGOLE DI STILE E DI COMPATTEZZA (FERREE):
    - TITOLO: Inizia l'output ESATTAMENTE con: <b>Aggiornamento meteo a medio termine di {oggi_str}</b>.
    - STRUTTURA: Scrivi esattamente tre paragrafi (un paragrafo per il primo giorno di estrazione, uno per il secondo, uno per il terzo). Lascia una riga vuota DOPO il titolo. È SEVERAMENTE VIETATO lasciare righe vuote tra un paragrafo e l'altro: vai semplicemente a capo per mantenere il testo del bollettino compatto ed elegante.
    - REQUISITO DELLE TEMPERATURE: All'interno di ciascun paragrafo, cita la temperatura minima e la temperatura massima previste. Accanto alla temperatura massima, aggiungi ESATTAMENTE la dicitura sul disagio termico con la relativa emoji che trovi nei dati di input (es. "(disagio marcato 🟠)" o "(disagio lieve da freddo ❄️)").
    - RIMOZIONE AUTOMATISMI ROBOTICI (PENA IL FALLIMENTO):
       * È SEVERAMENTE VIETATO generare espressioni ridondanti o cacofoniche come "nuvolosità parzialmente nuvolosa". Esprimiti in modo naturale (es. "il cielo si presenterà parzialmente nuvoloso", "nuvolosità irregolare", "spazi di sereno").
       * Se non piove, È VIETATO scrivere frasi meccaniche come "senza segnalazioni di precipitazioni significative" o "nessuna precipitazione prevista". Descrivi la giornata parlando di "contesto asciutto", "tempo stabile", oppure ometti del tutto il riferimento alla pioggia.
    - FORMATTAZIONE: Non usare MAI caratteri di formattazione Markdown (niente asterischi *, underscore _, o elenchi puntati). Usa solo testo pulito e il tag HTML <b> per il titolo.

    DATI GIORNALIERI DA ELABORARE:
    {dati_testuali}
    """
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.25,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Errore AI Groq: {e}"

def main():
    mese_corrente = datetime.now().month
    inverno = mese_corrente in [10, 11, 12, 1, 2, 3, 4]
    estate = mese_corrente in [5, 6, 7, 8, 9]
    
    FILE_LOCK = "lock_medio_termine.txt"
    oggi_str_lock = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi_str_lock:
                print("✅ Bollettino a medio termine già inviato oggi. Esecuzione terminata.")
                sys.exit(0)

    dt_oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dt_inizio_estrazione = dt_oggi + timedelta(days=2)
    dt_fine_estrazione = dt_oggi + timedelta(days=4)

    dati_det = {}
    dati_eps = {}
    usa_seamless = False

    try:
        dati_det = scarica_dati_con_retry("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "wind_direction_10m,cape,sunshine_duration,apparent_temperature,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
            "daily": "sunrise,sunset",
            "models": "meteoswiss_icon_ch2",
            "timezone": "Europe/Rome", 
            "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
            "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
        })

        dati_eps = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m,apparent_temperature",
            "models": "meteoswiss_icon_ch2_ensemble",
            "timezone": "Europe/Rome",
            "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
            "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
        })
        
        orari_temp = dati_det.get('hourly', {}).get('time', [])
        target_dt = dt_fine_estrazione + timedelta(hours=20)
        
        if not orari_temp or datetime.fromisoformat(orari_temp[-1]) < target_dt:
            usa_seamless = True
            
    except Exception as e:
        print(f"⚠️ Errore con ICON-CH2 (possibile timeout o server down): {e}. Fallback su SEAMLESS in corso...")
        usa_seamless = True

    if usa_seamless:
        try:
            print("⚠️ Procedo con ICON-SEAMLESS...")
            dati_det = scarica_dati_con_retry("https://api.open-meteo.com/v1/forecast", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "wind_direction_10m,cape,sunshine_duration,apparent_temperature,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
                "daily": "sunrise,sunset",
                "models": "icon_seamless",
                "timezone": "Europe/Rome", 
                "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
                "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
            })

            dati_eps = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m,apparent_temperature",
                "models": "icon_seamless",
                "timezone": "Europe/Rome",
                "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
                "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
            })
        except Exception as e:
            print(f"❌ Errore fatale nel recupero dati Open-Meteo (Seamless fallito): {e}")
            return

    h_det = dati_det.get('hourly', {})
    h_eps = dati_eps.get('hourly', {})
    orari = h_det.get('time', [])
    
    if not orari:
        print("Errore: Nessun dato restituito dai server per il modello selezionato.")
        return

    sunrise_str = dati_det.get('daily', {}).get('sunrise', [])
    sunset_str = dati_det.get('daily', {}).get('sunset', [])

    medie_sole = {2: {'mattino': [], 'pomeriggio': []}, 
                  3: {'mattino': [], 'pomeriggio': []}, 
                  4: {'mattino': [], 'pomeriggio': []}}
                  
    indici_validi = []
    
    for i, t_str in enumerate(orari):
        ora_dt = datetime.fromisoformat(t_str)
        giorno_idx = (ora_dt.date() - dt_oggi.date()).days
        
        if giorno_idx == 4 and ora_dt.hour > 20:
            continue
            
        indici_validi.append(i)
        
        if giorno_idx not in medie_sole:
            continue
            
        alba = datetime.fromisoformat(sunrise_str[giorno_idx - 2])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx - 2])
        alba_piu_2 = alba + timedelta(hours=2)
        tramonto_meno_2 = tramonto - timedelta(hours=2)
        
        sun_sec = h_det.get('sunshine_duration', [])[i] if i < len(h_det.get('sunshine_duration', [])) else None
        sun_minuti = (sun_sec or 0) / 60
        
        if alba_piu_2 <= ora_dt and ora_dt.hour < 13:
            medie_sole[giorno_idx]['mattino'].append(sun_minuti)
        elif ora_dt.hour >= 13 and ora_dt <= tramonto_meno_2:
            medie_sole[giorno_idx]['pomeriggio'].append(sun_minuti)

    for g in medie_sole:
        for p in ['mattino', 'pomeriggio']:
            lst = medie_sole[g][p]
            medie_sole[g][p] = sum(lst) / len(lst) if lst else 0

    sintesi = {2: [], 3: [], 4: []}
    t_min = {2: 100, 3: 100, 4: 100}
    t_max = {2: -100, 3: -100, 4: -100}
    dew_max = {2: -100, 3: -100, 4: -100}
    windchill_min = {2: 100, 3: 100, 4: 100}
    
    dew_point_prev = None
    w_gst_prev = None
    w_spd_prev = None
    ur_prev = None
    
    if len(orari) > 0 and indici_validi:
        primo_idx = indici_validi[0]
        if primo_idx > 0:
            dew_membri_prev = [h_eps[k][primo_idx - 1] for k in h_eps if k.startswith('dew_point_2m_member')]
            dew_point_prev = media_lista(dew_membri_prev)
            
            gst_membri_prev = [h_eps[k][primo_idx - 1] for k in h_eps if k.startswith('wind_gusts_10m_member')]
            w_gst_prev = media_lista(gst_membri_prev)
            
            spd_membri_prev = [h_eps[k][primo_idx - 1] for k in h_eps if k.startswith('wind_speed_10m_member')]
            w_spd_prev = media_lista(spd_membri_prev)
            
            ur_membri_prev = [h_eps[k][primo_idx - 1] for k in h_eps if k.startswith('relative_humidity_2m_member')]
            ur_prev = media_lista(ur_membri_prev)

    for i in indici_validi:
        ora_dt = datetime.fromisoformat(orari[i])
        ora_solare = ora_dt.hour
        giorno_idx = (ora_dt.date() - dt_oggi.date()).days
        
        t_membri = [h_eps[k][i] for k in h_eps if k.startswith('temperature_2m_member')]
        t_media = media_lista(t_membri)
        
        dew_membri = [h_eps[k][i] for k in h_eps if k.startswith('dew_point_2m_member')]
        dew_media = media_lista(dew_membri)

        app_membri = [h_eps[k][i] for k in h_eps if k.startswith('apparent_temperature_member')]
        app_media = media_lista(app_membri)
        
        ur_membri = [h_eps[k][i] for k in h_eps if k.startswith('relative_humidity_2m_member')]
        ur_media = media_lista(ur_membri)
        
        w_spd_membri = [h_eps[k][i] for k in h_eps if k.startswith('wind_speed_10m_member')]
        w_spd_media = media_lista(w_spd_membri)
        
        w_gst_membri = [h_eps[k][i] for k in h_eps if k.startswith('wind_gusts_10m_member')]
        w_gst_media = media_lista(w_gst_membri)
        
        w_dir = h_det.get('wind_direction_10m', [])[i] if i < len(h_det.get('wind_direction_10m', [])) else None
        w_dir_str = gradi_a_direzione(w_dir)
        
        prec_eps_membri = [h_eps[k][i] for k in h_eps if k.startswith('precipitation_member')]
        prec_media_eps = media_lista_float(prec_eps_membri)
        
        pct_1mm = percentuale_superamento(prec_eps_membri, 1.0)
        pct_3mm = percentuale_superamento(prec_eps_membri, 3.0)
        pct_5mm = percentuale_superamento(prec_eps_membri, 5.0)
        num_1mm = conta_superamenti(prec_eps_membri, 1.0)
        
        instabilita = "assente"
        perturbazione = False
        probabilita = 0

        if estate:
            if num_1mm >= 3:
                instabilita = "un aumento dell'instabilità"
                if pct_5mm >= 75: probabilita = 95
                elif pct_5mm >= 50: probabilita = 80
                elif pct_5mm >= 25: probabilita = 70
                elif pct_3mm >= 50: probabilita = 60
                elif pct_3mm >= 25: probabilita = 50
                elif pct_1mm >= 50: probabilita = 40
                elif pct_1mm >= 25: probabilita = 30
                else: probabilita = 15
        elif inverno:
            if pct_1mm >= 75:
                perturbazione = True

        tipo_prec = ""
        int_prec = ""
        
        if estate and instabilita != "assente":
            cape = h_det.get('cape', [])[i] if i < len(h_det.get('cape', [])) else 0
            if cape is None: cape = 0
            if cape > 200: tipo_prec = "rovesci o temporali"
            else: tipo_prec = "rovesci"
            
        elif inverno and perturbazione:
            if prec_media_eps > 5: int_prec = "forti"
            elif prec_media_eps >= 2: int_prec = "moderate"
            else: int_prec = "deboli"
            
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
                    
                    if is_fohn and int_vento not in ["blanda", "modesta"]:
                        vento_evento = f"ventilazione {int_vento} da probabile Föhn"
                    elif is_oriente and int_vento not in ["blanda", "modesta"]:
                        vento_evento = f"ventilazione {int_vento} umida orientale"
                    elif int_vento not in ["blanda", "modesta"]:
                        vento_evento = f"ventilazione {int_vento}"
            else:
                if int_vento not in ["blanda", "modesta"]:
                    vento_evento = f"ventilazione {int_vento}"
                            
        dew_point_prev = dew_media
        w_gst_prev = w_gst_media
        w_spd_prev = w_spd_media
        ur_prev = ur_media

        alba = datetime.fromisoformat(sunrise_str[giorno_idx - 2])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx - 2])
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

        t_min[giorno_idx] = min(t_min[giorno_idx], t_media)
        t_max[giorno_idx] = max(t_max[giorno_idx], t_media)
        if estate: 
            dew_max[giorno_idx] = max(dew_max[giorno_idx], dew_media)
        elif inverno:
            windchill_min[giorno_idx] = min(windchill_min[giorno_idx], app_media)

        record = f"Ore {ora_solare}: T={t_media}°C."
        if cielo: record += f" cielo {cielo}."
        
        if estate and instabilita != "assente":
            if tipo_prec in ["rovesci", "rovesci o temporali"]:
                record += f" Si segnala {instabilita} con possibili {tipo_prec} ({probabilita}%)."
            else:
                record += f" Si segnala {instabilita} con rischio di {tipo_prec} ({probabilita}%)."
        elif inverno and perturbazione:
            record += f" Perturbazione in transito con {tipo_prec} {int_prec} (media {prec_media_eps} mm/h)."
                
        if vento_evento: record += f" {vento_evento}."
        if nebbia: record += f" {nebbia}."
        
        sintesi[giorno_idx].append(record)

    disagio = {2: "", 3: "", 4: ""}
    for g in [2, 3, 4]:
        if estate and t_max[g] != -100:
            disagio[g] = calcola_disagio_caldo(t_max[g], dew_max[g])
        elif inverno and windchill_min[g] != 100:
            disagio[g] = calcola_disagio_freddo(windchill_min[g])

    oggi_str = formatta_data_it(dt_oggi)
    
    giorni_str = {
        2: formatta_data_it(dt_oggi + timedelta(days=2)),
        3: formatta_data_it(dt_oggi + timedelta(days=3)),
        4: formatta_data_it(dt_oggi + timedelta(days=4))
    }

    testo_per_ia = ""
    for g in [2, 3, 4]:
        if not sintesi[g]: continue
        testo_per_ia += f"GIORNO: {giorni_str[g]}\n"
        testo_per_ia += f"- Temperatura Minima: {t_min[g]}°C\n"
        testo_per_ia += f"- Temperatura Massima: {t_max[g]}°C {disagio[g]}\n"
        testo_per_ia += "CRONISTORIA DEGLI EVENTI:\n"
        testo_per_ia += "\n".join(sintesi[g]) + "\n\n"

    bollettino_finale = interpella_groq(testo_per_ia, oggi_str, giorni_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "HTML"})
        if risposta_tg.status_code == 200:
            print("Bollettino a medio termine inviato con successo!")
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
