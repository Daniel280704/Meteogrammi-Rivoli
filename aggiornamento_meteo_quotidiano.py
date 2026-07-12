#!/usr/bin/env python3
import os
import requests
from datetime import datetime, timedelta

# Disabilita i warning se usi librerie non aggiornate, importa genai
import google.generativeai as genai

# Coordinate di Rivoli (TO) impostate dal tuo script originale
LAT = 45.073443
LON = 7.543472

# Dizionari per le date in italiano
GIORNI_IT = {0: "lunedì", 1: "martedì", 2: "mercoledì", 3: "giovedì", 4: "venerdì", 5: "sabato", 6: "domenica"}
MESI_IT = {1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno", 
           7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"}

def formatta_data_it(dt):
    """Formatta la data in italiano es: domenica 12 luglio"""
    return f"{GIORNI_IT[dt.weekday()]} {dt.day} {MESI_IT[dt.month]}"

def gradi_a_direzione(gradi):
    """Converte i gradi del vento nei punti cardinali standard"""
    if gradi is None: return "N/A"
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'N']
    return dirs[int(round(gradi / 45.0)) % 8]

def descrivi_velocita_vento(kmh):
    """Nomenclatura standard per la velocità media del vento (Scala Beaufort semplificata)"""
    if kmh < 5: return "bava di vento / assente"
    elif kmh < 12: return "vento debole"
    elif kmh < 28: return "vento moderato"
    elif kmh < 49: return "vento forte"
    else: return "vento burrascoso"

def calcola_disagio_caldo(t_aria, dew_point):
    """Calcola il disagio estivo basato sulla relazione tra Temp e Dew Point (es. Indice Thom/Humidex)"""
    # Formula empirica semplificata per il disagio
    if t_aria >= 34 or dew_point >= 24: return "disagio estremo (ELEVATO PERICOLO)"
    elif t_aria >= 32 or dew_point >= 22: return "disagio forte"
    elif t_aria >= 30 or dew_point >= 20: return "disagio marcato"
    elif t_aria >= 27 or dew_point >= 18: return "disagio lieve"
    return "nessun disagio"

def calcola_disagio_freddo(windchill):
    """Valuta il disagio da freddo in base al Wind Chill (temperatura apparente)"""
    if windchill < -10: return "disagio estremo da freddo"
    elif windchill < -5: return "disagio forte da freddo"
    elif windchill < 0: return "disagio marcato da freddo"
    elif windchill < 5: return "disagio lieve da freddo"
    return "nessun disagio"

def media_lista(lista):
    """Calcola la media arrotondata all'intero di una lista di valori, ignorando i None"""
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return int(round(sum(valori_validi) / len(valori_validi)))

def interpella_gemini(dati_testuali, oggi_str, domani_str):
    """Invia il testo pre-calcolato a Gemini per la stesura finale discorsiva"""
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-1.5-flash') # Modello aggiornato consigliato
    
    prompt = f"""
    Sei un meteorologo. Il tuo UNICO compito è prendere i dati orari e giornalieri forniti qui sotto e trasformarli in un testo fluido e discorsivo.
    NON devi inventare nulla, NON devi fare calcoli. Leggi gli eventi che ho già calcolato e uniscili in un discorso.
    
    Regole ferree:
    1. Il testo DEVE iniziare esattamente con: **Aggiornamento meteo di {oggi_str}**
    2. Lascia una riga vuota dopo il titolo.
    3. Scrivi esattamente due paragrafi: uno per la giornata odierna ({oggi_str}) e uno per domani ({domani_str}).
    4. Fai una descrizione fluida, unendo gli eventi orari. Esempio: "La giornata inizia serena con minime di 19°C. Nel pomeriggio passaggio a nubi sparse con possibili temporali attorno alle 16-19..."
    5. Quando citi l'ora, usa SOLO il numero intero (es. "alle 16" o "tra le 16 e le 18"), MAI i minuti (vietato scrivere "16:00").
    6. Inserisci le indicazioni sui disagi (caldo/freddo) esattamente come le trovi nei dati forniti.
    
    DATI PRE-CALCOLATI DA TRASFORMARE IN TESTO:
    {dati_testuali}
    """
    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.2})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    mese_corrente = datetime.now().month
    inverno = mese_corrente in [11, 12, 1, 2, 3]
    estate = mese_corrente in [5, 6, 7, 8, 9, 10]
    
    # 1. RECUPERO DATI MODELLI (Deterministico D2, EPS D2, EPS CH2)
    # Richiediamo dati di superficie e in quota (fino a 800hPa ~ 2000m) per le inversioni
    try:
        # ICON-D2 Deterministico (per vento, direzione, upper air e CAPE)
        dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "wind_direction_10m,cape,sunshine_duration,apparent_temperature,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
            "daily": "sunrise,sunset",
            "models": "icon_d2",
            "timezone": "Europe/Rome", "forecast_days": 2
        }, timeout=10).json()

        # ICON-D2 Ensemble (Media Scenari)
        dati_eps_d2 = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m",
            "models": "icon_d2",
            "timezone": "Europe/Rome", "forecast_days": 2
        }, timeout=10).json()
        
        # ICON-CH2 Ensemble (Media Scenari) - Gestiamo un possibile errore se non disponibile
        ch2_disponibile = True
        try:
            dati_eps_ch2 = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "precipitation",
                "models": "icon_ch2",
                "timezone": "Europe/Rome", "forecast_days": 2
            }, timeout=10).json()
        except:
            ch2_disponibile = False
            
    except Exception as e:
        print(f"Errore fatale nel recupero dati Open-Meteo: {e}")
        return

    # Estrazione array orari
    h_det = dati_det.get('hourly', {})
    h_eps_d2 = dati_eps_d2.get('hourly', {})
    h_eps_ch2 = dati_eps_ch2.get('hourly', {}) if ch2_disponibile else {}
    orari = h_det.get('time', [])
    
    # Orari di alba e tramonto per il calcolo della nuvolosità
    sunrise_str = dati_det.get('daily', {}).get('sunrise', [])
    sunset_str = dati_det.get('daily', {}).get('sunset', [])

    # Strutture dati per raccogliere la sintesi da inviare a Gemini
    sintesi_oggi = []
    sintesi_domani = []
    t_min_oggi, t_max_oggi = 100, -100
    t_min_domani, t_max_domani = 100, -100
    
    # Variabili per memorizzare il dew_point precedente (per il calcolo del Föhn)
    dew_point_prev = None

    # CICLO SULLE 48 ORE PREVISTE
    for i in range(len(orari)):
        ora_dt = datetime.fromisoformat(orari[i])
        ora_solare = ora_dt.hour
        
        giorno_idx = 0 if i < 24 else 1 # 0 = Oggi, 1 = Domani
        
        # --- ESTRAZIONE E CALCOLO MEDIE SCENARI (ICON-D2) ---
        t_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('temperature_2m_member')]
        t_media = media_lista(t_membri)
        
        dew_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('dew_point_2m_member')]
        dew_media = media_lista(dew_membri)
        
        ur_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('relative_humidity_2m_member')]
        ur_media = media_lista(ur_membri)
        
        w_spd_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('wind_speed_10m_member')]
        w_spd_media = media_lista(w_spd_membri)
        
        w_gst_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('wind_gusts_10m_member')]
        w_gst_media = media_lista(w_gst_membri)
        
        # Vento: Direzione dal deterministico, classificazione velocità
        w_dir = h_det.get('wind_direction_10m', [])[i]
        w_dir_str = gradi_a_direzione(w_dir)
        vento_tipo = descrivi_velocita_vento(w_spd_media)
        
        # --- PRECIPITAZIONI: INCROCIO EPS D2, DET D2 e EPS CH2 ---
        prec_eps_d2_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('precipitation_member')]
        prec_eps_d2_media = sum([v for v in prec_eps_d2_membri if v is not None]) / len(prec_eps_d2_membri) if prec_eps_d2_membri else 0
        prec_det_d2 = h_det.get('precipitation', [])[i] if 'precipitation' in h_det else prec_eps_d2_media # Fallback se assente
        
        prec_eps_ch2_media = 0
        if ch2_disponibile:
            prec_eps_ch2_membri = [h_eps_ch2[k][i] for k in h_eps_ch2 if k.startswith('precipitation_member')]
            if prec_eps_ch2_membri:
                prec_eps_ch2_media = sum([v for v in prec_eps_ch2_membri if v is not None]) / len(prec_eps_ch2_membri)

        # Valutazione probabilità base
        prob_maggiorata = prec_eps_d2_media > prec_det_d2
        
        # Controllo della convergenza dei modelli (soglie 1mm, 3mm, 5mm)
        instabilita = "assente"
        if ch2_disponibile:
            condizione = (prec_eps_d2_media >= 1) and (prec_det_d2 >= 1) and (prec_eps_ch2_media >= 1)
        else:
            condizione = (prec_eps_d2_media >= 1) and (prec_det_d2 >= 1)

        mm_max = max(prec_eps_d2_media, prec_det_d2, prec_eps_ch2_media)
        
        if condizione:
            if mm_max >= 5: instabilita = "spiccata instabilità"
            elif mm_max >= 3: instabilita = "marcata instabilità"
            else: instabilita = "possibile instabilità"

        # Tipi di precipitazione (Neve / Inversione Termica / Temporali)
        tipo_prec = ""
        if instabilita != "assente":
            if inverno:
                if t_media < 2:
                    # Controllo termico in quota per l'inversione
                    strati_quota = [
                        h_det.get('temperature_1000hPa', [])[i], h_det.get('temperature_975hPa', [])[i],
                        h_det.get('temperature_950hPa', [])[i], h_det.get('temperature_925hPa', [])[i],
                        h_det.get('temperature_900hPa', [])[i], h_det.get('temperature_850hPa', [])[i],
                        h_det.get('temperature_800hPa', [])[i]
                    ]
                    inversione_presente = any(t > 1 for t in strati_quota if t is not None)
                    
                    if inversione_presente:
                        if t_media > 0: tipo_prec = "pioggia (a causa di inversione termica in quota)"
                        else: tipo_prec = "PERICOLO PIOGGIA CONGELANTE (Gelicidio per inversione termica)"
                    else:
                        tipo_prec = "neve"
                else:
                    tipo_prec = "pioggia"
            else:
                # Da Aprile a Ottobre: Temporali vs Rovesci tramite CAPE
                cape = h_det.get('cape', [])[i] if h_det.get('cape') else 0
                if cape > 400: tipo_prec = "temporale"
                else: tipo_prec = "rovesci"

        # --- EVENTI DI VENTO (Föhn, Umido Orientale, Outflow) ---
        vento_evento = ""
        if dew_point_prev is not None:
            crollo_dew = dew_point_prev - dew_media >= 2 # Crollo di 2°C in un'ora
            if w_dir_str in ['NW', 'N', 'W'] and w_gst_media > 25 and crollo_dew:
                vento_evento = "improvviso rinforzo per probabile Föhn"
            elif w_dir_str in ['E', 'NE', 'SE'] and w_gst_media > 20 and not crollo_dew:
                vento_evento = "ventilazione umida orientale"
                
        if not inverno and instabilita == "assente" and w_gst_media > 40:
            vento_evento = "improvvise raffiche (possibile outflow da temporali vicini)"
        elif not inverno and instabilita != "assente" and w_gst_media > 40:
            vento_evento = f"raffiche che accompagnano il {tipo_prec}"
            
        dew_point_prev = dew_media

        # --- NUVOLOSITA' (Basato su Sunshine e alba/tramonto) ---
        # Isoliamo l'alba e tramonto del giorno corrente
        alba = datetime.fromisoformat(sunrise_str[giorno_idx])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx])
        alba_piu_2 = alba + timedelta(hours=2)
        tramonto_meno_2 = tramonto - timedelta(hours=2)
        
        cielo = ""
        if alba_piu_2 <= ora_dt <= tramonto_meno_2:
            sun_minuti = (h_det.get('sunshine_duration', [])[i] or 0) / 60
            if sun_minuti < 5: cielo = "molto nuvoloso o coperto"
            elif sun_minuti <= 15: cielo = "irregolarmente o molto nuvoloso"
            elif sun_minuti <= 30: cielo = "parzialmente o irregolarmente nuvoloso"
            elif sun_minuti <= 45: cielo = "parzialmente nuvoloso"
            elif sun_minuti <= 55: cielo = "poco nuvoloso"
            else: cielo = "sereno"

        # --- NEBBIA ---
        nebbia = ""
        if abs(dew_media - t_media) <= 1 and ur_media >= 95 and w_spd_media < 10:
            nebbia = "possibile formazione di nebbia"

        # --- AGGIORNAMENTO MIN/MAX GIORNALIERE ---
        if giorno_idx == 0:
            t_min_oggi = min(t_min_oggi, t_media)
            t_max_oggi = max(t_max_oggi, t_media)
        else:
            t_min_domani = min(t_min_domani, t_media)
            t_max_domani = max(t_max_domani, t_media)

        # --- COMPILAZIONE RECORD ORARIO ---
        # Costruiamo una stringa che riassume gli eventi di quest'ora se c'è qualcosa di rilevante
        record = f"Ore {ora_solare}: T={t_media}°C."
        if cielo: record += f" Cielo {cielo}."
        if instabilita != "assente": record += f" Rilevata {instabilita} con {tipo_prec}."
        if vento_evento: record += f" {vento_evento}."
        if nebbia: record += f" {nebbia}."
        
        if giorno_idx == 0: sintesi_oggi.append(record)
        else: sintesi_domani.append(record)

    # 2. CALCOLO DISAGI SULLE TEMPERATURE ESTREME DELLA GIORNATA
    # Per semplicità valutiamo il disagio caldo sulle ore centrali e freddo sui valori minimi
    disagio_oggi = ""
    disagio_domani = ""
    
    if estate:
        # Troviamo il Dew point medio nelle ore diurne per il calcolo del disagio max
        dew_max_oggi = media_lista([h_eps_d2[k][14] for k in h_eps_d2 if k.startswith('dew_point_2m_member')])
        dew_max_domani = media_lista([h_eps_d2[k][14+24] for k in h_eps_d2 if k.startswith('dew_point_2m_member')])
        disagio_oggi = f"Disagio termico da caldo: {calcola_disagio_caldo(t_max_oggi, dew_max_oggi)}"
        disagio_domani = f"Disagio termico da caldo: {calcola_disagio_caldo(t_max_domani, dew_max_domani)}"
    elif inverno:
        windchill_min_oggi = min(h_det.get('apparent_temperature', [])[0:24])
        windchill_min_domani = min(h_det.get('apparent_temperature', [])[24:48])
        disagio_oggi = f"Disagio termico da freddo: {calcola_disagio_freddo(windchill_min_oggi)}"
        disagio_domani = f"Disagio termico da freddo: {calcola_disagio_freddo(windchill_min_domani)}"

    # 3. ASSEMBLAGGIO TESTO PER GEMINI
    dt_oggi = datetime.now()
    dt_domani = dt_oggi + timedelta(days=1)
    oggi_str = formatta_data_it(dt_oggi)
    domani_str = formatta_data_it(dt_domani)

    testo_per_ia = f"""
    GIORNO 1: {oggi_str}
    Temperatura Minima: {t_min_oggi}°C
    Temperatura Massima: {t_max_oggi}°C
    {disagio_oggi}
    Cronistoria eventi:
    {chr(10).join(sintesi_oggi)}

    GIORNO 2: {domani_str}
    Temperatura Minima: {t_min_domani}°C
    Temperatura Massima: {t_max_domani}°C
    {disagio_domani}
    Cronistoria eventi:
    {chr(10).join(sintesi_domani)}
    """

    # 4. CHIAMATA A GEMINI E INVIO TELEGRAM
    bollettino_finale = interpella_gemini(testo_per_ia, oggi_str, domani_str)
    
    # Mantengo intatto il tuo codice originale per Telegram[cite: 1]
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "Markdown"})
        if risposta_tg.status_code == 200:
            print("Bollettino inviato con successo!")
        else:
            print(f"Errore Telegram: {risposta_tg.text}")
    else:
        print("Errore: Token o Chat ID mancanti! Stampo a video:")
        print("-------------------------------------------------")
        print(bollettino_finale)

if __name__ == "__main__":
    main()
