#!/usr/bin/env python3
import os
import sys
import time
import requests
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
            print(f"⚠️ Errore connessione Open-Meteo (Tentativo {tentativo + 1}/{max_retries}): {e}")
            if tentativo < max_retries - 1:
                time.sleep(10)
            else:
                raise e

def formatta_data_it(dt):
    return f"{GIORNI_IT[dt.weekday()]} {dt.day} {MESI_IT[dt.month]}"

def ottieni_fascia_oraria(ora):
    if 0 <= ora < 6: return "nella notte"
    elif 6 <= ora < 10: return "nella prima parte della mattinata"
    elif 10 <= ora < 13: return "nella tarda mattinata"
    elif 13 <= ora < 17: return "nel pomeriggio"
    elif 17 <= ora < 19: return "nel tardo pomeriggio"
    elif 19 <= ora < 22: return "in serata"
    else: return "nella tarda serata"

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
    else: return ("(nessun disagio o caldo tollerabile 🟢)", 0)

def calcola_disagio_freddo(windchill):
    if windchill < -40: return ("(disagio estremo da freddo 🥶)", 4)
    elif windchill < -25: return ("(disagio forte da freddo 🥶)", 3)
    elif windchill < -10: return ("(disagio marcato da freddo 🥶)", 2)
    elif windchill < 0: return ("(disagio lieve da freddo 🥶)", 1)
    else: return ("(nessun disagio o freddo tollerabile 🟢)", 0)

def pulisci_disagio(stringa):
    return stringa.replace("(disagio ", "").replace("da freddo ", "").replace("(", "").replace(")", "").replace("o caldo tollerabile ", "").replace("o freddo tollerabile ", "").strip()

def arrotonda_tondo(valore):
    if valore is None: return 0
    if valore >= 10: return int(round(valore / 10.0) * 10)
    else: return int(round(valore))

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
    if not api_key: return "Errore: GROQ_API_KEY non trovata."
        
    client = Groq(api_key=api_key)
    
    prompt = f"""
    Sei un meteorologo professionista. Il tuo compito è scrivere un bollettino discorsivo, fluido ed elegante per Rivoli (TO) a MEDIO TERMINE.
    Ti fornirò un elenco dei "fatti salienti" già calcolati. Trasforma questi appunti in un testo discorsivo.
    
    REGOLE FERREE (PENA IL FALLIMENTO):
    1. TITOLO: Inizia ESATTAMENTE con: <b>Aggiornamento meteo a medio termine di {oggi_str}</b>. Lascia una riga vuota tra il titolo e il testo.
    2. STRUTTURA: Tre paragrafi, uno per {giorni_str[2]}, uno per {giorni_str[3]}, uno per {giorni_str[4]}. Lascia ESATTAMENTE una riga vuota tra un paragrafo e l'altro.
    3. STILE TEMPERATURE E DISAGIO: Usa il singolare (es. "una temperatura minima di 20°C e una massima di 34°C"). Il disagio termico va inserito tra parentesi con l'emoji.
    4. STILE VENTO E PRECIPITAZIONI: Se indichi raffiche o inizio/fine ventilazione, integra fluidamente (es. "La ventilazione si intensificherà nel pomeriggio per poi attenuarsi in serata, con raffiche massime attorno ai 60 km/h"). Se leggi "ventilazione blanda" o "ventilazione modesta", riportalo ESATTAMENTE così senza inventare orari o raffiche.
    5. ORARI E PREPOSIZIONI: Copia e usa ESATTAMENTE le preposizioni articolate di tempo fornite (es. "nel pomeriggio", "nella notte"). È severamente vietato scrivere "in notte" o "in pomeriggio".
    6. DIVIETO ASSOLUTO DI COMMENTI SOGGETTIVI E RIEMPITIVI: NON aggiungere deduzioni o frasi finali come "offrendo condizioni ideali", "senza compromettere la piacevolezza", "rendendo la giornata scomoda". Mantieni un tono puramente descrittivo.
    7. QUALITÀ DELL'ARIA: Se nei dati compare l'avviso sulla qualità dell'aria, scrivilo ESATTAMENTE come fornito alla fine del paragrafo (es. "Attenzione, l'aria sarà inquinata.").
    8. FORMATTAZIONE: Nessun asterisco o underscore.
    
    DATI DA TRASFORMARE:
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
    
    base_params = {
        "latitude": LAT, "longitude": LON,
        "daily": "temperature_2m_min,temperature_2m_max,rain_sum,snowfall_sum,wind_gusts_10m_max",
        "hourly": "temperature_2m,dew_point_2m,wind_gusts_10m,rain,snowfall,snow_depth,cape,sunshine_duration,apparent_temperature,relative_humidity_2m",
        "timezone": "Europe/Rome",
        "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
        "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
    }

    try:
        params_ch2 = base_params.copy()
        params_ch2["models"] = "meteoswiss_icon_ch2_ensemble"
        dati_eps = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params=params_ch2)
        orari_temp = dati_eps.get('hourly', {}).get('time', [])
        target_dt = dt_fine_estrazione + timedelta(hours=20)
        if not orari_temp or datetime.fromisoformat(orari_temp[-1]) < target_dt: usa_seamless = True
    except Exception as e:
        print(f"⚠️ Errore ICON-CH2: {e}. Fallback Seamless...")
        usa_seamless = True

    if usa_seamless:
        try:
            params_seamless = base_params.copy()
            params_seamless["models"] = "icon_seamless"
            dati_eps = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params=params_seamless)
        except Exception as e:
            print(f"❌ Errore Seamless: {e}")
            return

    # Recupero Qualità dell'aria (AQ)
    h_aq = {}
    try:
        dati_aq = scarica_dati_con_retry("https://air-quality-api.open-meteo.com/v1/air-quality", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "pm10,pm2_5",
            "timezone": "Europe/Rome",
            "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
            "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
        })
        h_aq = dati_aq.get('hourly', {})
    except Exception as e:
        print(f"⚠️ Errore API Qualità Aria: {e}")

    aq_dict = {}
    for idx_aq, t_aq in enumerate(h_aq.get('time', [])):
        aq_dict[t_aq] = {
            'pm10': h_aq.get('pm10', [])[idx_aq] if idx_aq < len(h_aq.get('pm10', [])) else 0,
            'pm25': h_aq.get('pm2_5', [])[idx_aq] if idx_aq < len(h_aq.get('pm2_5', [])) else 0
        }

    h_eps = dati_eps.get('hourly', {})
    d_eps = dati_eps.get('daily', {})
    orari = h_eps.get('time', [])
    if not orari: return

    giorni_time = d_eps.get('time', [])
    dati_giorni = {g: {
        't_min': 100, 'ora_t_min': None, 't_max': -100, 'ora_t_max': None,
        'rain_sum': 0.0, 'snow_sum': 0.0, 'max_snow_depth': 0.0,
        'livello_disagio_max': -1, 'stringa_disagio': "", 'ora_disagio_max': None,
        'w_gst_max': -1, 'ora_w_gst_max': None, 'ora_inizio_vento': None, 'ora_fine_vento': None,
        'ha_precip': False, 'ora_inizio_p': None, 'ora_fine_p': None, 'picco_p_mm': -1, 'ora_picco_p': None, 'prob_max_p': 0, 'tipo_p': "",
        'sole_mattino': [], 'sole_pomeriggio': [], 'cielo_mattino': "", 'cielo_pomeriggio': "",
        'gelate': set(), 'nebbie': set(), 'aq_level': 0
    } for g in [2, 3, 4]}

    for d_idx, d_str in enumerate(giorni_time):
        d_dt = datetime.fromisoformat(d_str)
        giorno_idx = (d_dt.date() - dt_oggi.date()).days
        if giorno_idx in dati_giorni:
            dati_giorni[giorno_idx]['rain_sum'] = media_lista_float([d_eps[k][d_idx] for k in d_eps if k.startswith('rain_sum_member')])
            dati_giorni[giorno_idx]['snow_sum'] = media_lista_float([d_eps[k][d_idx] for k in d_eps if k.startswith('snowfall_sum_member')])

    indici_validi = [i for i, t in enumerate(orari) if 2 <= (datetime.fromisoformat(t).date() - dt_oggi.date()).days <= 4 and not ((datetime.fromisoformat(t).date() - dt_oggi.date()).days == 4 and datetime.fromisoformat(t).hour > 20)]

    for i in indici_validi:
        ora_dt = datetime.fromisoformat(orari[i])
        ora_solare = ora_dt.hour
        giorno_idx = (ora_dt.date() - dt_oggi.date()).days
        if giorno_idx not in dati_giorni: continue
        
        g_data = dati_giorni[giorno_idx]
        
        # Qualità dell'aria oraria
        pm10_val = aq_dict.get(orari[i], {}).get('pm10')
        pm25_val = aq_dict.get(orari[i], {}).get('pm25')
        if pm10_val is None: pm10_val = 0
        if pm25_val is None: pm25_val = 0
        
        if pm10_val > 100 or pm25_val > 50:
            g_data['aq_level'] = 2
        elif (pm10_val > 51 or pm25_val > 36) and g_data['aq_level'] < 2:
            g_data['aq_level'] = 1

        t_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('temperature_2m_member')])
        dew_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('dew_point_2m_member')])
        ur_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('relative_humidity_2m_member')])
        app_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('apparent_temperature_member')])
        w_gst_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('wind_gusts_10m_member')])
        rain_media = media_lista_float([h_eps[k][i] for k in h_eps if k.startswith('rain_member')])
        snow_media = media_lista_float([h_eps[k][i] for k in h_eps if k.startswith('snowfall_member')])
        snow_depth_media = media_lista_float([h_eps[k][i] for k in h_eps if k.startswith('snow_depth_member')])
        cape_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('cape_member')])
        sun_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('sunshine_duration_member')])
        
        prec_tot_media = rain_media + snow_media
        prec_tot_membri = [r + s for r, s in zip([h_eps[k][i] for k in h_eps if k.startswith('rain_member')], [h_eps[k][i] for k in h_eps if k.startswith('snowfall_member')]) if r is not None and s is not None]
        pct_1mm = percentuale_superamento(prec_tot_membri, 1.0)
        
        sun_pct = (sun_media / 3600.0) * 100
        if 7 <= ora_solare <= 12: g_data['sole_mattino'].append(sun_pct)
        elif 13 <= ora_solare <= 18: g_data['sole_pomeriggio'].append(sun_pct)
        
        if t_media < g_data['t_min']: g_data['t_min'], g_data['ora_t_min'] = t_media, ora_solare
        if t_media > g_data['t_max']: g_data['t_max'], g_data['ora_t_max'] = t_media, ora_solare
            
        if estate: str_dis, liv_dis = calcola_disagio_caldo(t_media, dew_media)
        else: str_dis, liv_dis = calcola_disagio_freddo(app_media)
        if liv_dis > g_data['livello_disagio_max']: g_data['livello_disagio_max'], g_data['stringa_disagio'], g_data['ora_disagio_max'] = liv_dis, str_dis, ora_solare

        # VENTO E TRACCIAMENTO INTENSIFICAZIONE (Soglia approfondimento: 50 km/h)
        if w_gst_media > g_data['w_gst_max']: 
            g_data['w_gst_max'] = w_gst_media
            g_data['ora_w_gst_max'] = ora_solare
            
        if w_gst_media >= 50:
            if g_data['ora_inizio_vento'] is None: g_data['ora_inizio_vento'] = ora_solare
            g_data['ora_fine_vento'] = ora_solare # Estende continuamente il termine
                
        if snow_depth_media > g_data['max_snow_depth']: g_data['max_snow_depth'] = snow_depth_media

        is_instabilita_estiva = (estate and cape_media > 200)
        prob_soglia = 15 if is_instabilita_estiva else 50
        
        if pct_1mm >= prob_soglia:
            g_data['ha_precip'] = True
            if g_data['ora_inizio_p'] is None: g_data['ora_inizio_p'] = ora_solare
            g_data['ora_fine_p'] = ora_solare 
            if pct_1mm > g_data['prob_max_p']: g_data['prob_max_p'] = int(round(pct_1mm))
            if prec_tot_media >= g_data['picco_p_mm']: 
                g_data['picco_p_mm'], g_data['ora_picco_p'] = prec_tot_media, ora_solare
                if snow_media > rain_media and snow_media > 0.5: g_data['tipo_p'] = "nevicate"
                elif is_instabilita_estiva: g_data['tipo_p'] = "rovesci o temporali"
                elif estate: g_data['tipo_p'] = "rovesci"
                else: g_data['tipo_p'] = "piogge"

        if abs(dew_media - t_media) <= 1 and ur_media >= 95 and w_gst_media < 15: g_data['nebbie'].add(ottieni_fascia_oraria(ora_solare))
        if ora_solare >= 22 or ora_solare <= 8:
            if t_media <= -4 and ur_media >= 50: g_data['gelate'].add(f"forti gelate {ottieni_fascia_oraria(ora_solare)}")
            elif -4 < t_media <= -1 and ur_media >= 60: g_data['gelate'].add(f"gelate diffuse {ottieni_fascia_oraria(ora_solare)}")
            elif -1 < t_media <= 1 and t_media <= 0 and ur_media >= 55: g_data['gelate'].add(f"lievi gelate {ottieni_fascia_oraria(ora_solare)}")

    for g in [2, 3, 4]:
        for fascia in ['mattino', 'pomeriggio']:
            lista_sole = dati_giorni[g][f'sole_{fascia}']
            avg_sun = sum(lista_sole) / len(lista_sole) if lista_sole else 0
            if avg_sun >= 80: cielo = "sereno"
            elif avg_sun >= 60: cielo = "poco nuvoloso"
            elif avg_sun >= 40: cielo = "parzialmente nuvoloso"
            elif avg_sun >= 20: cielo = "irregolarmente nuvoloso"
            else: cielo = "molto nuvoloso o coperto"
            dati_giorni[g][f'cielo_{fascia}'] = cielo

    oggi_str = formatta_data_it(dt_oggi)
    giorni_str = {2: formatta_data_it(dt_oggi + timedelta(days=2)), 3: formatta_data_it(dt_oggi + timedelta(days=3)), 4: formatta_data_it(dt_oggi + timedelta(days=4))}

    testo_per_ia = ""
    for g in [2, 3, 4]:
        dg = dati_giorni[g]
        testo_per_ia += f"GIORNO: {giorni_str[g]}\n"
        
        testo_per_ia += f"- Temp Minima: {round(dg['t_min'])}°C"
        if dg['ora_t_min'] is not None and dg['ora_t_min'] >= 10: testo_per_ia += f" (raggiunta insolitamente verso le {dg['ora_t_min']}, {ottieni_fascia_oraria(dg['ora_t_min'])})\n"
        else: testo_per_ia += "\n"
            
        testo_per_ia += f"- Temp Massima: {round(dg['t_max'])}°C"
        if dg['ora_t_max'] is not None and (dg['ora_t_max'] < 13 or dg['ora_t_max'] >= 19): testo_per_ia += f" (raggiunta insolitamente verso le {dg['ora_t_max']}, {ottieni_fascia_oraria(dg['ora_t_max'])})\n"
        else: testo_per_ia += "\n"
        
        if dg['livello_disagio_max'] > 0:
            testo_per_ia += f"- Picco di disagio termico: ({pulisci_disagio(dg['stringa_disagio'])}) registrato {ottieni_fascia_oraria(dg['ora_disagio_max'])}\n"
            
        testo_per_ia += f"- Cielo prevalente al mattino: {dg['cielo_mattino']}\n- Cielo prevalente al pomeriggio: {dg['cielo_pomeriggio']}\n"
        
        if dg['ha_precip']:
            testo_per_ia += f"- Precipitazioni: previste {dg['tipo_p']} con probabilità massima del {dg['prob_max_p']}%.\n"
            testo_per_ia += f"  Inizio {ottieni_fascia_oraria(dg['ora_inizio_p'])}, termine {ottieni_fascia_oraria(dg['ora_fine_p'])} con picco di intensità {ottieni_fascia_oraria(dg['ora_picco_p'])}.\n"
            if dg['tipo_p'] == "nevicate" and dg['snow_sum'] > 0:
                testo_per_ia += f"  Accumulo totale nevoso stimato: circa {arrotonda_tondo(dg['snow_sum'])} cm. "
                if dg['max_snow_depth'] > 0: testo_per_ia += f"Deposito massimo previsto al suolo: circa {arrotonda_tondo(dg['max_snow_depth'])} cm.\n"
                else: testo_per_ia += "\n"
            elif dg['rain_sum'] > 1.0 and not estate:
                testo_per_ia += f"  Accumulo pluviometrico giornaliero stimato: circa {arrotonda_tondo(dg['rain_sum'])} mm.\n"
            
            int_prec = "forti" if dg['picco_p_mm'] > 5 else ("moderate" if dg['picco_p_mm'] >= 2 else "deboli")
            testo_per_ia += f"  Intensità massima stimata come {int_prec} (circa {arrotonda_tondo(dg['picco_p_mm'])} mm/h).\n"
            
        if dg['w_gst_max'] >= 50:
            int_vento = "tempestosa" if dg['w_gst_max'] >= 70 else "forte"
            txt_vento = f"- Vento: ventilazione {int_vento}."
            if dg['ora_inizio_vento'] != dg['ora_fine_vento']:
                txt_vento += f" Intensificazione a partire da {ottieni_fascia_oraria(dg['ora_inizio_vento'])} (ore {dg['ora_inizio_vento']}), in attenuazione {ottieni_fascia_oraria(dg['ora_fine_vento'])} (ore {dg['ora_fine_vento']})."
            else:
                txt_vento += f" Breve rinforzo isolato {ottieni_fascia_oraria(dg['ora_inizio_vento'])} (ore {dg['ora_inizio_vento']})."
            txt_vento += f" La media degli scenari indica raffiche massime {ottieni_fascia_oraria(dg['ora_w_gst_max'])} attorno ai {arrotonda_tondo(dg['w_gst_max'])} km/h."
            testo_per_ia += txt_vento + "\n"
        elif dg['w_gst_max'] >= 30:
            testo_per_ia += "- Vento: ventilazione modesta.\n"
        else:
            testo_per_ia += "- Vento: ventilazione blanda.\n"
            
        if dg['gelate']: testo_per_ia += f"- Pericolo gelo: {', '.join(dg['gelate'])}\n"
        if dg['nebbie']: testo_per_ia += f"- Rischio nebbia nelle seguenti fasce orarie: {', '.join(dg['nebbie'])}\n"
        
        if dg['aq_level'] == 2:
            testo_per_ia += "- Attenzione l'aria sarà molto inquinata 🟣.\n"
        elif dg['aq_level'] == 1:
            testo_per_ia += "- Attenzione, l'aria sarà inquinata 🔴.\n" 
            
        testo_per_ia += "\n"

    bollettino_finale = interpella_groq(testo_per_ia, oggi_str, giorni_str)
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        if bollettino_finale.startswith("Errore"): print(f"Blocco Telegram per errore API: {bollettino_finale}")
        else:
            risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "HTML"})
            if risposta_tg.status_code == 200:
                print("Bollettino inviato!")
                with open(FILE_LOCK, "w") as f: f.write(oggi_str_lock)
            else: print(f"Errore Telegram: {risposta_tg.text}")
    else:
        print("Mancano credenziali Telegram. Stampo a video:\n" + "-"*50 + "\n" + bollettino_finale)

if __name__ == "__main__":
    main()
