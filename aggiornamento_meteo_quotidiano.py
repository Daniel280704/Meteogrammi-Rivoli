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
            print(f"⚠️ Errore connessione (Tentativo {tentativo + 1}/{max_retries}): {e}")
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
    elif t_aria >= 38 and dew_point >= 12: return "(disagio forte 🔴)"
    elif t_aria >= 36 and dew_point >= 10: return "(disagio marcato 🟠)"
    elif t_aria >= 32 and dew_point >= 8: return "(disagio lieve 🟡)"
    else: return "(nessun disagio o caldo tollerabile 🟢)"

def calcola_disagio_freddo(windchill):
    if windchill < -40: return "(disagio estremo da freddo 🥶)"
    elif windchill < -25: return "(disagio forte da freddo 🔵)"
    elif windchill < -10: return "(disagio marcato da freddo 🧊)"
    elif windchill < 0: return "(disagio lieve da freddo ❄️)"
    else: return "(nessun disagio o freddo tollerabile 🟢)"

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

def interpella_groq(dati_testuali, oggi_str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "Errore: GROQ_API_KEY non trovata."
        
    client = Groq(api_key=api_key)
    
    prompt = f"""
    Sei un meteorologo professionista, profondo conoscitore del microclima del Piemonte e in particolare della zona di Rivoli (TO). Il tuo compito è redigere un bollettino meteo discorsivo, elegante e autorevole, analizzando i dati orari e le probabilità che ti vengono fornite.

    REGOLE DI RAGIONAMENTO METEOROLOGICO (FONDAMENTALI):
    1. Analisi delle Precipitazioni: Valuta autonomamente il contesto.
       - Se noti piogge pomeridiane/serali associate a valori di CAPE elevati (> 200/300 J/kg), deduci che si tratta di instabilità convettiva. Trattala in modo probabilistico (es. "rischio di temporali di calore", "possibili rovesci convettivi").
       - Se noti precipitazioni prolungate, assenza di CAPE, deduci che è una perturbazione frontale. Parla di "peggioramento", indicando il picco di massima intensità e il tipo (neve se T è < 2°C).
    2. Stima Probabilità: Usa la "Prob. Pioggia" (che ti fornisce la percentuale dei membri ensemble) per citare nel testo un valore probabilistico in caso di fenomeni instabili (es. 40%, 70%).
    3. Dinamiche del Vento: Ignoralo se le raffiche sono sotto i 30 km/h. Se noti raffiche forti da NW, N, W associate a un calo netto del Dew Point, deduci autonomamente l'ingresso di venti di Föhn e comunicalo.
    4. Sintesi del Cielo: Valuta il "Sole" (minuti di soleggiamento su 60). Non fare la telecronaca oraria. Fai una sintesi per fasce (es. "mattinata soleggiata seguita da nuvolosità", oppure "contesto molto nuvoloso o coperto").
    5. Nebbia: Se T e Dew Point sono quasi identici, vento assente, deduci possibile foschia o nebbia notturna.

    REGOLE STILISTICHE E FORMATTAZIONE:
    - TITOLO: Inizia ESATTAMENTE con: <b>Aggiornamento meteo di {oggi_str}</b>.
    - STRUTTURA: Due paragrafi in totale (uno per l'oggi, uno per domani). Lascia una riga vuota tra il titolo e il primo paragrafo, e una riga vuota tra i paragrafi.
    - DIVIETI ASSOLUTI: NON elencare i dati orari. È VIETATO dire espressioni come "nuvolosità parzialmente nuvolosa". È VIETATO dire "nessuna precipitazione", usa "contesto asciutto" o ometti il riferimento. NON usare formattazione markdown (niente asterischi o underscore).
    - Inserisci sempre Minima, Massima e l'emoji del disagio termico fornito.
    
    DATI GIORNALIERI DA ANALIZZARE (deduci le tendenze senza elencarli):
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
    estate = mese_corrente in [5, 6, 7, 8, 9]
    inverno = non estate
    
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
            "hourly": "wind_direction_10m,cape,sunshine_duration",
            "models": "icon_d2", "timezone": "Europe/Rome", "forecast_days": 2
        })
        dati_eps = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,dew_point_2m,apparent_temperature",
            "models": "icon_d2", "timezone": "Europe/Rome", "forecast_days": 2
        })
    except Exception as e:
        print(f"❌ Errore fatale dati Open-Meteo: {e}")
        return

    h_det = dati_det.get('hourly', {})
    h_eps = dati_eps.get('hourly', {})
    orari = h_det.get('time', [])
    
    if not orari: return

    sintesi = {0: [], 1: []}
    t_min = {0: 100, 1: 100}
    t_max = {0: -100, 1: -100}
    app_medie = []

    for i in range(len(orari)):
        ora_dt = datetime.fromisoformat(orari[i])
        giorno_idx = 0 if i < 24 else 1
        
        t_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('temperature_2m_member')])
        dew_media = media_lista([h_eps[k][i] for k in h_eps if k.startswith('dew_point_2m_member')])
        w_spd = media_lista([h_eps[k][i] for k in h_eps if k.startswith('wind_speed_10m_member')])
        w_gst = media_lista([h_eps[k][i] for k in h_eps if k.startswith('wind_gusts_10m_member')])
        prec_memb = [h_eps[k][i] for k in h_eps if k.startswith('precipitation_member')]
        prec_media = media_lista_float(prec_memb)
        prob_prec = percentuale_superamento(prec_memb, 1.0)
        
        w_dir = gradi_a_direzione(h_det.get('wind_direction_10m', [])[i] if h_det.get('wind_direction_10m') else None)
        cape = h_det.get('cape', [])[i] if h_det.get('cape') else 0
        sun = (h_det.get('sunshine_duration', [])[i] or 0) / 60

        app_medie.append(media_lista([h_eps[k][i] for k in h_eps if k.startswith('apparent_temperature_member')]))
        
        t_min[giorno_idx] = min(t_min[giorno_idx], t_media)
        t_max[giorno_idx] = max(t_max[giorno_idx], t_media)

        record = f"Ore {ora_dt.hour:02d}: T={t_media}°C, Dew={dew_media}°C, Pioggia={prec_media}mm (Prob:{prob_prec:.0f}%), CAPE={cape or 0:.0f}J/kg, Vento={w_spd}km/h (Raff:{w_gst}, Dir:{w_dir}), Sole={sun:.0f}min"
        sintesi[giorno_idx].append(record)

    disagio = {0: "", 1: ""}
    for g in [0, 1]:
        if estate:
            dew_h14 = media_lista([h_eps[k][14 + (g*24)] for k in h_eps if k.startswith('dew_point_2m_member')])
            disagio[g] = calcola_disagio_caldo(t_max[g], dew_h14)
        else:
            disagio[g] = calcola_disagio_freddo(min(app_medie[g*24 : (g+1)*24]))

    dt_oggi = datetime.now()
    oggi_str = formatta_data_it(dt_oggi)
    domani_str = formatta_data_it(dt_oggi + timedelta(days=1))

    testo_per_ia = f"""
    GIORNO 1: {oggi_str}
    Estremi Termici: Min {t_min[0]}°C, Max {t_max[0]}°C {disagio[0]}
    Dettaglio Orario:
    {chr(10).join(sintesi[0])}

    GIORNO 2: {domani_str}
    Estremi Termici: Min {t_min[1]}°C, Max {t_max[1]}°C {disagio[1]}
    Dettaglio Orario:
    {chr(10).join(sintesi[1])}
    """

    bollettino_finale = interpella_groq(testo_per_ia, oggi_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "HTML"})
        if risposta_tg.status_code == 200:
            with open(FILE_LOCK, "w") as f: f.write(oggi_str_lock)
    else:
        print(bollettino_finale)

if __name__ == "__main__":
    main()
