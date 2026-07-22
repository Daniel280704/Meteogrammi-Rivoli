#!/usr/bin/env python3
import os
import sys
import time
import math
import requests
from collections import Counter
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
            print(f"⚠️ Errore connessione (Tentativo {tentativo + 1}/{max_retries}): {e}")
            if tentativo < max_retries - 1: time.sleep(10)
            else: raise e

def scarica_sicuro(url, params):
    try: return scarica_dati_con_retry(url, params)
    except Exception as e:
        print(f"⚠️ Fallito download per {params.get('models', 'Sconosciuto')}: {e}")
        return {}

def formatta_data_it(dt):
    return f"{GIORNI_IT[dt.weekday()]} {dt.day} {MESI_IT[dt.month]}"

def get_avg_arrays(*arrays):
    valid_arrays = [a for a in arrays if a and isinstance(a, list) and len(a) > 0]
    if not valid_arrays: return []
    max_len = max(len(a) for a in valid_arrays)
    result = []
    for i in range(max_len):
        vals = [a[i] for a in valid_arrays if i < len(a) and a[i] is not None]
        if vals: result.append(sum(vals) / len(vals))
        else: result.append(0.0)
    return result

def avg_wind_dir_arrays(*arrays):
    valid_arrays = [a for a in arrays if a and isinstance(a, list) and len(a) > 0]
    if not valid_arrays: return []
    max_len = max(len(a) for a in valid_arrays)
    result = []
    for i in range(max_len):
        vals = [a[i] for a in valid_arrays if i < len(a) and a[i] is not None]
        if not vals: result.append(0)
        else:
            u = sum(math.sin(math.radians(v)) for v in vals)
            v = sum(math.cos(math.radians(v)) for v in vals)
            result.append((math.degrees(math.atan2(u, v)) + 360) % 360)
    return result

def get_disagio_caldo(t_aria, dew_point):
    if t_aria >= 40 and dew_point >= 15: return 4, "(disagio estremo 🟣)"
    elif t_aria >= 38 and dew_point >= 18: return 4, "(disagio estremo 🟣)"
    elif t_aria >= 36 and dew_point >= 20: return 4, "(disagio estremo 🟣)"
    elif t_aria >= 34 and dew_point >= 22: return 4, "(disagio estremo 🟣)"
    elif t_aria >= 32 and dew_point >= 24: return 4, "(disagio estremo 🟣)"
    elif t_aria >= 30 and dew_point >= 25: return 4, "(disagio estremo 🟣)"
    elif t_aria >= 28 and dew_point >= 26: return 4, "(disagio estremo 🟣)"
    elif t_aria >= 38 and dew_point >= 12: return 3, "(disagio forte 🔴)"
    elif t_aria >= 36 and dew_point >= 15: return 3, "(disagio forte 🔴)"
    elif t_aria >= 34 and dew_point >= 18: return 3, "(disagio forte 🔴)"
    elif t_aria >= 32 and dew_point >= 20: return 3, "(disagio forte 🔴)"
    elif t_aria >= 30 and dew_point >= 22: return 3, "(disagio forte 🔴)"
    elif t_aria >= 28 and dew_point >= 24: return 3, "(disagio forte 🔴)"
    elif t_aria >= 26 and dew_point >= 25: return 3, "(disagio forte 🔴)"
    elif t_aria >= 36 and dew_point >= 10: return 2, "(disagio marcato 🟠)"
    elif t_aria >= 34 and dew_point >= 13: return 2, "(disagio marcato 🟠)"
    elif t_aria >= 32 and dew_point >= 16: return 2, "(disagio marcato 🟠)"
    elif t_aria >= 30 and dew_point >= 18: return 2, "(disagio marcato 🟠)"
    elif t_aria >= 28 and dew_point >= 20: return 2, "(disagio marcato 🟠)"
    elif t_aria >= 26 and dew_point >= 22: return 2, "(disagio marcato 🟠)"
    elif t_aria >= 24 and dew_point >= 24: return 2, "(disagio marcato 🟠)"
    elif t_aria >= 32 and dew_point >= 8:  return 1, "(disagio lieve 🟡)"
    elif t_aria >= 30 and dew_point >= 11: return 1, "(disagio lieve 🟡)"
    elif t_aria >= 28 and dew_point >= 13: return 1, "(disagio lieve 🟡)"
    elif t_aria >= 26 and dew_point >= 15: return 1, "(disagio lieve 🟡)"
    elif t_aria >= 24 and dew_point >= 17: return 1, "(disagio lieve 🟡)"
    elif t_aria >= 22 and dew_point >= 19: return 1, "(disagio lieve 🟡)"
    return 0, ""

def calc_windchill(t, v):
    if t <= 10 and v >= 4.8: return 13.12 + 0.6215 * t - 11.37 * (v ** 0.16) + 0.3965 * t * (v ** 0.16)
    return t

def get_disagio_freddo(wc):
    if wc <= -40: return 4, "con un disagio estremo da freddo 🥶"
    elif wc <= -28: return 3, "con un disagio forte da freddo 🥶"
    elif wc <= -10: return 2, "con un disagio marcato da freddo 🥶"
    elif wc <= 0: return 1, "con un disagio lieve da freddo 🥶"
    return 0, ""

def arrotonda_decina(valore):
    if valore is None: return 0
    if valore >= 10: return int(round(valore / 10.0) * 10)
    else: return int(round(valore))

def arrotonda_intero(valore):
    if valore is None: return 0
    return int(round(valore))

def arrotonda_prob(prob):
    if prob < 15: return 0
    return max(20, min(100, int(round(prob / 10.0) * 10)))

def ottieni_fascia_oraria(ora):
    if 0 <= ora < 6: return "nella notte"
    elif 6 <= ora < 10: return "nella prima parte della mattinata"
    elif 10 <= ora < 13: return "nella tarda mattinata"
    elif 13 <= ora < 17: return "nel pomeriggio"
    elif 17 <= ora < 19: return "nel tardo pomeriggio"
    elif 19 <= ora < 22: return "in serata"
    else: return "nella tarda serata"

def get_cielo_prevalente(hours, cc_tot, cc_low, cc_mid, cc_high):
    if not hours: return "sereno"
    
    # Calcolo delle medie aritmetiche della copertura per il blocco orario
    avg_cc = sum(cc_tot[h] for h in hours if h < len(cc_tot) and cc_tot[h] is not None) / len(hours)
    avg_low = sum(cc_low[h] for h in hours if h < len(cc_low) and cc_low[h] is not None) / len(hours)
    avg_mid = sum(cc_mid[h] for h in hours if h < len(cc_mid) and cc_mid[h] is not None) / len(hours)
    
    if avg_cc < 10: return "sereno"
    elif avg_low < 15 and avg_mid < 15:
        if avg_cc <= 15: return "sereno o al più poco nuvoloso per velature"
        elif avg_cc <= 30: return "poco nuvoloso per velature"
        elif avg_cc <= 50: return "parzialmente nuvoloso per velature"
        elif avg_cc <= 70: return "irregolarmente nuvoloso per velature a tratti estese"
        elif avg_cc <= 90: return "molto nuvoloso per estese velature"
        else: return "coperto da nubi alte"
    else:
        if avg_cc <= 10: return "sereno"
        elif avg_cc <= 30: return "poco nuvoloso"
        elif avg_cc <= 50: return "parzialmente nuvoloso"
        elif avg_cc <= 70: return "irregolarmente nuvoloso"
        elif avg_cc <= 90: return "molto nuvoloso"
        else: return "coperto"

def interpella_groq(dati_testuali, oggi_str, domani_str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: return "Errore: GROQ_API_KEY non trovata."
    client = Groq(api_key=api_key)
    
    prompt = f'''
    Sei un meteorologo professionista. Scrivi un bollettino discorsivo, fluido ed elegante per Rivoli QUOTIDIANO (Oggi e Domani).
    Ti fornirò i "fatti salienti" generati da algoritmi matematici.
    
    REGOLE FERREE (PENA IL FALLIMENTO):
    1. STRUTTURA VISIVA E IMPAGINAZIONE: Devi rispettare in modo ASSOLUTO questo esatto schema di formattazione. Usa ESATTAMENTE gli spazi indicati qui sotto, senza incollare i testi, senza aggiungere ulteriori righe vuote e senza creare paragrafi extra:

<b>Aggiornamento meteo di {oggi_str}</b>

[Scrivi qui il paragrafo di Oggi]

[Scrivi qui il paragrafo di Domani]

    2. CONTENUTO PARAGRAFI E NUMERO: INIZIA SEMPRE ogni paragrafo citando il giorno contestualizzato e la data (es. "Oggi, {oggi_str}, " oppure "Domani, {domani_str}, "). I paragrafi testuali devono essere ESATTAMENTE E SOLTANTO DUE.
    3. DIVIETO ASSOLUTO DI FRASI RIEMPITIVE: NON aggiungere MAI frasi di chiusura, deduzioni o riempitivi come "non sono previsti altri fenomeni degni di nota", "nessun'altra segnalazione" o simili. Se i dati per una giornata finiscono, termina il paragrafo immediatamente con un punto.
    4. STILE TEMPERATURE E DISAGIO CALDO: Subito dopo la data, per esprimere le temperature usa TASSATIVAMENTE questa struttura al singolare: "la temperatura minima sarà di X °C, mentre la massima raggiungerà i Y °C". Scrivi i valori termici SEMPRE staccando l'unità di misura (es. "20 °C"). DEVI INCLUDERE l'emoji del disagio termico copiandola dai dati (es. "con un disagio marcato 🟠"). Se c'è l'avviso "(possibili gelate)", copialo testualmente dopo la minima.
    5. CIELO E NEBBIA: Non usare MAI l'avverbio "prevalentemente", usa sempre "in prevalenza". Se nei dati è indicata la nebbia, integrala in maniera fluida con la descrizione della nuvolosità.
    6. STILE VENTO E DISAGIO FREDDO: Se nei dati leggi "La ventilazione sarà blanda" o "La ventilazione sarà da blanda a moderata", scrivi ESATTAMENTE questo. Se è forte, aggancia fluidamente l'emoji e il disagio da freddo al vento se indicato.
    7. DIVIETO COMMENTI SOGGETTIVI: NON usare MAI espressioni romanzate come "condizioni ideali" o "giornata scomoda". Mantieni un tono tecnico e fattuale. NESSUN asterisco o markdown. Usa un linguaggio naturale per integrare le varie fasi di precipitazione fornite nei dati.
    8. QUALITÀ DELL'ARIA E SABBIA: Se presente l'avviso per aria inquinata o depositi di sabbia sulle superfici esposte, riportalo testualmente in modo asciutto alla fine del rispettivo paragrafo.
    
    DATI DA TRASFORMARE:
    {dati_testuali}
    '''
    try:
        res = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile", temperature=0.25)
        return res.choices[0].message.content
    except Exception as e: return f"Errore AI Groq: {e}"

def main():
    mese_corrente = datetime.now().month
    estate = mese_corrente in [5, 6, 7, 8, 9]
    FILE_LOCK = "lock_quotidiano.txt"
    oggi_str_lock = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi_str_lock:
                print("✅ Bollettino quotidiano già inviato oggi.")
                sys.exit(0)

    dt_oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    p_ch2_det = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "models": "meteoswiss_icon_ch2", 
                 "daily": "temperature_2m_min,temperature_2m_max,rain_sum,snowfall_sum,precipitation_probability_max,wind_direction_10m_dominant",
                 "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,wind_gusts_10m,snowfall,snow_depth,cloud_cover_low,cloud_cover_mid,cloud_cover_high,cape,cloud_cover"}
    p_ch2_ens = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "models": "meteoswiss_icon_ch2_ensemble_mean",
                 "daily": "temperature_2m_max,temperature_2m_min,rain_sum,snowfall_sum,wind_direction_10m_dominant",
                 "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,snowfall,snow_depth,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_gusts_10m,cape"}
    p_sea_det = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "models": "dwd_icon_seamless",
                 "daily": "temperature_2m_min,temperature_2m_max,rain_sum,snowfall_sum,precipitation_probability_max",
                 "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,snowfall,snow_depth,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_gusts_10m,cape"}
    p_sea_ens = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "models": "dwd_icon_eps_ensemble_mean_seamless",
                 "daily": "temperature_2m_min,temperature_2m_max,rain_sum,snowfall_sum",
                 "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,snowfall,cloud_cover,wind_gusts_10m,cape"}
    p_aq = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "hourly": "pm10,pm2_5,dust"}

    dati_ch2_det = scarica_sicuro("https://api.open-meteo.com/v1/forecast", p_ch2_det)
    dati_ch2_ens = scarica_sicuro("https://ensemble-api.open-meteo.com/v1/ensemble", p_ch2_ens)
    dati_sea_det = scarica_sicuro("https://api.open-meteo.com/v1/forecast", p_sea_det)
    dati_sea_ens = scarica_sicuro("https://ensemble-api.open-meteo.com/v1/ensemble", p_sea_ens)
    dati_aq = scarica_sicuro("https://air-quality-api.open-meteo.com/v1/air-quality", p_aq)

    d_ch2_det = dati_ch2_det.get('daily', {}); d_ch2_ens = dati_ch2_ens.get('daily', {})
    d_sea_det = dati_sea_det.get('daily', {}); d_sea_ens = dati_sea_ens.get('daily', {})

    giorni_time = d_ch2_det.get('time') or d_ch2_ens.get('time') or d_sea_det.get('time') or d_sea_ens.get('time') or []
    t_min_avg = get_avg_arrays(d_ch2_det.get('temperature_2m_min'), d_ch2_ens.get('temperature_2m_min'), d_sea_det.get('temperature_2m_min'), d_sea_ens.get('temperature_2m_min'))
    t_max_avg = get_avg_arrays(d_ch2_det.get('temperature_2m_max'), d_ch2_ens.get('temperature_2m_max'), d_sea_det.get('temperature_2m_max'), d_sea_ens.get('temperature_2m_max'))
    rain_sum_avg = get_avg_arrays(d_ch2_det.get('rain_sum'), d_ch2_ens.get('rain_sum'), d_sea_det.get('rain_sum'), d_sea_ens.get('rain_sum'))
    snow_sum_avg = get_avg_arrays(d_ch2_det.get('snowfall_sum'), d_ch2_ens.get('snowfall_sum'), d_sea_det.get('snowfall_sum'), d_sea_ens.get('snowfall_sum'))
    prob_det_avg = get_avg_arrays(d_ch2_det.get('precipitation_probability_max'), d_sea_det.get('precipitation_probability_max'))
    wind_dir_avg = avg_wind_dir_arrays(d_ch2_det.get('wind_direction_10m_dominant'), d_ch2_ens.get('wind_direction_10m_dominant'))
    
    h_ch2_det = dati_ch2_det.get('hourly', {}); h_ch2_ens = dati_ch2_ens.get('hourly', {})
    h_sea_det = dati_sea_det.get('hourly', {}); h_sea_ens = dati_sea_ens.get('hourly', {})
    
    orari = h_ch2_det.get('time') or h_ch2_ens.get('time') or h_sea_det.get('time') or h_sea_ens.get('time') or []
    if not orari: return

    t_avg = get_avg_arrays(h_ch2_det.get('temperature_2m'), h_ch2_ens.get('temperature_2m'), h_sea_det.get('temperature_2m'), h_sea_ens.get('temperature_2m'))
    dew_avg = get_avg_arrays(h_ch2_det.get('dew_point_2m'), h_ch2_ens.get('dew_point_2m'), h_sea_det.get('dew_point_2m'), h_sea_ens.get('dew_point_2m'))
    ur_avg = get_avg_arrays(h_ch2_det.get('relative_humidity_2m'), h_ch2_ens.get('relative_humidity_2m'), h_sea_det.get('relative_humidity_2m'), h_sea_ens.get('relative_humidity_2m'))
    app_avg = get_avg_arrays(h_ch2_det.get('apparent_temperature'), h_ch2_ens.get('apparent_temperature'), h_sea_det.get('apparent_temperature'), h_sea_ens.get('apparent_temperature'))
    w_gst_avg = get_avg_arrays(h_ch2_det.get('wind_gusts_10m'), h_ch2_ens.get('wind_gusts_10m'), h_sea_det.get('wind_gusts_10m'), h_sea_det.get('wind_gusts_10m'))
    cape_avg = get_avg_arrays(h_ch2_det.get('cape'), h_ch2_ens.get('cape'), h_sea_det.get('cape'), h_sea_ens.get('cape'))
    rain_avg = get_avg_arrays(h_ch2_det.get('rain'), h_ch2_ens.get('rain'), h_sea_det.get('rain'), h_sea_ens.get('rain'))
    snow_avg = get_avg_arrays(h_ch2_det.get('snowfall'), h_ch2_ens.get('snowfall'), h_sea_det.get('snowfall'), h_sea_ens.get('snowfall'))
    cc_tot = get_avg_arrays(h_ch2_det.get('cloud_cover'), h_ch2_ens.get('cloud_cover'), h_sea_det.get('cloud_cover'), h_sea_ens.get('cloud_cover'))
    snow_depth_avg = get_avg_arrays(h_ch2_det.get('snow_depth'), h_ch2_ens.get('snow_depth'), h_sea_det.get('snow_depth'))
    cc_low = get_avg_arrays(h_ch2_det.get('cloud_cover_low'), h_ch2_ens.get('cloud_cover_low'), h_sea_det.get('cloud_cover_low'))
    cc_mid = get_avg_arrays(h_ch2_det.get('cloud_cover_mid'), h_ch2_ens.get('cloud_cover_mid'), h_sea_det.get('cloud_cover_mid'))
    cc_high = get_avg_arrays(h_ch2_det.get('cloud_cover_high'), h_ch2_ens.get('cloud_cover_high'), h_sea_det.get('cloud_cover_high'))
    
    h_aq = dati_aq.get('hourly', {})
    pm10 = h_aq.get('pm10', []); pm25 = h_aq.get('pm2_5', []); dust = h_aq.get('dust', [])

    target_days = [0, 1]
    dati_giorni = {}
    
    for d_idx, d_str in enumerate(giorni_time):
        giorno_idx = (datetime.fromisoformat(d_str).date() - dt_oggi.date()).days
        if giorno_idx in target_days:
            dati_giorni[giorno_idx] = {
                't_min': t_min_avg[d_idx] if d_idx < len(t_min_avg) else 0,
                't_max': t_max_avg[d_idx] if d_idx < len(t_max_avg) else 0,
                'rain_sum': rain_sum_avg[d_idx] if d_idx < len(rain_sum_avg) else 0,
                'snow_sum': snow_sum_avg[d_idx] if d_idx < len(snow_sum_avg) else 0,
                'wind_dir': wind_dir_avg[d_idx] if d_idx < len(wind_dir_avg) else 0,
                'prob_max': prob_det_avg[d_idx] if d_idx < len(prob_det_avg) else 0,
                'livello_dc_max': 0, 'str_dc': "", 'livello_df_max': 0, 'str_df': "",
                'w_gst_max': -1, 'ora_w_gst_max': None, 'ora_inizio_vento': None, 'ora_fine_vento': None,
                'ha_precip': False, 
                'eventi_precip': {
                    'pioggia': {'inizio': None, 'fine': None, 'picco_mm': -1, 'ora_picco': None, 'estate_tipo': 'piogge'},
                    'mista': {'inizio': None, 'fine': None, 'picco_mm': -1, 'ora_picco': None},
                    'neve': {'inizio': None, 'fine': None, 'picco_mm': -1, 'ora_picco': None}
                },
                'cielo_mattino': "", 'cielo_pomeriggio': "", 'nebbie': set(), 'ha_gelate': False, 'aq_level': 0, 'max_snow_depth': 0.0,
                'ha_sabbia': False
            }

    ora_attuale = datetime.now().hour
    indici_validi = [
        i for i, t in enumerate(orari) 
        if (datetime.fromisoformat(t).date() - dt_oggi.date()).days in target_days 
        and not ((datetime.fromisoformat(t).date() - dt_oggi.date()).days == 0 and datetime.fromisoformat(t).hour < ora_attuale)
    ]

    for i in indici_validi:
        ora_solare = datetime.fromisoformat(orari[i]).hour
        giorno_idx = (datetime.fromisoformat(orari[i]).date() - dt_oggi.date()).days
        dg = dati_giorni[giorno_idx]
        
        t_m, dew_m, ur_m, app_m, w_m = t_avg[i], dew_avg[i], ur_avg[i], app_avg[i], w_gst_avg[i]
        cc_low_m = cc_low[i] if i < len(cc_low) and cc_low[i] is not None else 0
        cc_mid_m = cc_mid[i] if i < len(cc_mid) and cc_mid[i] is not None else 0
        dep = t_m - dew_m
        
        # AQ e Dust
        p10 = pm10[i] if i < len(pm10) and pm10[i] is not None else 0
        p25 = pm25[i] if i < len(pm25) and pm25[i] is not None else 0
        dust_val = dust[i] if i < len(dust) and dust[i] is not None else 0

        if p10 > 100 or p25 > 50: dg['aq_level'] = 2
        elif (p10 > 51 or p25 > 36) and dg['aq_level'] < 2: dg['aq_level'] = 1
            
        if estate:
            lvl_dc, st_dc = get_disagio_caldo(t_m, dew_m)
            if lvl_dc > dg['livello_dc_max']: dg['livello_dc_max'], dg['str_dc'] = lvl_dc, st_dc
        else:
            lvl_df, st_df = get_disagio_freddo(calc_windchill(t_m, w_m))
            if lvl_df > dg['livello_df_max']: dg['livello_df_max'], dg['str_df'] = lvl_df, st_df
            
        if w_m > dg['w_gst_max']: dg['w_gst_max'], dg['ora_w_gst_max'] = w_m, ora_solare
        if w_m >= 50:
            if dg['ora_inizio_vento'] is None: dg['ora_inizio_vento'] = ora_solare
            dg['ora_fine_vento'] = ora_solare

        sd_i = snow_depth_avg[i] if i < len(snow_depth_avg) else 0
        if sd_i > dg['max_snow_depth']: dg['max_snow_depth'] = sd_i

        # Rolling window per le precipitazioni (3 ore)
        idx_start = max(0, i - 1)
        idx_end = min(len(orari), i + 2)
        prec_3h = sum((rain_avg[j] + snow_avg[j]) for j in range(idx_start, idx_end) if j < len(rain_avg) and j < len(snow_avg))
        prec_oraria = rain_avg[i] + snow_avg[i]
        
        if prec_3h >= 1.0 and prec_oraria > 0.0:
            if dust_val > 25: dg['ha_sabbia'] = True
            
            # Determinazione del tipo di precipitazione oraria
            is_snow = snow_avg[i] >= 0.1
            is_rain = rain_avg[i] >= 0.1
            
            if is_snow and is_rain: t_p = 'mista'
            elif is_snow: t_p = 'neve'
            else: t_p = 'pioggia'
            
            ev = dg['eventi_precip'][t_p]
            if ev['inizio'] is None: ev['inizio'] = ora_solare
            ev['fine'] = ora_solare
            
            if prec_oraria > ev['picco_mm']:
                ev['picco_mm'] = prec_oraria
                ev['ora_picco'] = ora_solare
                
                if t_p == 'pioggia':
                    if estate and cape_avg[i] > 400: ev['estate_tipo'] = "rovesci o temporali"
                    elif estate: ev['estate_tipo'] = "rovesci"
                    else: ev['estate_tipo'] = "piogge"

        # Nebbia
        if ur_m >= 93 or dep <= 1.5:
            if cc_low_m < 20 and cc_mid_m < 20 and w_m < 10:
                dg['nebbie'].add(ottieni_fascia_oraria(ora_solare))
                
        # Gelate
        if ur_m >= 75 or dep <= 3.0:
            if t_m <= 0.0:
                dg['ha_gelate'] = True
            elif t_m <= 3.0 and cc_low_m < 20 and cc_mid_m < 20 and w_m < 12:
                dg['ha_gelate'] = True

    testo_per_ia = ""
    oggi_str = formatta_data_it(dt_oggi)
    domani_str = formatta_data_it(dt_oggi + timedelta(days=1))
    
    for g, nome_giorno in zip([0, 1], ["Oggi", "Domani"]):
        dg = dati_giorni[g]
        
        h_mat = [i for i in indici_validi if (datetime.fromisoformat(orari[i]).date() - dt_oggi.date()).days == g and 6 <= datetime.fromisoformat(orari[i]).hour <= 12]
        h_pom = [i for i in indici_validi if (datetime.fromisoformat(orari[i]).date() - dt_oggi.date()).days == g and 13 <= datetime.fromisoformat(orari[i]).hour <= 19]
        c_mat = get_cielo_prevalente(h_mat, cc_tot, cc_low, cc_mid, cc_high)
        c_pom = get_cielo_prevalente(h_pom, cc_tot, cc_low, cc_mid, cc_high)
        
        is_instabile = (estate and max([cape_avg[i] for i in indici_validi if (datetime.fromisoformat(orari[i]).date() - dt_oggi.date()).days == g] + [0]) > 400)
        soglia_precip = 15 if is_instabile else 50
        
        # Scatta l'avviso precipitazioni se la probabilità è raggiunta e almeno una categoria di precipitazione è iniziata
        if dg['prob_max'] >= soglia_precip and any(dg['eventi_precip'][k]['inizio'] is not None for k in dg['eventi_precip']): 
            dg['ha_precip'] = True
            
        testo_per_ia += f"GIORNO: {nome_giorno} ({oggi_str if g==0 else domani_str})\n"
        gelate_str = " (possibili gelate)" if dg['ha_gelate'] else ""
        testo_per_ia += f"- Temperature: minima {round(dg['t_min'])} °C{gelate_str}, massima {round(dg['t_max'])} °C {dg['str_dc']}\n"
        
        cielo_txt = ""
        if dg['nebbie']: cielo_txt += f"Possibili banchi di nebbia {', '.join(dg['nebbie'])}, per il resto "
        if c_mat == c_pom:
            if c_mat in ["sereno", "coperto"]: cielo_txt += f"cielo {c_mat} per gran parte del giorno."
            else: cielo_txt += f"cielo in prevalenza {c_mat} per gran parte del giorno."
        else: cielo_txt += f"cielo in prevalenza {c_mat} al mattino, tendente a {c_pom} nel pomeriggio."
        testo_per_ia += f"- Cielo: {cielo_txt}\n"
        
        if dg['ha_precip']:
            p_round = arrotonda_prob(dg['prob_max'])
            sabbia_str = " (con possibilità di depositi di sabbia sulle superfici esposte)" if dg['ha_sabbia'] else ""
            testo_per_ia += f"- Precipitazioni (Probabilità {p_round}%){sabbia_str}:\n"
            
            # Filtra ed ordina cronologicamente le fasi attive
            active_types = [t for t in ['pioggia', 'mista', 'neve'] if dg['eventi_precip'][t]['inizio'] is not None]
            active_types.sort(key=lambda t: dg['eventi_precip'][t]['inizio'])
            
            for t_p in active_types:
                ev = dg['eventi_precip'][t_p]
                
                if t_p == 'pioggia': nome_fenomeno = ev['estate_tipo']
                elif t_p == 'mista': nome_fenomeno = "pioggia mista a neve"
                elif t_p == 'neve': nome_fenomeno = "nevicate"
                
                i_prec = "deboli"
                if ev['picco_mm'] >= 30: i_prec = "a carattere di nubifragio"
                elif ev['picco_mm'] >= 8: i_prec = "molto forti"
                elif ev['picco_mm'] >= 4: i_prec = "forti"
                elif ev['picco_mm'] >= 2: i_prec = "moderate"
                
                picco_val = arrotonda_intero(ev['picco_mm'])
                picco_txt = f"circa {picco_val} mm/h" if picco_val > 0 else "inferiore a 1 mm/h"
                
                # Gestione semantica per eventi a cavallo della mezzanotte
                str_inizio = "in prosecuzione dalla serata precedente" if ev['inizio'] == 0 else f"inizio {ottieni_fascia_oraria(ev['inizio'])} (ore {ev['inizio']})"
                str_fine = "in prosecuzione oltre la mezzanotte" if ev['fine'] == 23 else f"fine {ottieni_fascia_oraria(ev['fine'])} (ore {ev['fine']})"
                
                if ev['inizio'] == ev['fine']:
                    if ev['inizio'] == 0:
                        testo_per_ia += f"  * Fase di {nome_fenomeno} {i_prec}: residui dalla serata precedente fino alle ore 0.\n"
                    elif ev['inizio'] == 23:
                        testo_per_ia += f"  * Fase di {nome_fenomeno} {i_prec}: in peggioramento dalle ore 23 e in prosecuzione oltre la mezzanotte.\n"
                    else:
                        testo_per_ia += f"  * Fase di {nome_fenomeno} {i_prec}: fenomeni isolati {ottieni_fascia_oraria(ev['inizio'])} (ore {ev['inizio']}).\n"
                else:
                    testo_per_ia += f"  * Fase di {nome_fenomeno} {i_prec}: {str_inizio}, picco {ottieni_fascia_oraria(ev['ora_picco'])} (ore {ev['ora_picco']}) con intensità {picco_txt}, {str_fine}.\n"
            
            if dg['snow_sum'] > 0 and ('neve' in active_types or 'mista' in active_types):
                sd_max = dg['max_snow_depth'] * 100
                if sd_max <= 1: s_str = "lieve velo al suolo"
                elif sd_max <= 3: s_str = "lieve imbiancata"
                elif sd_max <= 5: s_str = "discreta imbiancata"
                else: s_str = "abbondante imbiancata"
                testo_per_ia += f"  * Accumulo nevoso stimato a fine evento: {arrotonda_intero(dg['snow_sum'])} cm ({s_str}).\n"
            
            testo_per_ia += f"  * Accumulo pluviometrico totale stimato (incluso equivalente liquido della neve): {arrotonda_intero(dg['rain_sum'] + dg['snow_sum'])} mm.\n"

        if dg['w_gst_max'] >= 50:
            int_vento = "tempestosa" if dg['w_gst_max'] >= 70 else "forte"
            fohn_str = " (vento di Föhn)" if (225 <= dg['wind_dir'] <= 330) else ""
            txt_vento = f"La ventilazione diverrà {int_vento}{fohn_str}."
            if dg['ora_inizio_vento'] != dg['ora_fine_vento']:
                txt_vento += f" Intensificazione a partire da {ottieni_fascia_oraria(dg['ora_inizio_vento'])} (ore {dg['ora_inizio_vento']}), in attenuazione {ottieni_fascia_oraria(dg['ora_fine_vento'])} (ore {dg['ora_fine_vento']})."
            else:
                txt_vento += f" Breve rinforzo isolato {ottieni_fascia_oraria(dg['ora_inizio_vento'])} (ore {dg['ora_inizio_vento']})."
            txt_vento += f" Le raffiche massime previste {ottieni_fascia_oraria(dg['ora_w_gst_max'])} saranno attorno ai {arrotonda_tondo(dg['w_gst_max'])} km/h."
        elif dg['w_gst_max'] >= 30:
            txt_vento = "La ventilazione sarà da blanda a moderata."
        else:
            txt_vento = "La ventilazione sarà blanda."
            
        if dg['str_df']: txt_vento += f" Associato alla ventilazione, si percepirà {dg['str_df']}."
        testo_per_ia += f"- Vento: {txt_vento}\n"
            
        if dg['aq_level'] == 2: testo_per_ia += "- Attenzione, l'aria sarà molto inquinata.\n"
        elif dg['aq_level'] == 1: testo_per_ia += "- Attenzione, l'aria sarà inquinata.\n"
        testo_per_ia += "\n"

    # --- SALVATAGGIO STATO PER IL NOWCASTING ---
    try:
        with open("stato_precipitazioni_quotidiano.txt", "w") as f_stato:
            for g in target_days:
                data_str = (dt_oggi + timedelta(days=g)).strftime("%Y-%m-%d")
                ha_precip_str = "SI" if dati_giorni[g]['ha_precip'] else "NO"
                f_stato.write(f"{data_str},{ha_precip_str}\n")
    except Exception as e:
        print(f"⚠️ Errore salvataggio stato precipitazioni: {e}")
    # -------------------------------------------

    oggi_str = formatta_data_it(dt_oggi)
    bollettino_finale = interpella_groq(testo_per_ia, oggi_str, domani_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        if bollettino_finale.startswith("Errore"): print(f"Blocco Telegram per errore API: {bollettino_finale}")
        else:
            risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "HTML"})
            if risposta_tg.status_code == 200:
                print("Bollettino inviato con successo!")
                with open(FILE_LOCK, "w") as f: f.write(oggi_str_lock)
            else: print(f"Errore Telegram: {risposta_tg.text}")
    else: print("Mancano credenziali Telegram. Stampo a video:\n" + "-"*50 + "\n" + bollettino_finale)

if __name__ == "__main__":
    main()
