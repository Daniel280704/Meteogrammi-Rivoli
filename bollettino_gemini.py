#!/usr/bin/env python3
import os
import requests
import sys
import google.generativeai as genai
from datetime import datetime, timedelta

LAT = 45.073443
LON = 7.543472

# Dizionari per forzare l'italiano senza dipendere dal sistema operativo
GIORNI_IT = {0: "lunedì", 1: "martedì", 2: "mercoledì", 3: "giovedì", 4: "venerdì", 5: "sabato", 6: "domenica"}
MESI_IT = {1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno", 
           7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"}

def formatta_data_it(dt):
    giorno_sett = GIORNI_IT[dt.weekday()]
    mese = MESI_IT[dt.month]
    return f"{giorno_sett} {dt.day} {mese}"

def gradi_a_direzione(gradi):
    if gradi is None: return "N/A"
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'N']
    ix = int(round(gradi / 45.0))
    return dirs[ix % 8]

def interpella_gemini(dati_meteo, info_giornaliere, oggi_str, domani_str):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-3-flash-preview')    

    prompt = f"""
    Sei un meteorologo professionista. Scrivi un bollettino meteo discorsivo per Rivoli (TO) per le prossime 48 ore.
    
    TITOLO OBBLIGATORIO:
    Inizia il testo ESATTAMENTE con questo titolo in grassetto: **Aggiornamento meteo di {oggi_str}**
    (Non aggiungere "Ecco il bollettino" o altre frasi prima del titolo).

    RIFERIMENTI UFFICIALI (Usa questi valori testualmente per le temperature min/max e disagio):
    {info_giornaliere}

    REGOLE DI SCRITTURA (BOLLETTINO AVANZATO):
    1. NON usare elenchi puntati. Scrivi paragrafi fluidi e professionali.
    2. Usa le temperature min/max fornite nei RIFERIMENTI UFFICIALI come base della narrazione.
    
    REGOLA NUVOLOSITÀ E STATO DEL CIELO:
    3. Analizza la colonna 'Cielo' (precalcolata in base al soleggiamento reale).
       - TASSATIVO: Per le ore contrassegnate come 'Notte' è severamente vietato parlare di nuvolosità o stato del cielo. Ignora totalmente l'argomento per quelle fasce orarie.
       - Per le ore diurne, sii MOLTO CONCISO. Menziona il cielo rapidamente indicando solo lo stato generale o le variazioni significative durante la giornata. Non dilungarti.
    
    REGOLA PRECIPITAZIONI E PROBABILITÀ (CRITICA):
    4. Analizza 'Probabilità'. Se indica 'Assente', IGNORA TOTALMENTE il tema della pioggia.
       - STAGIONALITÀ: Tra MARZO e OTTOBRE usa "rovesci" o "temporali". Tra NOVEMBRE e FEBBRAIO usa "piogge" o "precipitazioni".
       - FORMATO ORARIO: Raggruppa gli orari (es. "tra le 16 e le 21"). Usa solo il numero intero.
    
    REGOLA NEVE E INVERNO (INVERSIONI E WET BULB):
    5. Se sono previste precipitazioni e fa freddo:
       - INVERSIONE/GELICIDIO: Se T suolo <= 1°C ma in ALMENO UNA quota (T_925, T_900, T_850, T_800) la T è > 0°C, c'è inversione termica. NON prevedere neve, avvisa del grave rischio di pioggia congelantesi (gelicidio).
       - BULBO UMIDO: Se l'aria è > 0°C ma Wet_Bulb <= 0°C, annuncia rischio neve per crollo termico da rovesciamento.
       - NEVE: Se Z.Termico basso, T su tutte le quote <= 0°C e Wet Bulb <= 0°C, avvisa probabilità di neve.
       
    REGOLA NEBBIA E GELATE NOTTURNE:
    6. NEBBIA: Se l'UR% > 95% e il vento è calmo (< 5 km/h), segnala possibili foschie o nebbia.
       GELATE: In inverno, se di notte/mattino la T_Media scende a <= 0°C e l'umidità è medio-alta, avvisa rischio gelate/brina.
       
    REGOLA VENTO E RAFFICHE:
    7. REGOLA DEL SILENZIO: Se nella colonna 'Raffiche' NESSUN valore raggiunge o supera i 30 km/h, è ASSOLUTAMENTE VIETATO menzionare il vento o la ventilazione nel bollettino.
       FÖHN/EST: Parlane SOLO se le raffiche superano i 30 km/h (es. Föhn da W/NW con crollo UR% e Dew, oppure flussi umidi da E).
    
    REGOLE DI DISAGIO TERMICO E WIND CHILL:
    8. NON calcolare nulla in autonomia. Ricopia testualmente le diciture dai RIFERIMENTI UFFICIALI:
       - TASSATIVO: L'indicazione estiva (es. "(disagio moderato 🟠)") va ESCLUSIVAMENTE accanto alla T_Massima. Vietato nominarlo per la notte o le minime.
       - TASSATIVO: Il freddo pungente va ESCLUSIVAMENTE accanto alla T_Minima.
       - Non aggiungere spiegazioni personali del fenomeno.
    
    DIVIETO SUI TERMINI TECNICI:
    9. È severamente VIETATO menzionare i nomi delle colonne (come "Cielo", "Wet_Bulb", "T_925hPa", "Dew", "Raffiche").
    
    DATI ANALITICI ORARI (Ora | T | Cielo | UR% | Dew | Prob | Vento | Raff | Dir | Z.Termico | Wet_B | T_925 | T_900 | T_850 | T_800):
    {dati_meteo}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.3})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def estrai_membri(hourly_data, prefisso_variabile, indice_ora):
    valori = []
    for key, lst in hourly_data.items():
        if key.startswith(prefisso_variabile):
            if indice_ora < len(lst) and lst[indice_ora] is not None:
                valori.append(lst[indice_ora])
    return valori

def main():
    # Rimossa la colonna cloud_cover, mantenuto solo sunshine_duration e is_day
    dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,freezinglevel_height,wet_bulb_temperature_2m,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa,wind_direction_10m,wind_gusts_10m,sunshine_duration,is_day",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 2
    }).json()

    dati_eps_d2 = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "models": "icon_d2",
        "timezone": "Europe/Rome", "forecast_days": 2
    }).json()

    dati_eps_ch2 = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "models": "icon_ch2",
        "timezone": "Europe/Rome", "forecast_days": 2
    }).json()

    hourly_det = dati_det.get('hourly', {})
    hourly_d2 = dati_eps_d2.get('hourly', {})
    hourly_ch2 = dati_eps_ch2.get('hourly', {})
    orari = hourly_det.get('time', [])
    
    report = "Ora | T | Cielo | UR% | Dew | Prob | Vento | Raff | Dir | Z.Termico | Wet_B | T_925 | T_900 | T_850 | T_800\n"
    
    temp_oggi = []
    temp_domani = []
    
    disagio_oggi_score = 0
    disagio_domani_score = 0
    
    wind_chill_oggi = False
    wind_chill_domani = False

    t_det_list = hourly_det.get('temperature_2m', [])
    ur_list = hourly_det.get('relative_humidity_2m', [])
    dew_list = hourly_det.get('dew_point_2m', [])
    z_term_list = hourly_det.get('freezinglevel_height', [])
    wet_bulb_list = hourly_det.get('wet_bulb_temperature_2m', [])
    t925_list = hourly_det.get('temperature_925hPa', [])
    t900_list = hourly_det.get('temperature_900hPa', [])
    t850_list = hourly_det.get('temperature_850hPa', [])
    t800_list = hourly_det.get('temperature_800hPa', [])
    wd_list = hourly_det.get('wind_direction_10m', [])
    wg_list = hourly_det.get('wind_gusts_10m', [])
    sun_list = hourly_det.get('sunshine_duration', [])
    is_day_list = hourly_det.get('is_day', [])

    p1_d2_all, p3_d2_all, p5_d2_all = [], [], []
    p1_ch_all, p3_ch_all, p5_ch_all = [], [], []

    def pct(vals, th):
        if not vals: return 0 
        return (sum(1 for v in vals if v >= th) / len(vals)) * 100

    for i in range(48):
        prec_d2 = estrai_membri(hourly_d2, "precipitation_member", i)
        prec_ch2 = estrai_membri(hourly_ch2, "precipitation_member", i)
        
        p1_d2_all.append(pct(prec_d2, 1))
        p3_d2_all.append(pct(prec_d2, 3))
        p5_d2_all.append(pct(prec_d2, 5))
        
        p1_ch_all.append(pct(prec_ch2, 1))
        p3_ch_all.append(pct(prec_ch2, 3))
        p5_ch_all.append(pct(prec_ch2, 5))

    for i in range(48): 
        if i >= len(orari): break

        t_d2_mem = estrai_membri(hourly_d2, "temperature_2m_member", i)
        t_ch2_mem = estrai_membri(hourly_ch2, "temperature_2m_member", i)
        t_det = t_det_list[i] if i < len(t_det_list) else None

        w_d2_mem = estrai_membri(hourly_d2, "wind_speed_10m_member", i)
        w_ch2_mem = estrai_membri(hourly_ch2, "wind_speed_10m_member", i)

        valori_temp = []
        if t_d2_mem: valori_temp.append(sum(t_d2_mem) / len(t_d2_mem))
        if t_ch2_mem: valori_temp.append(sum(t_ch2_mem) / len(t_ch2_mem))
        if t_det is not None: valori_temp.append(t_det)
        
        temp_finale = round(sum(valori_temp) / len(valori_temp)) if valori_temp else 0
        
        valori_vento = []
        if w_d2_mem: valori_vento.append(sum(w_d2_mem) / len(w_d2_mem))
        if w_ch2_mem: valori_vento.append(sum(w_ch2_mem) / len(w_ch2_mem))
        vento_finale = round(sum(valori_vento) / len(valori_vento)) if valori_vento else 0
        
        ur = ur_list[i] if i < len(ur_list) else 0
        dew = dew_list[i] if i < len(dew_list) else 0

        z_term_val = z_term_list[i] if i < len(z_term_list) else "N/A"
        wet_bulb_val = wet_bulb_list[i] if i < len(wet_bulb_list) else "N/A"
        t925_val = t925_list[i] if i < len(t925_list) else "N/A"
        t900_val = t900_list[i] if i < len(t900_list) else "N/A"
        t850_val = t850_list[i] if i < len(t850_list) else "N/A"
        t800_val = t800_list[i] if i < len(t800_list) else "N/A"
        
        wd_val = wd_list[i] if i < len(wd_list) else None
        dir_str = gradi_a_direzione(wd_val)
        wg_val = round(wg_list[i]) if i < len(wg_list) else 0
        
        is_day_val = is_day_list[i] if i < len(is_day_list) else 1
        sun_val = round(sun_list[i] / 60) if (i < len(sun_list) and sun_list[i] is not None) else 0

        # Rilevamento alba e tramonto (Fascia crepuscolare +/- 2 ore)
        is_twilight = False
        if is_day_val == 1:
            for offset in [-2, -1, 1, 2]:
                idx = i + offset
                if 0 <= idx < len(is_day_list) and is_day_list[idx] == 0:
                    is_twilight = True
                    break

        # Logica esclusiva basata sul soleggiamento per lo Stato del Cielo
        if is_day_val == 0 or is_twilight:
            # Notte o crepuscolo: etichettiamo come "Notte" e Gemini ignorerà l'argomento
            cielo_str = "Notte"
        else:
            # Deep Day: classificazione rigorosa sui minuti di sole
            if sun_val >= 50:
                cielo_str = "In prevalenza sereno"
            elif sun_val >= 30:
                cielo_str = "Parzialmente nuvoloso"
            elif sun_val >= 20:
                cielo_str = "Da parzialmente a irregolarmente nuvoloso"
            elif sun_val >= 5:
                cielo_str = "Irregolarmente nuvoloso"
            else:
                cielo_str = "Coperto"

        d_score = 0
        if (temp_finale >= 32 and dew >= 20) or (temp_finale >= 30 and dew >= 24):
            d_score = 2
        elif (temp_finale >= 28 and dew >= 15) or (temp_finale >= 25 and dew >= 20):
            d_score = 1
            
        wc_flag = (temp_finale <= 8 and vento_finale >= 15)

        if i < 24:
            temp_oggi.append(temp_finale)
            disagio_oggi_score = max(disagio_oggi_score, d_score)
            if wc_flag: wind_chill_oggi = True
        else:
            temp_domani.append(temp_finale)
            disagio_domani_score = max(disagio_domani_score, d_score)
            if wc_flag: wind_chill_domani = True

        start_j = max(0, i - 3)
        end_j = min(48, i + 4)
        
        ch2_support_for_d2 = any(p1_ch_all[j] >= 10 for j in range(start_j, end_j))
        d2_support_for_ch = any(p1_d2_all[j] >= 10 for j in range(start_j, end_j))
        
        valido = False
        if p1_d2_all[i] >= 10 and ch2_support_for_d2: valido = True
        if p1_ch_all[i] >= 10 and d2_support_for_ch: valido = True
        if not any(p1_ch_all) and p1_d2_all[i] >= 10: valido = True 

        prob = "Assente"
        if valido:
            max5 = max(p5_d2_all[i], p5_ch_all[i])
            max3 = max(p3_d2_all[i], p3_ch_all[i])
            max1 = max(p1_d2_all[i], p1_ch_all[i])
            
            def livello(p):
                if p >= 30: return "Serio rischio"
                if p >= 20: return "Probabile"
                return "Minima possibilità"

            if max5 >= 10: prob = f"{livello(max5)} pioggia intensa o instabilità diffusa"
            elif max3 >= 10: prob = f"{livello(max3)} pioggia moderata o instabilità sparsa"
            elif max1 >= 10: prob = f"{livello(max1)} pioggia debole o instabilità isolata"

        report += f"{orari[i][-5:]} | {temp_finale}°C | {cielo_str} | {ur}% | {dew}°C | {prob} | {vento_finale} km/h | {wg_val} km/h | {dir_str} | {z_term_val}m | {wet_bulb_val}°C | {t925_val}°C | {t900_val}°C | {t850_val}°C | {t800_val}°C\n"

    is_summer = 5 <= datetime.now().month <= 10

    def formatta_disagio(score):
        if score == 2: return " (forte disagio 🔴)" if is_summer else ""
        if score == 1: return " (disagio moderato 🟠)" if is_summer else ""
        return " (assenza di disagio 🟢)" if is_summer else ""

    dt_oggi = datetime.now()
    dt_domani = dt_oggi + timedelta(days=1)
    
    oggi_str = formatta_data_it(dt_oggi)
    domani_str = formatta_data_it(dt_domani)

    min_oggi, max_oggi = (min(temp_oggi), max(temp_oggi)) if temp_oggi else ("N/A", "N/A")
    min_domani, max_domani = (min(temp_domani), max(temp_domani)) if temp_domani else ("N/A", "N/A")
    
    str_disagio_oggi = formatta_disagio(disagio_oggi_score)
    str_disagio_domani = formatta_disagio(disagio_domani_score)
    
    str_wc_oggi = " (freddo pungente causa vento)" if wind_chill_oggi else ""
    str_wc_domani = " (freddo pungente causa vento)" if wind_chill_domani else ""

    info_giornaliere = f"""
    {oggi_str}: Min {min_oggi}°C{str_wc_oggi}, Max {max_oggi}°C{str_disagio_oggi}
    {domani_str}: Min {min_domani}°C{str_wc_domani}, Max {max_domani}°C{str_disagio_domani}
    """

    bollettino = interpella_gemini(report, info_giornaliere, oggi_str, domani_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino, "parse_mode": "Markdown"})
        print("Bollettino inviato con successo!")
    else:
        print("Errore: Token o Chat ID mancanti!")

if __name__ == "__main__":
    main()
