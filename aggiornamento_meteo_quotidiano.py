#!/usr/bin/env python3
import os
import sys
import time
import math
import requests
from collections import Counter
from datetime import datetime, timedelta
from groq import Groq

LAT = 45.0736
LON = 7.5434

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
    states = []
    for h in hours:
        cc = cc_tot[h] if h < len(cc_tot) else 0
        low = cc_low[h] if h < len(cc_low) else 0
        mid = cc_mid[h] if h < len(cc_mid) else 0
        
        if cc < 10: states.append("sereno")
        elif low < 15 and mid < 15:
            if cc <= 15: states.append("sereno")
            elif cc <= 50: states.append("poco nuvoloso per velature")
            elif cc <= 80: states.append("parzialmente nuvoloso per nubi alte")
            else: states.append("cielo velato o coperto da nubi alte")
        else:
            if cc <= 10: states.append("sereno")
            elif cc <= 30: states.append("poco nuvoloso")
            elif cc <= 60: states.append("irregolarmente nuvoloso")
            elif cc <= 85: states.append("molto nuvoloso")
            else: states.append("coperto")
    return Counter(states).most_common(1)[0][0] if states else "sereno"

def interpella_groq(dati_testuali, oggi_str, domani_str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: return "Errore: GROQ_API_KEY non trovata."
    client = Groq(api_key=api_key)
    
    prompt = f"""
    Sei un meteorologo professionista. Scrivi un bollettino discorsivo, fluido ed elegante per Rivoli (TO) QUOTIDIANO.
    Ti fornirò i "fatti salienti" generati da algoritmi matematici.
    
    REGOLE FERREE (PENA IL FALLIMENTO):
    1. TITOLO: Inizia ESATTAMENTE con: <b>Aggiornamento meteo di {oggi_str}</b>.
    2. STRUTTURA: Due paragrafi totali, uno per oggi e uno per domani. Lascia TASSATIVAMENTE UNA E UNA SOLA riga vuota tra i paragrafi.
    3. STILE TEMPERATURE E DISAGIO CALDO: Usa il singolare senza indicare gli orari (es. "una temperatura minima di 20°C e una massima di 34°C"). DEVI TASSATIVAMENTE INCLUDERE L'EMOJI DEL DISAGIO COPIANDOLA DAI DATI (es. "con un disagio marcato 🟠").
    4. STILE VENTO E DISAGIO FREDDO: Se nei dati leggi "La ventilazione sarà blanda" o "La ventilazione sarà da blanda a moderata", scrivi ESATTAMENTE questo. Se è forte, aggancia fluidamente l'emoji e il disagio da freddo al vento se indicato (es. "...con un disagio lieve da freddo 🥶").
    5. ORARI E PREPOSIZIONI: Usa ESATTAMENTE le preposizioni articolate fornite (es. "nel pomeriggio"). È vietato usare "in notte" o "in pomeriggio". Se presente l'orario numerico in parentesi, integralo nel discorso (es. "attorno alle ore 15").
    6. DIVIETO COMMENTI SOGGETTIVI: NON usare MAI espressioni romanzate come "condizioni ideali" o "giornata scomoda". Mantieni un tono tecnico e fattuale. NESSUN asterisco o markdown.
    7. QUALITÀ DELL'ARIA E SABBIA: Se presente l'avviso per aria inquinata o depositi di sabbia sulle superfici esposte, riportalo testualmente.
    
    DATI DA TRASFORMARE:
    {dati_testuali}
    """
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
    
    # 1. ICON-CH2 Deterministico
    p_ch2_det = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "models": "meteoswiss_icon_ch2", 
                 "daily": "temperature_2m_min,temperature_2m_max,rain_sum,snowfall_sum,precipitation_probability_max,wind_direction_10m_dominant",
                 "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,wind_gusts_10m,snowfall,snow_depth,cloud_cover_low,cloud_cover_mid,cloud_cover_high,cape,cloud_cover"}
    # 2. ICON-CH2 Ensemble Mean
    p_ch2_ens = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "models": "meteoswiss_icon_ch2_ensemble_mean",
                 "daily": "temperature_2m_max,temperature_2m_min,rain_sum,snowfall_sum,wind_direction_10m_dominant",
                 "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,snowfall,snow_depth,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_gusts_10m,cape"}
    # 3. ICON Seamless Deterministico
    p_sea_det = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "models": "dwd_icon_seamless",
                 "daily": "temperature_2m_min,temperature_2m_max,rain_sum,snowfall_sum,precipitation_probability_max",
                 "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,snowfall,snow_depth,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_gusts_10m,cape"}
    # 4. ICON Seamless Ensemble Mean
    p_sea_ens = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3, "models": "dwd_icon_eps_ensemble_mean_seamless",
                 "daily": "temperature_2m_min,temperature_2m_max,rain_sum,snowfall_sum",
                 "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,snowfall,cloud_cover,wind_gusts_10m,cape"}
    # 5. Air Quality & Dust
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
    w_gst_avg = get_avg_arrays(h_ch2_det.get('wind_gusts_10m'), h_ch2_ens.get('wind_gusts_10m'), h_sea_det.get('wind_gusts_10m'), h_sea_ens.get('wind_gusts_10m'))
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
                'ha_precip': False, 'ora_inizio_p': None, 'ora_fine_p': None, 'picco_p_mm': -1, 'ora_picco_p': None, 'tipo_p': "",
                'cielo_mattino': "", 'cielo_pomeriggio': "", 'gelate': set(), 'nebbie': set(), 'aq_level': 0, 'max_snow_depth': 0.0,
                'ha_sabbia': False
            }

    indici_validi = [i for i, t in enumerate(orari) if (datetime.fromisoformat(t).date() - dt_oggi.date()).days in target_days]

    for i in indici_validi:
        ora_solare = datetime.fromisoformat(orari[i]).hour
        giorno_idx = (datetime.fromisoformat(orari[i]).date() - dt_oggi.date()).days
        dg = dati_giorni[giorno_idx]
        
        t_m, dew_m, ur_m, app_m, w_m = t_avg[i], dew_avg[i], ur_avg[i], app_avg[i], w_gst_avg[i]
        
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

        prec_tot = rain_avg[i] + snow_avg[i]
        if prec_tot >= 1.0:
            if dust_val > 25: dg['ha_sabbia'] = True
            if dg['ora_inizio_p'] is None: dg['ora_inizio_p'] = ora_solare
            dg['ora_fine_p'] = ora_solare
            if prec_tot > dg['picco_p_mm']:
                dg['picco_p_mm'], dg['ora_picco_p'] = prec_tot, ora_solare
                if snow_avg[i] > rain_avg[i] and snow_avg[i] > 0.5: dg['tipo_p'] = "nevicate"
                elif (estate and cape_avg[i] > 400): dg['tipo_p'] = "rovesci o temporali"
                elif estate: dg['tipo_p'] = "rovesci"
                else: dg['tipo_p'] = "piogge"

        if abs(dew_m - t_m) <= 1 and ur_m >= 95 and w_m < 15: dg['nebbie'].add(ottieni_fascia_oraria(ora_solare))
        if ora_solare >= 22 or ora_solare <= 8:
            if t_m <= -4 and ur_m >= 50: dg['gelate'].add(f"forti gelate {ottieni_fascia_oraria(ora_solare)}")
            elif -4 < t_m <= -1 and ur_m >= 60: dg['gelate'].add(f"gelate diffuse {ottieni_fascia_oraria(ora_solare)}")
            elif -1 < t_m <= 1 and t_m <= 0 and ur_m >= 55: dg['gelate'].add(f"lievi gelate {ottieni_fascia_oraria(ora_solare)}")

    testo_per_ia = ""
    oggi_str = formatta_data_it(dt_oggi)
    domani_str = formatta_data_it(dt_oggi + timedelta(days=1))
    
    for g, nome_giorno in zip([0, 1], ["Oggi", "Domani"]):
        dg = dati_giorni[g]
        
        h_mat = [i for i in indici_validi if (datetime.fromisoformat(orari[i]).date() - dt_oggi.date()).days == g and 6 <= datetime.fromisoformat(orari[i]).hour < 13]
        h_pom = [i for i in indici_validi if (datetime.fromisoformat(orari[i]).date() - dt_oggi.date()).days == g and 13 <= datetime.fromisoformat(orari[i]).hour < 19]
        c_mat = get_cielo_prevalente(h_mat, cc_tot, cc_low, cc_mid, cc_high)
        c_pom = get_cielo_prevalente(h_pom, cc_tot, cc_low, cc_mid, cc_high)
        
        is_instabile = (estate and max([cape_avg[i] for i in indici_validi if (datetime.fromisoformat(orari[i]).date() - dt_oggi.date()).days == g] + [0]) > 400)
        soglia_precip = 15 if is_instabile else 50
        if dg['prob_max'] >= soglia_precip and dg['picco_p_mm'] >= 1.0: dg['ha_precip'] = True
            
        testo_per_ia += f"GIORNO: {nome_giorno} ({oggi_str if g==0 else domani_str})\n"
        testo_per_ia += f"- Temperature: minima {round(dg['t_min'])}°C, massima {round(dg['t_max'])}°C {dg['str_dc']}\n"
        
        if c_mat == c_pom: 
            if c_mat in ["sereno", "coperto"]:
                testo_per_ia += f"- Cielo: prevalentemente {c_mat} per gran parte del giorno.\n"
            else:
                testo_per_ia += f"- Cielo: in prevalenza {c_mat} per gran parte del giorno.\n"
        else: testo_per_ia += f"- Cielo: {c_mat} al mattino, tendente a {c_pom} nel pomeriggio.\n"
        
        if dg['ha_precip']:
            p_round = arrotonda_prob(dg['prob_max'])
            sabbia_str = " (con possibilità di depositi di sabbia sulle superfici esposte)" if dg['ha_sabbia'] else ""
            
            if estate and dg['tipo_p'] in ["rovesci", "rovesci o temporali"]:
                testo_per_ia += f"- Precipitazioni: Possibilità di {dg['tipo_p']} ({p_round}%){sabbia_str}."
                if dg['ora_inizio_p'] == dg['ora_fine_p']: testo_per_ia += f" Fenomeni isolati {ottieni_fascia_oraria(dg['ora_inizio_p'])} (ore {dg['ora_inizio_p']}).\n"
                else: testo_per_ia += f" Tra le ore {dg['ora_inizio_p']} e le ore {dg['ora_fine_p']}.\n"
            else:
                i_prec = "deboli"
                if dg['picco_p_mm'] >= 30: i_prec = "a carattere di nubifragio"
                elif dg['picco_p_mm'] >= 8: i_prec = "molto forti"
                elif dg['picco_p_mm'] >= 4: i_prec = "forti"
                elif dg['picco_p_mm'] >= 2: i_prec = "moderate"
                
                testo_per_ia += f"- Precipitazioni: Previste {i_prec} {dg['tipo_p']} ({p_round}%){sabbia_str}."
                if dg['ora_inizio_p'] == dg['ora_fine_p']: testo_per_ia += f" Isolate {ottieni_fascia_oraria(dg['ora_inizio_p'])} (ore {dg['ora_inizio_p']})."
                else: testo_per_ia += f" Inizio {ottieni_fascia_oraria(dg['ora_inizio_p'])} (ore {dg['ora_inizio_p']}), intensificazione con picco {ottieni_fascia_oraria(dg['ora_picco_p'])} (ore {dg['ora_picco_p']}), attenuazione e cessazione {ottieni_fascia_oraria(dg['ora_fine_p'])} (ore {dg['ora_fine_p']})."
                
                if dg['tipo_p'] == "nevicate" and dg['snow_sum'] > 0:
                    sd_max = dg['max_snow_depth'] * 100
                    if sd_max <= 1: s_str = "lieve velo al suolo"
                    elif sd_max <= 3: s_str = "lieve imbiancata"
                    elif sd_max <= 5: s_str = "discreta imbiancata"
                    else: s_str = "abbondante imbiancata"
                    testo_per_ia += f" Accumulo nevoso stimato: {arrotonda_intero(dg['snow_sum'])} cm ({s_str}).\n"
                else:
                    testo_per_ia += f" Accumulo pluviometrico stimato sui {arrotonda_intero(dg['rain_sum'] + dg['snow_sum'])} mm.\n"

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
            
        if dg['gelate']: testo_per_ia += f"- Pericolo gelo: {', '.join(dg['gelate'])}\n"
        if dg['nebbie']: testo_per_ia += f"- Rischio nebbia nelle seguenti fasce orarie: {', '.join(dg['nebbie'])}\n"
        if dg['aq_level'] == 2: testo_per_ia += "- Attenzione, l'aria sarà molto inquinata.\n"
        elif dg['aq_level'] == 1: testo_per_ia += "- Attenzione, l'aria sarà inquinata.\n"
        testo_per_ia += "\n"

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
