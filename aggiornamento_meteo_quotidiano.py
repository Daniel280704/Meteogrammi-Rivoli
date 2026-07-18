#!/usr/bin/env python3
import os
import sys
import time
import math
import requests
from collections import Counter
from datetime import datetime, timedelta
from groq import Groq

LAT = 45.0707
LON = 7.5146

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

def formatta_data_it(dt):
    return f"{GIORNI_IT[dt.weekday()]} {dt.day} {MESI_IT[dt.month]}"

def get_avg_array(arr1, arr2):
    if not arr1: return arr2
    if not arr2: return arr1
    return [(v1 + v2) / 2.0 if v1 is not None and v2 is not None else (v1 if v1 is not None else (v2 if v2 is not None else 0.0)) for v1, v2 in zip(arr1, arr2)]

def avg_wind_dir(arr1, arr2):
    if not arr1: return arr2
    if not arr2: return arr1
    res = []
    for d1, d2 in zip(arr1, arr2):
        if d1 is None and d2 is None: res.append(0)
        elif d1 is None: res.append(d2)
        elif d2 is None: res.append(d1)
        else:
            u = math.sin(math.radians(d1)) + math.sin(math.radians(d2))
            v = math.cos(math.radians(d1)) + math.cos(math.radians(d2))
            res.append((math.degrees(math.atan2(u, v)) + 360) % 360)
    return res

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
    if wc <= -40: return 4, "un disagio estremo da freddo 🥶"
    elif wc <= -28: return 3, "un disagio forte da freddo 🥶"
    elif wc <= -10: return 2, "un disagio marcato da freddo 🥶"
    elif wc <= 0: return 1, "un disagio lieve da freddo 🥶"
    return 0, ""

def arrotonda_decina(valore):
    return int(round(valore / 10.0) * 10)

def arrotonda_intero(valore):
    return int(round(valore))

def arrotonda_prob(prob):
    if prob < 15: return 0
    return max(20, min(100, int(round(prob / 10.0) * 10)))

def get_cielo_prevalente(hours, cc_tot, cc_low, cc_mid, cc_high):
    if not hours: return "sereno"
    states = []
    for h in hours:
        cc = cc_tot[h]; low = cc_low[h]; mid = cc_mid[h]
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
    Sei un meteorologo professionista. Il tuo compito è scrivere un bollettino discorsivo, fluido ed elegante per Rivoli (TO) QUOTIDIANO.
    Ti fornirò i "fatti salienti" generati da rigorosi algoritmi matematici. Trasforma questi appunti in un testo discorsivo.

    REGOLE FERREE (PENA IL FALLIMENTO):
    1. TITOLO E IMPAGINAZIONE: Inizia ESATTAMENTE con: <b>Aggiornamento meteo di {oggi_str}</b>. Lascia una riga vuota tra il titolo e il testo, e UNA SOLA riga vuota tra i paragrafi (2 paragrafi totali per le due giornate previste).
    2. STILE TEMPERATURE E DISAGIO CALDO: Usa il singolare senza MAI indicare gli orari per le temperature. Unisci il disagio termico fornito alla temperatura massima (es. "La giornata sarà caratterizzata da una temperatura minima di 20°C e una massima di 34°C (disagio marcato 🟠)"). NON dedurre disagi inesistenti.
    3. STILE VENTO E DISAGIO FREDDO: Riporta l'intensità (blanda/moderata/forte), l'eventuale Föhn e le raffiche arrotondate fornite. Aggiungi fluidamente il disagio da freddo al vento se presente (es. "La ventilazione diverrà forte (vento di Föhn)... con un marcato disagio da freddo 🥶").
    4. PRECIPITAZIONI E NUVOLOSITÀ: Usa ESATTAMENTE i termini forniti per il cielo (es. "cielo velato o coperto da nubi alte"). Riporta le probabilità arrotondate (%), gli orari per inizio/fine e gli accumuli testuali (es. "lieve imbiancata"). Converti le ore numeriche in fasce orarie discorsive quando utile per rendere il testo naturale ("ore 15" -> "metà pomeriggio").
    5. QUALITÀ DELL'ARIA: Se presente l'avviso per PM10/PM2.5 nei dati, riportalo testualmente e in modo asciutto alla fine del rispettivo paragrafo.
    6. DIVIETO ASSOLUTO DI COMMENTI SOGGETTIVI: NON usare MAI espressioni romanzate come "condizioni ideali", "senza compromettere la piacevolezza", "giornata scomoda". Il tono deve essere tecnico e fattuale. NESSUN asterisco o markdown.

    DATI DA TRASFORMARE:
    {dati_testuali}
    """
    try:
        res = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile", temperature=0.25)
        return res.choices[0].message.content
    except Exception as e: return f"Errore AI Groq: {e}"

def main():
    FILE_LOCK = "lock_quotidiano.txt"
    oggi_str_lock = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi_str_lock:
                print("✅ Bollettino quotidiano già inviato oggi.")
                sys.exit(0)

    dt_oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    params_base = {"latitude": LAT, "longitude": LON, "timezone": "auto", "forecast_days": 3}
    try:
        p_det = params_base.copy()
        p_det.update({"models": "meteoswiss_icon_ch2", 
                      "daily": "temperature_2m_min,temperature_2m_max,rain_sum,snowfall_sum,precipitation_probability_max,wind_direction_10m_dominant",
                      "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,wind_gusts_10m,snowfall,snow_depth,cloud_cover_low,cloud_cover_mid,cloud_cover_high,cape,cloud_cover"})
        dati_det = scarica_dati_con_retry("https://api.open-meteo.com/v1/forecast", params=p_det)
        
        p_ens = params_base.copy()
        p_ens.update({"models": "meteoswiss_icon_ch2_ensemble_mean",
                      "daily": "temperature_2m_max,temperature_2m_min,rain_sum,snowfall_sum,wind_direction_10m_dominant",
                      "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,rain,snowfall,snow_depth,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_gusts_10m,cape"})
        dati_ens = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params=p_ens)
        
        p_aq = params_base.copy()
        p_aq.update({"hourly": "pm10,pm2_5"})
        dati_aq = scarica_dati_con_retry("https://air-quality-api.open-meteo.com/v1/air-quality", params=p_aq)
    except Exception as e:
        print(f"❌ Errore critico download dati: {e}")
        return

    # Estrazione Dati Giornalieri (Media Det/Ens)
    d_det = dati_det.get('daily', {}); d_ens = dati_ens.get('daily', {})
    t_min_avg = get_avg_array(d_det.get('temperature_2m_min', []), d_ens.get('temperature_2m_min', []))
    t_max_avg = get_avg_array(d_det.get('temperature_2m_max', []), d_ens.get('temperature_2m_max', []))
    rain_sum_avg = get_avg_array(d_det.get('rain_sum', []), d_ens.get('rain_sum', []))
    snow_sum_avg = get_avg_array(d_det.get('snowfall_sum', []), d_ens.get('snowfall_sum', []))
    wind_dir_avg = avg_wind_dir(d_det.get('wind_direction_10m_dominant', []), d_ens.get('wind_direction_10m_dominant', []))
    prob_det = d_det.get('precipitation_probability_max', [0]*3)
    
    # Estrazione Dati Orari (Media Det/Ens)
    h_det = dati_det.get('hourly', {}); h_ens = dati_ens.get('hourly', {})
    t_avg = get_avg_array(h_det.get('temperature_2m', []), h_ens.get('temperature_2m', []))
    dew_avg = get_avg_array(h_det.get('dew_point_2m', []), h_ens.get('dew_point_2m', []))
    w_gst_avg = get_avg_array(h_det.get('wind_gusts_10m', []), h_ens.get('wind_gusts_10m', []))
    cape_avg = get_avg_array(h_det.get('cape', []), h_ens.get('cape', []))
    rain_avg = get_avg_array(h_det.get('rain', []), h_ens.get('rain', []))
    snow_avg = get_avg_array(h_det.get('snowfall', []), h_ens.get('snowfall', []))
    snow_depth_avg = get_avg_array(h_det.get('snow_depth', []), h_ens.get('snow_depth', []))
    cc_tot = get_avg_array(h_det.get('cloud_cover', []), h_ens.get('cloud_cover', []))
    cc_low = get_avg_array(h_det.get('cloud_cover_low', []), h_ens.get('cloud_cover_low', []))
    cc_mid = get_avg_array(h_det.get('cloud_cover_mid', []), h_ens.get('cloud_cover_mid', []))
    cc_high = get_avg_array(h_det.get('cloud_cover_high', []), h_ens.get('cloud_cover_high', []))
    
    # Air Quality Oraria
    h_aq = dati_aq.get('hourly', {})
    pm10 = h_aq.get('pm10', [])
    pm25 = h_aq.get('pm2_5', [])

    testo_per_ia = ""
    oggi_str = formatta_data_it(dt_oggi)
    domani_str = formatta_data_it(dt_oggi + timedelta(days=1))
    
    for d_idx, nome_giorno in zip([0, 1], ["Oggi", "Domani"]):
        day_hours = list(range(d_idx * 24, (d_idx + 1) * 24))
        
        # Disagio Caldo
        max_dc_lvl, str_dc = 0, ""
        for h in day_hours:
            lvl, st = get_disagio_caldo(t_avg[h], dew_avg[h])
            if lvl > max_dc_lvl: max_dc_lvl, str_dc = lvl, st
                
        # Disagio Freddo
        max_df_lvl, str_df = 0, ""
        for h in day_hours:
            lvl, st = get_disagio_freddo(calc_windchill(t_avg[h], w_gst_avg[h]))
            if lvl > max_df_lvl: max_df_lvl, str_df = lvl, st

        # Precipitazioni
        cape_max = max([cape_avg[h] for h in day_hours])
        is_convective = (cape_max >= 400)
        prob_max = prob_det[d_idx]
        prob_rounded = arrotonda_prob(prob_max)
        hours_with_precip = [h for h in day_hours if (rain_avg[h] + snow_avg[h]) >= 1.0]
        
        txt_precip = ""
        has_precip = False
        
        if is_convective and prob_max >= 15 and hours_with_precip:
            has_precip = True
            start_h = min(hours_with_precip) % 24
            end_h = max(hours_with_precip) % 24
            if start_h == end_h: txt_precip = f"Possibilità di rovesci o temporali ({prob_rounded}%) isolati attorno alle ore {start_h}."
            else: txt_precip = f"Possibilità di rovesci o temporali ({prob_rounded}%) tra le ore {start_h} e le ore {end_h}."
                
        elif not is_convective and prob_max >= 50 and hours_with_precip:
            has_precip = True
            start_h = min(hours_with_precip) % 24
            end_h = max(hours_with_precip) % 24
            max_int = max([rain_avg[h] + snow_avg[h] for h in hours_with_precip])
            peak_h = [h%24 for h in hours_with_precip if (rain_avg[h] + snow_avg[h]) == max_int][0]
            
            int_str = "deboli"
            if max_int >= 30: int_str = "a carattere di nubifragio"
            elif max_int >= 8: int_str = "molto forti"
            elif max_int >= 4: int_str = "forti"
            elif max_int >= 2: int_str = "moderate"
            
            rs = rain_sum_avg[d_idx]
            ss = snow_sum_avg[d_idx]
            tipo = "nevicate" if ss > rs else "piogge"
            
            txt_precip = f"Previste {int_str} {tipo} ({prob_rounded}%) a partire dalle ore {start_h}, in intensificazione con picco verso le ore {peak_h}, attenuazione e successiva cessazione attorno alle ore {end_h}."
            if start_h == end_h: txt_precip = f"Previste {int_str} {tipo} ({prob_rounded}%) isolate attorno alle ore {start_h}."
            
            if ss > rs:
                sd_max = max([snow_depth_avg[h] * 100 for h in day_hours])
                if sd_max <= 1: snow_str = "lieve velo al suolo"
                elif sd_max <= 3: snow_str = "lieve imbiancata"
                elif sd_max <= 5: snow_str = "discreta imbiancata"
                else: snow_str = "abbondante imbiancata"
                txt_precip += f" Accumulo nevoso stimato: {arrotonda_intero(ss)} cm ({snow_str})."
            else:
                txt_precip += f" L'accumulo pluviometrico complessivo è stimato sui {arrotonda_intero(rs+ss)} mm."

        # Copertura Nuvolosa
        c_mat = get_cielo_prevalente([h for h in day_hours if 6 <= h%24 < 13], cc_tot, cc_low, cc_mid, cc_high)
        c_pom = get_cielo_prevalente([h for h in day_hours if 13 <= h%24 < 19], cc_tot, cc_low, cc_mid, cc_high)

        # Ventilazione
        max_w = max([w_gst_avg[h] for h in day_hours])
        if max_w < 30:
            txt_vento = "La ventilazione si manterrà blanda."
            if str_df: txt_vento += f" Ad essa si assocerà {str_df}."
        else:
            is_fohn = (225 <= wind_dir_avg[d_idx] <= 315)
            fohn_str = " (vento di Föhn)" if is_fohn else ""
            
            if max_w >= 60:
                h_target = [h%24 for h in day_hours if w_gst_avg[h] >= 60]
                int_str = "forte"
                ritorno_str = "moderata"
            else:
                h_target = [h%24 for h in day_hours if w_gst_avg[h] >= 30]
                int_str = "moderata"
                ritorno_str = "blanda"
                
            start_w = min(h_target)
            end_w = max(h_target)
            
            txt_vento = f"La ventilazione diverrà {int_str}{fohn_str} a partire dalle ore {start_w}"
            if start_w < end_w and end_w < 23:
                txt_vento += f", tornando {ritorno_str} verso le ore {end_w}"
            elif start_w == end_w and end_w < 23:
                txt_vento = f"Si segnala un isolato rinforzo a ventilazione {int_str}{fohn_str} verso le ore {start_w}"
            txt_vento += f". Le raffiche massime si attesteranno sui {arrotonda_decina(max_w)} km/h."
            if str_df: txt_vento += f" Associato alla ventilazione, si percepirà {str_df}."

        # Air Quality
        aq_lvl = 0
        for h in day_hours:
            if h < len(pm10):
                if pm10[h] > 100 or pm25[h] > 50: aq_lvl = 2
                elif (pm10[h] > 51 or pm25[h] > 36) and aq_lvl < 2: aq_lvl = 1
        txt_aq = "Attenzione, l'aria sarà molto inquinata." if aq_lvl == 2 else ("Attenzione, l'aria sarà inquinata." if aq_lvl == 1 else "")

        # Assemblaggio 
        testo_per_ia += f"GIORNO: {nome_giorno} ({oggi_str if d_idx==0 else domani_str})\n"
        testo_per_ia += f"- Temperature: minima {round(t_min_avg[d_idx])}°C, massima {round(t_max_avg[d_idx])}°C {str_dc}\n"
        if c_mat == c_pom: testo_per_ia += f"- Cielo: prevalentemente {c_mat} per gran parte del giorno.\n"
        else: testo_per_ia += f"- Cielo: {c_mat} al mattino, tendente a {c_pom} nel pomeriggio.\n"
        if has_precip: testo_per_ia += f"- Precipitazioni: {txt_precip}\n"
        testo_per_ia += f"- Vento: {txt_vento}\n"
        if txt_aq: testo_per_ia += f"- Qualità aria: {txt_aq}\n"
        testo_per_ia += "\n"

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
    else:
        print("Mancano credenziali Telegram. Stampo a video:\n" + "-"*50 + "\n" + bollettino_finale)

if __name__ == "__main__":
    main()
