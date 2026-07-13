#!/usr/bin/env python3
import os
import sys
import requests
from datetime import datetime, timedelta

import google.generativeai as genai

LAT = 45.07347491421504
LON = 7.543461388723449

GIORNI_IT = {0: "lunedì", 1: "martedì", 2: "mercoledì", 3: "giovedì", 4: "venerdì", 5: "sabato", 6: "domenica"}
MESI_IT = {1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno", 
           7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"}

def formatta_data_it(dt):
    return f"{GIORNI_IT[dt.weekday()]} {dt.day} {MESI_IT[dt.month]}"

def gradi_a_direzione(gradi):
    if gradi is None: return "N/A"
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'N']
    return dirs[int(round(gradi / 45.0)) % 8]

def calcola_disagio_caldo(t_aria, dew_point):
    # =========================================================================
    # 1. DISAGIO ESTREMO 🟣 (Condizioni torride/afose estreme, elevato pericolo)
    # =========================================================================
    if t_aria >= 40 and dew_point >= 15: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"  # Caldo torrido nel deserto
    elif t_aria >= 38 and dew_point >= 18: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 36 and dew_point >= 20: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"  # Afa intensa padana
    elif t_aria >= 34 and dew_point >= 22: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 32 and dew_point >= 24: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"  # Clima tropicale opprimente
    elif t_aria >= 30 and dew_point >= 25: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 28 and dew_point >= 26: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"

    # =========================================================================
    # 2. DISAGIO FORTE 🔴 (Afa molto pesante, limitare gli sforzi fisici)
    # =========================================================================
    elif t_aria >= 38 and dew_point >= 12: return "(disagio forte 🔴)"
    elif t_aria >= 36 and dew_point >= 15: return "(disagio forte 🔴)"
    elif t_aria >= 34 and dew_point >= 18: return "(disagio forte 🔴)"
    elif t_aria >= 32 and dew_point >= 20: return "(disagio forte 🔴)"
    elif t_aria >= 30 and dew_point >= 22: return "(disagio forte 🔴)"
    elif t_aria >= 28 and dew_point >= 24: return "(disagio forte 🔴)"
    elif t_aria >= 26 and dew_point >= 25: return "(disagio forte 🔴)"

    # =========================================================================
    # 3. DISAGIO MARCATO 🟠 (Sensazione netta di calura e compressione)
    # =========================================================================
    elif t_aria >= 36 and dew_point >= 10: return "(disagio marcato 🟠)"
    elif t_aria >= 34 and dew_point >= 13: return "(disagio marcato 🟠)"
    elif t_aria >= 32 and dew_point >= 16: return "(disagio marcato 🟠)"
    elif t_aria >= 30 and dew_point >= 18: return "(disagio marcato 🟠)"
    elif t_aria >= 28 and dew_point >= 20: return "(disagio marcato 🟠)"
    elif t_aria >= 26 and dew_point >= 22: return "(disagio marcato 🟠)"
    elif t_aria >= 24 and dew_point >= 24: return "(disagio marcato 🟠)"

    # =========================================================================
    # 4. DISAGIO LIEVE 🟡 (Primi segnali di fastidio da caldo umido)
    # =========================================================================
    elif t_aria >= 32 and dew_point >= 8: return "(disagio lieve 🟡)"
    elif t_aria >= 30 and dew_point >= 11: return "(disagio lieve 🟡)"
    elif t_aria >= 28 and dew_point >= 13: return "(disagio lieve 🟡)"
    elif t_aria >= 26 and dew_point >= 15: return "(disagio lieve 🟡)"
    elif t_aria >= 24 and dew_point >= 17: return "(disagio lieve 🟡)"
    elif t_aria >= 22 and dew_point >= 19: return "(disagio lieve 🟡)"

    # =========================================================================
    # COMFORT O CALDO SOPPORTABILE 🟢
    # =========================================================================
    else:
        return "(nessun disagio o caldo tollerabile)"

def calcola_disagio_freddo(windchill):
    # =========================================================================
    # 1. DISAGIO ESTREMO (Pericolo immediato di congelamento della pelle esposta in meno di 10 minuti)
    # =========================================================================
    if windchill < -40: return "(disagio estremo da freddo 🥶)"
    
    # =========================================================================
    # 2. DISAGIO FORTE (Rischio elevato di congelamento in 10-30 minuti, brividi violenti)
    # =========================================================================
    elif windchill < -25: return "(disagio forte da freddo 🥶)"
    
    # =========================================================================
    # 3. DISAGIO MARCATO (Freddo intenso, forte fastidio e necessità di coprirsi molto bene)
    # =========================================================================
    elif windchill < -10: return "(disagio marcato da freddo 🥶)"
    
    # =========================================================================
    # 4. DISAGIO LIEVE (Primi segnali di fastidio pungente, specialmente sulle estremità)
    # =========================================================================
    elif windchill < 0: return "(disagio lieve da freddo 🥶)"
    
    # =========================================================================
    # COMFORT O FREDDO SOPPORTABILE
    # =========================================================================
    else:
        return "(nessun disagio o freddo tollerabile)"

def media_lista(lista):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return int(round(sum(valori_validi) / len(valori_validi)))

def conta_superamenti(lista, soglia):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return sum(1 for v in valori_validi if v >= soglia)

def percentuale_superamento(lista, soglia):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return (sum(1 for v in valori_validi if v >= soglia) / len(valori_validi)) * 100

def interpella_gemini(dati_testuali, oggi_str, domani_str):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-3.5-flash')
    
    prompt = f"""
    Sei un meteorologo professionista. Il tuo compito è scrivere un bollettino discorsivo, fluido ed elegante per Rivoli (TO) partendo dalla sintesi oraria fornita.
    
    REGOLE FERREE (PENA IL FALLIMENTO):
    1. TITOLO: Inizia ESATTAMENTE con: **Aggiornamento meteo di {oggi_str}**
    2. STRUTTURA: Scrivi esattamente due paragrafi: il primo per la giornata odierna, il secondo per domani.
    3. DIVIETO ASSOLUTO DI ELENCARE GLI ORARI: NON elencare MAI le temperature ora per ora.
    4. SINTESI DISCORSIVA: Sintetizza l'evoluzione usando fasi del giorno ("in mattinata", "nelle ore centrali", "nel pomeriggio", "in serata"). Usa la cronistoria fornita solo per capire l'andamento del cielo e dei fenomeni meteo, ma raccontali in modo narrativo.
    5. TEMPERATURE DA CITARE: Cita solo la temperatura minima e la temperatura massima prevista.
    6. DISAGIO TERMICO: Quando citi la temperatura massima, affianca ESATTAMENTE la dicitura sul disagio che trovi nei dati.
    7. TERMINOLOGIA CIELO: Quando descrivi la nuvolosità, DEVI integrare nel testo ESATTAMENTE le stesse diciture fornite dai dati. Evita sinonimi liberi.
    8. PROBABILISMO SULLE PRECIPITAZIONI: Non dare mai i fenomeni precipitativi per certi. Usa sempre un tono probabilistico e riporta la percentuale indicata nei dati (es. "possibile instabilità (60%) con rischio di rovesci").
    9. FILTRO INSTABILITÀ: Se all'interno della stessa giornata ci sono più orari con "possibile instabilità", individua quello con la percentuale di probabilità più alta e descrivi ESCLUSIVAMENTE quello nel bollettino. Ignora e non menzionare in alcun modo gli altri momenti di instabilità della stessa giornata.
    
    ESEMPIO DI STILE DA IMITARE ALLA PERFEZIONE:
    "La giornata di domenica si apre con condizioni di stabilità atmosferica. Le temperature minime si assestano sui 19°C. Durante le ore di luce il cielo si manterrà in prevalenza sereno, favorendo un ampio soleggiamento che porterà la massima a 33°C (disagio marcato 🟠). Nel tardo pomeriggio si segnala una possibile instabilità (40%) con rischio di rovesci. In serata la situazione volgerà al miglioramento."
    
    DATI GIORNALIERI DA TRASFORMARE IN TESTO:
    {dati_testuali}
    """
    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.25})
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def main():
    mese_corrente = datetime.now().month
    inverno = mese_corrente in [11, 12, 1, 2, 3, 4]
    estate = mese_corrente in [5, 6, 7, 8, 9, 10]
    
    # --- BLOCCO SEMAFORO: CONTROLLO INIZIALE ---
    FILE_LOCK = "lock_quotidiano.txt"
    oggi_str_lock = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi_str_lock:
                print("✅ Bollettino quotidiano già inviato oggi. Esecuzione terminata.")
                sys.exit(0)
    # -------------------------------------------
    
    try:
        dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "wind_direction_10m,cape,sunshine_duration,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
            "daily": "sunrise,sunset",
            "models": "icon_d2",
            "timezone": "Europe/Rome", "forecast_days": 2
        }, timeout=10).json()

        dati_eps_d2 = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m,apparent_temperature",
            "models": "icon_d2",
            "timezone": "Europe/Rome", "forecast_days": 2
        }, timeout=10).json()
        
        ch2_disponibile = True
        try:
            dati_eps_ch2 = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "precipitation",
                "models": "meteoswiss_icon_ch2_ensemble",
                "timezone": "Europe/Rome", "forecast_days": 2
            }, timeout=10).json()
            
            dati_det_ch2 = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "sunshine_duration",
                "models": "meteoswiss_icon_ch2",
                "timezone": "Europe/Rome", "forecast_days": 2
            }, timeout=10).json()
            
            if 'hourly' not in dati_eps_ch2 or 'hourly' not in dati_det_ch2:
                ch2_disponibile = False
        except:
            ch2_disponibile = False
            
    except Exception as e:
        print(f"Errore fatale nel recupero dati Open-Meteo: {e}")
        return

    h_det = dati_det.get('hourly', {})
    h_eps_d2 = dati_eps_d2.get('hourly', {})
    h_eps_ch2 = dati_eps_ch2.get('hourly', {}) if ch2_disponibile else {}
    h_det_ch2 = dati_det_ch2.get('hourly', {}) if ch2_disponibile else {}
    orari = h_det.get('time', [])
    
    sunrise_str = dati_det.get('daily', {}).get('sunrise', [])
    sunset_str = dati_det.get('daily', {}).get('sunset', [])

    medie_sole = {0: {'mattino': [], 'pomeriggio': []}, 1: {'mattino': [], 'pomeriggio': []}}
    for i in range(len(orari)):
        ora_dt = datetime.fromisoformat(orari[i])
        giorno_idx = 0 if i < 24 else 1
        alba = datetime.fromisoformat(sunrise_str[giorno_idx])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx])
        alba_piu_2 = alba + timedelta(hours=2)
        tramonto_meno_2 = tramonto - timedelta(hours=2)
        
        if ch2_disponibile and h_det_ch2.get('sunshine_duration'):
            sun_sec = h_det_ch2['sunshine_duration'][i]
        else:
            sun_sec = h_det.get('sunshine_duration', [])[i] if i < len(h_det.get('sunshine_duration', [])) else 0
            
        sun_minuti = (sun_sec or 0) / 60
        
        if alba_piu_2 <= ora_dt and ora_dt.hour < 13:
            medie_sole[giorno_idx]['mattino'].append(sun_minuti)
        elif ora_dt.hour >= 13 and ora_dt <= tramonto_meno_2:
            medie_sole[giorno_idx]['pomeriggio'].append(sun_minuti)

    for g in [0, 1]:
        for p in ['mattino', 'pomeriggio']:
            lst = medie_sole[g][p]
            medie_sole[g][p] = sum(lst) / len(lst) if lst else 0

    sintesi_oggi = []
    sintesi_domani = []
    t_min_oggi, t_max_oggi = 100, -100
    t_min_domani, t_max_domani = 100, -100
    apparent_temperatures_medie = []
    dew_point_prev = None

    for i in range(len(orari)):
        ora_dt = datetime.fromisoformat(orari[i])
        ora_solare = ora_dt.hour
        giorno_idx = 0 if i < 24 else 1
        
        t_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('temperature_2m_member')]
        t_media = media_lista(t_membri)
        
        dew_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('dew_point_2m_member')]
        dew_media = media_lista(dew_membri)

        app_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('apparent_temperature_member')]
        app_media = media_lista(app_membri)
        apparent_temperatures_medie.append(app_media)
        
        ur_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('relative_humidity_2m_member')]
        ur_media = media_lista(ur_membri)
        
        w_spd_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('wind_speed_10m_member')]
        w_spd_media = media_lista(w_spd_membri)
        
        w_gst_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('wind_gusts_10m_member')]
        w_gst_media = media_lista(w_gst_membri)
        
        w_dir = h_det.get('wind_direction_10m', [])[i]
        w_dir_str = gradi_a_direzione(w_dir)
        
        prec_eps_d2_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('precipitation_member')]
        prec_eps_ch2_membri = [h_eps_ch2[k][i] for k in h_eps_ch2 if k.startswith('precipitation_member')] if ch2_disponibile else []
        
        pct_d2_1mm = percentuale_superamento(prec_eps_d2_membri, 1.0)
        pct_d2_3mm = percentuale_superamento(prec_eps_d2_membri, 3.0)
        pct_d2_5mm = percentuale_superamento(prec_eps_d2_membri, 5.0)
        num_d2_1mm = conta_superamenti(prec_eps_d2_membri, 1.0)
        
        instabilita = "assente"
        probabilita = 0

        if ch2_disponibile:
            pct_ch2_1mm = percentuale_superamento(prec_eps_ch2_membri, 1.0)
            pct_ch2_3mm = percentuale_superamento(prec_eps_ch2_membri, 3.0)
            pct_ch2_5mm = percentuale_superamento(prec_eps_ch2_membri, 5.0)
            num_ch2_1mm = conta_superamenti(prec_eps_ch2_membri, 1.0)
            
            if num_d2_1mm >= 2 and num_ch2_1mm >= 2:
                instabilita = "possibile instabilità"
                if pct_d2_5mm >= 75 and pct_ch2_5mm >= 75:
                    probabilita = 95
                elif pct_d2_5mm >= 50 and pct_ch2_5mm >= 50:
                    probabilita = 80
                elif pct_d2_5mm >= 25 and pct_ch2_5mm >= 25:
                    probabilita = 70
                elif pct_d2_3mm >= 50 and pct_ch2_3mm >= 50:
                    probabilita = 60
                elif pct_d2_3mm >= 25 and pct_ch2_3mm >= 25:
                    probabilita = 50
                elif pct_d2_1mm >= 50 and pct_ch2_1mm >= 50:
                    probabilita = 40
                elif pct_d2_1mm >= 25 and pct_ch2_1mm >= 25:
                    probabilita = 30
                else:
                    probabilita = 15
        else:
            if num_d2_1mm >= 3:
                instabilita = "possibile instabilità"
                if pct_d2_5mm >= 75:
                    probabilita = 95
                elif pct_d2_5mm >= 50:
                    probabilita = 80
                elif pct_d2_5mm >= 25:
                    probabilita = 70
                elif pct_d2_3mm >= 50:
                    probabilita = 60
                elif pct_d2_3mm >= 25:
                    probabilita = 50
                elif pct_d2_1mm >= 50:
                    probabilita = 40
                elif pct_d2_1mm >= 25:
                    probabilita = 30
                else:
                    probabilita = 15

        tipo_prec = ""
        if instabilita != "assente":
            if inverno:
                if t_media < 2:
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
                    else: tipo_prec = "neve"
                else: tipo_prec = "pioggia"
            else:
                cape = h_det.get('cape', [])[i] if h_det.get('cape') else 0
                if cape > 400: tipo_prec = "temporale"
                else: tipo_prec = "rovesci"

        desc_raffiche = ""
        if w_gst_media > 80: desc_raffiche = "tempestose"
        elif w_gst_media > 55: desc_raffiche = "forti"
        elif w_gst_media > 35: desc_raffiche = "moderate"
        elif w_gst_media >= 25: desc_raffiche = "deboli"

        vento_evento = ""
        if w_spd_media >= 15 or w_gst_media >= 25:
            if dew_point_prev is not None:
                crollo_dew = dew_point_prev - dew_media >= 2
                if w_dir_str in ['NW', 'N', 'W'] and w_gst_media > 25 and crollo_dew:
                    vento_evento = "improvviso rinforzo per probabile Föhn"
                elif w_dir_str in ['E', 'NE', 'SE'] and w_gst_media > 20 and not crollo_dew:
                    vento_evento = "ventilazione umida orientale"
            
            if not vento_evento and not inverno and desc_raffiche:
                vento_evento = f"rischio di {desc_raffiche} raffiche di vento improvvise"
                    
            if not vento_evento and w_spd_media >= 15:
                vento_evento = "rinforzo della ventilazione"
            
        dew_point_prev = dew_media

        alba = datetime.fromisoformat(sunrise_str[giorno_idx])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx])
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

        if giorno_idx == 0:
            t_min_oggi = min(t_min_oggi, t_media)
            t_max_oggi = max(t_max_oggi, t_media)
        else:
            t_min_domani = min(t_min_domani, t_media)
            t_max_domani = max(t_max_domani, t_media)

        record = f"Ore {ora_solare}: T={t_media}°C."
        if cielo: record += f" Cielo {cielo}."
        
        if instabilita != "assente":
            str_instabilita = f"{instabilita} ({probabilita}%)"
            record += f" Si segnala {str_instabilita} con possibilità di {tipo_prec}."
            if "raffiche" in vento_evento:
                vento_evento = ""
                
        if vento_evento: record += f" {vento_evento}."
        if nebbia: record += f" {nebbia}."
        
        if giorno_idx == 0: sintesi_oggi.append(record)
        else: sintesi_domani.append(record)

    disagio_oggi = ""
    disagio_domani = ""
    
    if estate:
        dew_max_oggi = media_lista([h_eps_d2[k][14] for k in h_eps_d2 if k.startswith('dew_point_2m_member')])
        dew_max_domani = media_lista([h_eps_d2[k][14+24] for k in h_eps_d2 if k.startswith('dew_point_2m_member')])
        disagio_oggi = calcola_disagio_caldo(t_max_oggi, dew_max_oggi)
        disagio_domani = calcola_disagio_caldo(t_max_domani, dew_max_domani)
    elif inverno:
        windchill_min_oggi = min(apparent_temperatures_medie[0:24])
        windchill_min_domani = min(apparent_temperatures_medie[24:48])
        disagio_oggi = calcola_disagio_freddo(windchill_min_oggi)
        disagio_domani = calcola_disagio_freddo(windchill_min_domani)

    dt_oggi = datetime.now()
    dt_domani = dt_oggi + timedelta(days=1)
    oggi_str = formatta_data_it(dt_oggi)
    domani_str = formatta_data_it(dt_domani)

    testo_per_ia = f"""
    GIORNO 1: {oggi_str}
    - Temperatura Minima: {t_min_oggi}°C
    - Temperatura Massima: {t_max_oggi}°C {disagio_oggi}
    CRONISTORIA DEGLI EVENTI DA SINTETIZZARE:
    {chr(10).join(sintesi_oggi)}

    GIORNO 2: {domani_str}
    - Temperatura Minima: {t_min_domani}°C
    - Temperatura Massima: {t_max_domani}°C {disagio_domani}
    CRONISTORIA DEGLI EVENTI DA SINTETIZZARE:
    {chr(10).join(sintesi_domani)}
    """

    bollettino_finale = interpella_gemini(testo_per_ia, oggi_str, domani_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "Markdown"})
        if risposta_tg.status_code == 200:
            print("Bollettino inviato con successo!")
            # --- BLOCCO SEMAFORO: AGGIORNAMENTO DOPO IL SUCCESSO ---
            with open(FILE_LOCK, "w") as f:
                f.write(oggi_str_lock)
            # --------------------------------------------------------
        else:
            print(f"Errore Telegram: {risposta_tg.text}")
    else:
        print("Errore: Token o Chat ID mancanti! Stampo a video:")
        print("-------------------------------------------------")
        print(bollettino_finale)

if __name__ == "__main__":
    main()
