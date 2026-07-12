#!/usr/bin/env python3
import os
import requests
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

def interpella_gemini(dati_tendenza):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-3-flash-preview')    

    prompt = f"""
    Sei un meteorologo professionista. Scrivi una PANORAMICA SINTETICA (tendenza meteo a medio termine) per Rivoli (TO) per i prossimi giorni.
    
    TITOLO OBBLIGATORIO:
    Inizia il testo ESATTAMENTE con questo titolo in grassetto: **Aggiornamento meteo a medio termine**
    (Non aggiungere "Ecco la tendenza" o altre frasi prima del titolo).

    REGOLE DI SCRITTURA (TENDENZA SETTIMANALE):
    1. NON usare elenchi puntati. Scrivi un singolo paragrafo fluido, sintetico e professionale.
    2. Unisci i concetti: non fare una meccanica cronaca giorno per giorno, ma raggruppa le tendenze (es. "tra mercoledì e giovedì avremo una fase stabile, mentre da venerdì le temperature caleranno...").
    
    REGOLA PRECIPITAZIONI E STAGIONALITÀ (CRITICA):
    3. Analizza la colonna 'Probabilità Pioggia'. Se indica 'Assente', IGNORA TOTALMENTE il tema della pioggia per quel periodo.
       - Tra MARZO e OTTOBRE usa "rovesci" o "temporali".
       - Tra NOVEMBRE e FEBBRAIO usa "piogge" o "precipitazioni" (vietato parlare di temporali).
       
    REGOLE DI DISAGIO TERMICO E WIND CHILL (SINTESI):
    4. NON calcolare nulla in autonomia. Ricopia testualmente le diciture presenti nei dati (es. "(disagio moderato 🟠)" o "(freddo pungente causa vento)").
       - L'indicazione estiva va ESCLUSIVAMENTE riferita alle temperature massime/ore centrali.
       - L'indicazione del freddo pungente va ESCLUSIVAMENTE riferita alle minime/nottate.
       - Integra i disagi nel discorso fluido senza spiegarne il motivo tecnico.

    DIVIETO ASSOLUTO SUI TERMINI TECNICI:
    5. È severamente VIETATO menzionare i nomi delle colonne ("T.Min", "T.Max", "Probabilità"). Traduci i numeri in un discorso naturale e scorrevole.

    DATI SINTETICI GIORNALIERI (Temperature, Disagio e Precipitazioni):
    {dati_tendenza}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.4})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def estrai_membri(daily_data, prefisso_variabile, indice_giorno):
    valori = []
    for key, array_vals in daily_data.items():
        if key.startswith(prefisso_variabile):
            if indice_giorno < len(array_vals) and array_vals[indice_giorno] is not None:
                valori.append(array_vals[indice_giorno])
    return valori

def main():
    # 1. Dati orari deterministici (Necessari per valutare i picchi di Dew Point e Wind Chill in giornata)
    dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,dew_point_2m,wind_speed_10m",
        "models": "icon_seamless",
        "timezone": "Europe/Rome", "forecast_days": 7
    }).json()

    # 2. Dati Ensemble Giornalieri (icon_seamless raggruppa tutti i membri per le proiezioni a più giorni)
    dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
        "latitude": LAT, "longitude": LON,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "models": "icon_seamless",
        "timezone": "Europe/Rome", "forecast_days": 7
    }).json()

    daily = dati_eps.get('daily', {})
    date_array = daily.get('time', [])
    
    hourly_det = dati_det.get('hourly', {})
    h_temp = hourly_det.get('temperature_2m', [])
    h_dew = hourly_det.get('dew_point_2m', [])
    h_wind = hourly_det.get('wind_speed_10m', [])

    report = "Giorno | T.Min | T.Max | Probabilità Pioggia | Vento Max\n"
    
    is_summer = 5 <= datetime.now().month <= 10

    def formatta_disagio(score):
        if score == 2: return " (forte disagio 🔴)" if is_summer else ""
        if score == 1: return " (disagio moderato 🟠)" if is_summer else ""
        return " (assenza di disagio 🟢)" if is_summer else ""

    # Saltiamo oggi e domani (indici 0 e 1), analizziamo dal terzo giorno in poi (indici 2 fino a 6)
    for i in range(2, len(date_array)): 
        data_obj = datetime.strptime(date_array[i], "%Y-%m-%d")
        giorno_str = formatta_data_it(data_obj)
        
        # --- CALCOLO MEDIE TEMPERATURE E VENTO ---
        t_min_mem = estrai_membri(daily, "temperature_2m_min_member", i)
        t_max_mem = estrai_membri(daily, "temperature_2m_max_member", i)
        vento_mem = estrai_membri(daily, "wind_speed_10m_max_member", i)
        
        t_min_avg = round(sum(t_min_mem) / len(t_min_mem)) if t_min_mem else 0
        t_max_avg = round(sum(t_max_mem) / len(t_max_mem)) if t_max_mem else 0
        vento_avg = round(sum(vento_mem) / len(vento_mem)) if vento_mem else 0

        # --- CALCOLO PROBABILITÀ PRECIPITAZIONI ---
        prec_mem = estrai_membri(daily, "precipitation_sum_member", i)
        
        p1 = (sum(1 for v in prec_mem if v >= 1) / len(prec_mem) * 100) if prec_mem else 0
        p3 = (sum(1 for v in prec_mem if v >= 3) / len(prec_mem) * 100) if prec_mem else 0
        p5 = (sum(1 for v in prec_mem if v >= 5) / len(prec_mem) * 100) if prec_mem else 0

        prob_str = "Assente"
        if p1 >= 10:
            def livello(p):
                if p >= 30: return "Serio rischio"
                if p >= 20: return "Probabile"
                return "Minima possibilità"

            if p5 >= 10: prob_str = f"{livello(p5)} pioggia intensa o instabilità diffusa"
            elif p3 >= 10: prob_str = f"{livello(p3)} pioggia moderata o instabilità sparsa"
            else: prob_str = f"{livello(p1)} pioggia debole o instabilità isolata"

        # --- CALCOLO DISAGIO TERMICO E WIND CHILL (Scansione oraria deterministica del giorno) ---
        disagio_score_max = 0
        wind_chill_flag = False
        
        start_hour = i * 24
        end_hour = start_hour + 24
        
        for h in range(start_hour, end_hour):
            if h < len(h_temp):
                t_val = h_temp[h]
                d_val = h_dew[h]
                w_val = h_wind[h]
                
                # Valutazione Disagio Termico
                if t_val is not None and d_val is not None:
                    d_score = 0
                    if (t_val >= 32 and d_val >= 20) or (t_val >= 30 and d_val >= 24): d_score = 2
                    elif (t_val >= 28 and d_val >= 15) or (t_val >= 25 and d_val >= 20): d_score = 1
                    disagio_score_max = max(disagio_score_max, d_score)
                
                # Valutazione Wind Chill
                if t_val is not None and w_val is not None:
                    if t_val <= 8 and w_val >= 15:
                        wind_chill_flag = True

        str_disagio = formatta_disagio(disagio_score_max)
        str_wc = " (freddo pungente causa vento)" if wind_chill_flag else ""

        # Aggiunta riga alla tabella da fornire a Gemini
        report += f"{giorno_str} | Min {t_min_avg}°C{str_wc} | Max {t_max_avg}°C{str_disagio} | {prob_str} | {vento_avg} km/h\n"

    tendenza = interpella_gemini(report)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": tendenza, "parse_mode": "Markdown"})
        
        if risposta_tg.status_code == 200:
            print("Tendenza settimanale inviata con successo al canale!")
        else:
            print(f"ERRORE TELEGRAM: {risposta_tg.text}")
    else:
        print("Errore: Token o Chat ID mancanti.")

if __name__ == "__main__":
    main()
