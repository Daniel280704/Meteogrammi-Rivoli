#!/usr/bin/env python3
import os
import sys
import time
import requests
from datetime import datetime, timedelta
from groq import Groq

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

def ottieni_fascia_oraria(ora):
    if 0 <= ora < 6: return "notte"
    elif 6 <= ora < 10: return "prima parte della mattinata"
    elif 10 <= ora < 13: return "tarda mattinata"
    elif 13 <= ora < 17: return "pomeriggio"
    elif 17 <= ora < 19: return "tardo pomeriggio"
    elif 19 <= ora < 22: return "sera"
    else: return "tarda serata"

def gradi_a_direzione(gradi):
    if gradi is None: return "N/A"
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'N']
    return dirs[int(round(gradi / 45.0)) % 8]

def calcola_disagio_caldo(t_aria, dew_point):
    if t_aria >= 40 and dew_point >= 15: return ("(disagio estremo 🟣)", 4)
    elif t_aria >= 38 and dew_point >= 18: return ("(disagio estremo 🟣)", 4)
    elif t_aria >= 36 and dew_point >= 20: return ("(disagio estremo 🟣)", 4)
    elif t_aria >= 34 and dew_point >= 22: return ("(disagio estremo 🟣)", 4)
    elif t_aria >= 32 and dew_point >= 24: return ("(disagio estremo 🟣)", 4)
    elif t_aria >= 30 and dew_point >= 25: return ("(disagio estremo 🟣)", 4)
    elif t_aria >= 28 and dew_point >= 26: return ("(disagio estremo 🟣)", 4)
    
    elif t_aria >= 38 and dew_point >= 12: return ("(disagio forte 🔴)", 3)
    elif t_aria >= 36 and dew_point >= 15: return ("(disagio forte 🔴)", 3)
    elif t_aria >= 34 and dew_point >= 18: return ("(disagio forte 🔴)", 3)
    elif t_aria >= 32 and dew_point >= 20: return ("(disagio forte 🔴)", 3)
    elif t_aria >= 30 and dew_point >= 22: return ("(disagio forte 🔴)", 3)
    elif t_aria >= 28 and dew_point >= 24: return ("(disagio forte 🔴)", 3)
    elif t_aria >= 26 and dew_point >= 25: return ("(disagio forte 🔴)", 3)
    
    elif t_aria >= 36 and dew_point >= 10: return ("(disagio marcato 🟠)", 2)
    elif t_aria >= 34 and dew_point >= 13: return ("(disagio marcato 🟠)", 2)
    elif t_aria >= 32 and dew_point >= 16: return ("(disagio marcato 🟠)", 2)
    elif t_aria >= 30 and dew_point >= 18: return ("(disagio marcato 🟠)", 2)
    elif t_aria >= 28 and dew_point >= 20: return ("(disagio marcato 🟠)", 2)
    elif t_aria >= 26 and dew_point >= 22: return ("(disagio marcato 🟠)", 2)
    elif t_aria >= 24 and dew_point >= 24: return ("(disagio marcato 🟠)", 2)
    
    elif t_aria >= 32 and dew_point >= 8: return ("(disagio lieve 🟡)", 1)
    elif t_aria >= 30 and dew_point >= 11: return ("(disagio lieve 🟡)", 1)
    elif t_aria >= 28 and dew_point >= 13: return ("(disagio lieve 🟡)", 1)
    elif t_aria >= 26 and dew_point >= 15: return ("(disagio lieve 🟡)", 1)
    elif t_aria >= 24 and dew_point >= 17: return ("(disagio lieve 🟡)", 1)
    elif t_aria >= 22 and dew_point >= 19: return ("(disagio lieve 🟡)", 1)
    
    else:
        return ("(nessun disagio o caldo tollerabile 🟢)", 0)

def calcola_disagio_freddo(windchill):
    if windchill < -40: return ("(disagio estremo da freddo 🥶)", 4)
    elif windchill < -25: return ("(disagio forte da freddo 🥶)", 3)
    elif windchill < -10: return ("(disagio marcato da freddo 🥶)", 2)
    elif windchill < 0: return ("(disagio lieve da freddo 🥶)", 1)
    else:
        return ("(nessun disagio o freddo tollerabile 🟢)", 0)

def media_lista(lista):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return int(round(sum(valori_validi) / len(valori_validi)))

def media_lista_float(lista):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0.0
    return round(sum(valori_validi) / len(valori_validi), 1)

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
    Sei un meteorologo professionista. Il tuo compito è scrivere un bollettino discorsivo, fluido ed elegante per Rivoli (TO) a MEDIO TERMINE.
    Ti fornirò un elenco dei "fatti salienti" già calcolati e processati (picchi, orari, soglie superate). Il tuo compito è trasformare questi appunti in un testo discorsivo.
    
    REGOLE FERREE (PENA IL FALLIMENTO):
    1. TITOLO E IMPAGINAZIONE: Inizia ESATTAMENTE con: <b>Aggiornamento meteo a medio termine di {oggi_str}</b>. Lascia una riga vuota tra il titolo e il primo paragrafo.
    2. STRUTTURA: Scrivi tre paragrafi: il primo per {giorni_str[2]}, il secondo per {giorni_str[3]}, il terzo per {giorni_str[4]}. Non usare righe vuote tra i paragrafi.
    3. NO ELENCHI PUNTATI: Trasforma le informazioni in frasi continue. È vietato fare liste.
    4. CITA I DATI PRE-CALCOLATI: Usa fedelmente le fasce orarie che ti fornisco nei dati (es. "nella prima parte della mattinata", "nel tardo pomeriggio"). 
    5. NON INVENTARE: Non dedurre orari o condizioni diverse da quelle scritte. Se l'anomalia oraria di una temperatura è segnalata, menzionala ("raggiunta insolitamente in...").
    6. DISAGIO TERMICO: Includi sempre la stringa del disagio termico fornita (compresa l'emoji) quando parli del momento di maggior afa/freddo.
    7. FLUIDITÀ SULLA NUVOLOSITÀ: È SEVERAMENTE VIETATO generare cacofonie come "la nuvolosità sarà parzialmente nuvolosa". Usa "il cielo si presenterà...", "avremo cieli...", "copertura nuvolosa...".
    8. PRECIPITAZIONI: Riporta fluidamente le probabilità di precipitazione fornite, l'orario di inizio, il picco e la fine esatta indicata.
    9. DIVIETO ASSOLUTO DI FORMATTAZIONE MARKDOWN: NON USARE MAI asterischi (*) o underscore (_). Usa solo testo pulito e il tag HTML <b> per il titolo.
    10. SILENZIO SUI FENOMENI ASSENTI: NON menzionare MAI l'assenza di fenomeni (vento, precipitazioni, gelate). Parla SOLO di ciò che ti viene fornito.
    
    DATI SINTETIZZATI DA TRASFORMARE IN TESTO:
    {dati_testuali}
    """
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
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
        print(f"⚠️ Errore ICON-CH2: {e}. Fallback su SEAMLESS in corso...")
        usa_seamless = True

    if usa_seamless:
        try:
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
            print(f"❌ Errore fatale Seamless: {e}")
            return

    h_det = dati_det.get('hourly', {})
    h_eps = dati_eps.get('hourly', {})
    orari = h_det.get('time', [])
    if not orari: return

    sunrise_str = dati_det.get('daily', {}).get('sunrise', [])
    sunset_str = dati_det.get('daily', {}).get('sunset', [])

    medie_sole = {2: {'mattino': [], 'pomeriggio': []}, 3: {'mattino': [], 'pomeriggio': []}, 4: {'mattino': [], 'pomeriggio': []}}
    indici_validi = []
    
    for i, t_str in enumerate(orari):
        ora_dt = datetime.fromisoformat(t_str)
        giorno_idx = (ora_dt.date() - dt_oggi.date()).days
        if giorno_idx == 4 and ora_dt.hour > 20: continue
        indici_validi.append(i)
        
        if giorno_idx not in medie_sole: continue
        alba = datetime.fromisoformat(sunrise_str[giorno_idx - 2])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx - 2])
        alba_piu_2 = alba + timedelta(hours=2)
        tramonto_meno_2 = tramonto - timedelta(hours=2)
        
        sun_sec = h_det.get('sunshine_duration', [])[i] if i < len(h_det.get('sunshine_duration', [])) else None
        sun_minuti = (sun_sec or 0) / 60
        if alba_piu_2 <= ora_dt and ora_dt.hour < 13: medie_sole[giorno_idx]['mattino'].append(sun_minuti)
        elif ora_dt.hour >= 13 and ora_dt <= tramonto_meno_2: medie_sole[giorno_idx]['pomeriggio'].append(sun_minuti)

    for g in medie_sole:
        for p in ['mattino', 'pomeriggio']:
            lst = medie_sole[g][p]
            medie_sole[g][p] = sum(lst) / len(lst) if lst else 0

    dati_giorni = {g: {
        't_min': 100, 'ora_t_min': None,
        't_max': -100, 'ora_t_max': None,
        'livello_disagio_max': -1, 'stringa_disagio': "", 'ora_disagio_max': None,
        'w_gst_max': -1, 'ora_w_gst_max': None, 'vento_intensificato': False, 'tipo_vento': "",
        'ha_precip': False, 'ora_inizio_p': None, 'ora_fine_p': None, 'picco_p_mm': -1, 'ora_picco_p': None, 'prob_max_p': 0, 'tipo_p': "",
        'cielo_mattino': "", 'cielo_pomeriggio': "",
        'gelate': set(), 'nebbie': set()
    } for g in [2, 3, 4]}

    dew_point_prev = None
    w_gst_prev = None
    ur_prev = None

    if indici_validi and indici_validi[0] > 0:
        primo_idx = indici_validi[0]
        dew_point_prev = media_lista([h_eps[k][primo_idx - 1] for k in h_eps if k.startswith('dew_point_2m_member')])
        w_gst_prev = media_lista([h_eps[k][primo_idx - 1] for k in h_eps if k.startswith('wind_gusts_10m_member')])
        ur_prev = media_lista([h_eps[k][primo_idx - 1] for k in h_eps if k.startswith('relative_humidity_2m_member')])

    for i in indici_validi:
        ora_dt = datetime.fromisoformat(orari[i])
        ora_solare = ora_dt.hour
        giorno_idx = (ora_dt.date() - dt_oggi.date()).days
        if giorno_idx not in dati_giorni: continue
        
        g_data = dati_giorni[giorno_idx]
        
        t_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('temperature_2m_member')])
        dew_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('dew_point_2m_member')])
        app_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('apparent_temperature_member')])
        ur_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('relative_humidity_2m_member')])
        w_spd_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('wind_speed_10m_member')])
        w_gst_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('wind_gusts_10m_member')])
        
        w_dir = h_det.get('wind_direction_10m', [])[i] if i < len(h_det.get('wind_direction_10m', [])) else None
        w_dir_str = gradi_a_direzione(w_dir)
        cape = h_det.get('cape', [])[i] if i < len(h_det.get('cape', [])) else 0
        if cape is None: cape = 0
        
        prec_eps_membri = [h_eps[k][i] for k in h_eps if k.startswith('precipitation_member')]
        prec_media_eps = media_lista_float(prec_eps_membri)
        pct_1mm = percentuale_superamento(prec_eps_membri, 1.0)
        
        # --- TEMPERATURE ---
        if t_media < g_data['t_min']:
            g_data['t_min'] = t_media
            g_data['ora_t_min'] = ora_solare
        if t_media > g_data['t_max']:
            g_data['t_max'] = t_media
            g_data['ora_t_max'] = ora_solare
            
        # --- DISAGIO ORA PER ORA ---
        if estate:
            str_dis, liv_dis = calcola_disagio_caldo(t_media, dew_media)
        else:
            str_dis, liv_dis = calcola_disagio_freddo(app_media)
            
        if liv_dis > g_data['livello_disagio_max']:
            g_data['livello_disagio_max'] = liv_dis
            g_data['stringa_disagio'] = str_dis
            g_data['ora_disagio_max'] = ora_solare

        # --- VENTO ---
        if w_gst_media > g_data['w_gst_max']:
            g_data['w_gst_max'] = w_gst_media
            g_data['ora_w_gst_max'] = ora_solare
            
        if w_gst_prev is not None:
            if (w_gst_media - w_gst_prev) >= 10:
                g_data['vento_intensificato'] = True
                
            if w_dir_str in ['NW', 'N', 'W'] and ((w_gst_media - w_gst_prev) >= 10 or w_gst_media >= 30) and ((dew_point_prev - dew_media) >= 1 or ur_media < 40):
                g_data['tipo_vento'] = "per condizioni di Föhn"
            elif w_dir_str in ['E', 'NE', 'SE'] and ((w_gst_media - w_gst_prev) >= 10 or w_gst_media >= 30) and ur_media > 40:
                g_data['tipo_vento'] = "umida orientale"
                
        # --- PRECIPITAZIONI ---
        is_instabilita_estiva = (estate and cape > 200)
        prob_soglia = 15 if is_instabilita_estiva else 50
        
        if pct_1mm >= prob_soglia:
            g_data['ha_precip'] = True
            if g_data['ora_inizio_p'] is None:
                g_data['ora_inizio_p'] = ora_solare
            g_data['ora_fine_p'] = ora_solare 
            
            # Traccia la probabilità massima oraria raggiunta durante l'evento
            if pct_1mm > g_data['prob_max_p']:
                g_data['prob_max_p'] = int(round(pct_1mm))
                
            if prec_media_eps >= g_data['picco_p_mm']: 
                g_data['picco_p_mm'] = prec_media_eps
                g_data['ora_picco_p'] = ora_solare
                
                if is_instabilita_estiva:
                    g_data['tipo_p'] = "rovesci o temporali"
                elif estate:
                    g_data['tipo_p'] = "rovesci"
                else:
                    if t_media < 2:
                        strati_quota = [
                            h_det.get('temperature_1000hPa', [])[i] if i < len(h_det.get('temperature_1000hPa', [])) else None,
                            h_det.get('temperature_850hPa', [])[i] if i < len(h_det.get('temperature_850hPa', [])) else None
                        ]
                        inv = any(t > 1 for t in strati_quota if t is not None)
                        if inv:
                            g_data['tipo_p'] = "piogge (per inversione in quota)" if t_media > 0 else "PERICOLO PIOGGIA CONGELANTE"
                        else: g_data['tipo_p'] = "neve"
                    else:
                        g_data['tipo_p'] = "piogge"

        # --- NEBBIA E GELO ---
        if abs(dew_media - t_media) <= 1 and ur_media >= 95 and w_spd_media < 10:
            g_data['nebbie'].add(ottieni_fascia_oraria(ora_solare))
            
        if ora_solare >= 22 or ora_solare <= 8:
            if t_media <= -4 and ur_media >= 50: g_data['gelate'].add(f"forti gelate in {ottieni_fascia_oraria(ora_solare)}")
            elif -4 < t_media <= -1 and ur_media >= 60: g_data['gelate'].add(f"gelate diffuse in {ottieni_fascia_oraria(ora_solare)}")
            elif -1 < t_media <= 1 and t_media <= 0 and ur_media >= 55: g_data['gelate'].add(f"lievi gelate in {ottieni_fascia_oraria(ora_solare)}")

        dew_point_prev = dew_media
        w_gst_prev = w_gst_media
        ur_prev = ur_media
        
    for g in [2, 3, 4]:
        for fascia in ['mattino', 'pomeriggio']:
            avg_sun = medie_sole[g][fascia]
            cielo = ""
            if avg_sun < 10: cielo = "molto nuvoloso o coperto"
            elif avg_sun <= 25: cielo = "irregolarmente o molto nuvoloso"
            elif avg_sun <= 40: cielo = "parzialmente o irregolarmente nuvoloso"
            elif avg_sun <= 50: cielo = "parzialmente nuvoloso"
            elif avg_sun <= 57: cielo = "poco nuvoloso"
            else: cielo = "sereno"
            dati_giorni[g][f'cielo_{fascia}'] = cielo

    oggi_str = formatta_data_it(dt_oggi)
    giorni_str = {
        2: formatta_data_it(dt_oggi + timedelta(days=2)),
        3: formatta_data_it(dt_oggi + timedelta(days=3)),
        4: formatta_data_it(dt_oggi + timedelta(days=4))
    }

    testo_per_ia = ""
    for g in [2, 3, 4]:
        dg = dati_giorni[g]
        testo_per_ia += f"GIORNO: {giorni_str[g]}\n"
        
        testo_per_ia += f"- Temp Minima: {dg['t_min']}°C"
        if dg['ora_t_min'] is not None and dg['ora_t_min'] >= 10:
            testo_per_ia += f" (raggiunta insolitamente in {ottieni_fascia_oraria(dg['ora_t_min'])})\n"
        else: testo_per_ia += "\n"
            
        testo_per_ia += f"- Temp Massima: {dg['t_max']}°C"
        if dg['ora_t_max'] is not None and (dg['ora_t_max'] < 13 or dg['ora_t_max'] >= 19):
            testo_per_ia += f" (raggiunta insolitamente in {ottieni_fascia_oraria(dg['ora_t_max'])})\n"
        else: testo_per_ia += "\n"
        
        if dg['livello_disagio_max'] > 0:
            testo_per_ia += f"- Picco di disagio termico: {dg['stringa_disagio']} registrato in {ottieni_fascia_oraria(dg['ora_disagio_max'])}\n"
            
        testo_per_ia += f"- Cielo prevalente al mattino: {dg['cielo_mattino']}\n"
        testo_per_ia += f"- Cielo prevalente al pomeriggio: {dg['cielo_pomeriggio']}\n"
        
        if dg['ha_precip']:
            testo_per_ia += f"- Precipitazioni: previsti {dg['tipo_p']} con una probabilità massima stimata del {dg['prob_max_p']}%.\n"
            testo_per_ia += f"  Inizio precipitazioni in {ottieni_fascia_oraria(dg['ora_inizio_p'])}, termine in {ottieni_fascia_oraria(dg['ora_fine_p'])}.\n"
            
            int_prec = "deboli"
            if dg['picco_p_mm'] > 5: int_prec = "forti"
            elif dg['picco_p_mm'] >= 2: int_prec = "moderate"
            testo_per_ia += f"  Intensità massima stimata come {int_prec} (circa {dg['picco_p_mm']} mm/h) con picco in {ottieni_fascia_oraria(dg['ora_picco_p'])}.\n"
            
        if dg['w_gst_max'] >= 30:
            int_vento = "modesta"
            if dg['w_gst_max'] >= 70: int_vento = "tempestosa"
            elif dg['w_gst_max'] >= 50: int_vento = "forte"
            
            txt_vento = f"- Vento: ventilazione {int_vento} {dg['tipo_vento']}. Raffiche massime previste in {ottieni_fascia_oraria(dg['ora_w_gst_max'])}."
            if dg['vento_intensificato']: txt_vento += " Si segnala una netta intensificazione delle correnti nel corso di quelle ore."
            testo_per_ia += txt_vento + "\n"
            
        if dg['gelate']: testo_per_ia += f"- Pericolo gelo: {', '.join(dg['gelate'])}\n"
        if dg['nebbie']: testo_per_ia += f"- Rischio nebbia nelle seguenti fasce orarie: {', '.join(dg['nebbie'])}\n"
        
        testo_per_ia += "\n"

    bollettino_finale = interpella_groq(testo_per_ia, oggi_str, giorni_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        if bollettino_finale.startswith("Errore"):
            print(f"Blocco l'invio su Telegram a causa di un errore API: {bollettino_finale}")
        else:
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
