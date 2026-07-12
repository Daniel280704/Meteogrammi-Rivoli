#!/usr/bin/env python3
import os
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
    if t_aria >= 36 or dew_point >= 24: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 34 or dew_point >= 22: return "(disagio forte 🔴)"
    elif t_aria >= 30 or dew_point >= 20: return "(disagio marcato 🟠)"
    elif t_aria >= 27 or dew_point >= 18: return "(disagio lieve 🟡)"
    return "(assenza di disagio 🟢)"

def calcola_disagio_freddo(windchill):
    if windchill < -10: return "(disagio estremo da freddo 🥶)"
    elif windchill < -5: return "(disagio forte da freddo 🔵)"
    elif windchill < 0: return "(disagio marcato da freddo 🧊)"
    elif windchill < 5: return "(disagio lieve da freddo ❄️)"
    return "(assenza di disagio 🟢)"

def media_lista(lista):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return int(round(sum(valori_validi) / len(valori_validi)))

def percentuale_superamento(lista, soglia):
    valori_validi = [v for v in lista if v is not None]
    if not valori_validi: return 0
    return (sum(1 for v in valori_validi if v >= soglia) / len(valori_validi)) * 100

def interpella_gemini(dati_testuali, oggi_str, giorni_str):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-3.5-flash')
    
    prompt = f"""
    Sei un meteorologo professionista. Il tuo compito è scrivere un bollettino discorsivo, fluido ed elegante per Rivoli (TO) a MEDIO TERMINE, partendo dalla sintesi oraria fornita.
    
    REGOLE FERREE (PENA IL FALLIMENTO):
    1. TITOLO: Inizia ESATTAMENTE con: **Aggiornamento meteo a medio termine di {oggi_str}**
    2. STRUTTURA: Scrivi esattamente tre paragrafi:
       - Il primo paragrafo dedicato a {giorni_str[2]}
       - Il secondo paragrafo dedicato a {giorni_str[3]}
       - Il terzo paragrafo dedicato a {giorni_str[4]}
    3. DIVIETO ASSOLUTO DI ELENCARE GLI ORARI: NON elencare MAI le temperature ora per ora.
    4. SINTESI DISCORSIVA: Sintetizza l'evoluzione usando fasi del giorno ("in mattinata", "nelle ore centrali", "nel pomeriggio", "in serata"). Usa la cronistoria fornita solo per capire l'andamento del cielo e dei fenomeni meteo, ma raccontali in modo narrativo.
    5. TEMPERATURE DA CITARE: Cita solo la temperatura minima e la temperatura massima prevista.
    6. DISAGIO TERMICO: Quando citi la temperatura massima, affianca ESATTAMENTE la dicitura sul disagio che trovi nei dati.
    7. TERMINOLOGIA CIELO: Quando descrivi la nuvolosità, DEVI integrare nel testo ESATTAMENTE le stesse diciture fornite dai dati. Evita sinonimi liberi.
    
    ESEMPIO DI STILE DA IMITARE ALLA PERFEZIONE:
    "La giornata di {giorni_str[2]} si aprirà con condizioni di stabilità atmosferica. Le temperature minime si assesteranno sui 19°C. Durante le ore di luce il cielo si manterrà in prevalenza sereno, favorendo un ampio soleggiamento che porterà la massima a 33°C (disagio marcato 🟠). Nel tardo pomeriggio avremo un cielo parzialmente nuvoloso, ma senza fenomeni di rilievo."
    
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
    inverno = mese_corrente in [11, 12, 1, 2, 3]
    estate = mese_corrente in [5, 6, 7, 8, 9, 10]
    
    dt_oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dt_inizio_estrazione = dt_oggi + timedelta(days=2)
    dt_fine_estrazione = dt_oggi + timedelta(days=4)

    try:
        # TENTATIVO 1: Richiesta a ICON-CH2 (MeteoSwiss)
        dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "wind_direction_10m,cape,sunshine_duration,apparent_temperature,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
            "daily": "sunrise,sunset",
            "models": "meteoswiss_icon_ch2",
            "timezone": "Europe/Rome", 
            "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
            "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
        }, timeout=10).json()

        dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m",
            "models": "meteoswiss_icon_ch2_ensemble",
            "timezone": "Europe/Rome",
            "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
            "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
        }, timeout=10).json()
        
        # SISTEMA DI FAIL-SAFE: Controllo copertura oraria
        orari_temp = dati_det.get('hourly', {}).get('time', [])
        target_dt = dt_fine_estrazione + timedelta(hours=20)
        usa_seamless = False
        
        if not orari_temp:
            usa_seamless = True
        else:
            ultimo_orario = datetime.fromisoformat(orari_temp[-1])
            if ultimo_orario < target_dt:
                usa_seamless = True
                
        # TENTATIVO 2 (FALLBACK): Se CH2 è monco, usa ICON-SEAMLESS
        if usa_seamless:
            print("⚠️ ICON-CH2 non copre fino alle 20:00 del quinto giorno (o è offline). Fallback su ICON-SEAMLESS in corso...")
            dati_det = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "wind_direction_10m,cape,sunshine_duration,apparent_temperature,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
                "daily": "sunrise,sunset",
                "models": "icon_seamless",
                "timezone": "Europe/Rome", 
                "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
                "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
            }, timeout=10).json()

            dati_eps = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m",
                "models": "icon_seamless",
                "timezone": "Europe/Rome",
                "start_date": dt_inizio_estrazione.strftime("%Y-%m-%d"),
                "end_date": dt_fine_estrazione.strftime("%Y-%m-%d")
            }, timeout=10).json()

    except Exception as e:
        print(f"Errore fatale nel recupero dati Open-Meteo: {e}")
        return

    h_det = dati_det.get('hourly', {})
    h_eps = dati_eps.get('hourly', {})
    orari = h_det.get('time', [])
    
    if not orari:
        print("Errore: Nessun dato restituito dai server per il modello selezionato.")
        return

    sunrise_str = dati_det.get('daily', {}).get('sunrise', [])
    sunset_str = dati_det.get('daily', {}).get('sunset', [])

    medie_sole = {2: {'mattino': [], 'pomeriggio': []}, 
                  3: {'mattino': [], 'pomeriggio': []}, 
                  4: {'mattino': [], 'pomeriggio': []}}
                  
    indici_validi = []
    
    for i, t_str in enumerate(orari):
        ora_dt = datetime.fromisoformat(t_str)
        giorno_idx = (ora_dt.date() - dt_oggi.date()).days
        
        if giorno_idx == 4 and ora_dt.hour > 20:
            continue
            
        indici_validi.append(i)
        
        if giorno_idx not in medie_sole:
            continue
            
        alba = datetime.fromisoformat(sunrise_str[giorno_idx - 2])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx - 2])
        alba_piu_2 = alba + timedelta(hours=2)
        tramonto_meno_2 = tramonto - timedelta(hours=2)
        
        sun_sec = h_det.get('sunshine_duration', [])[i] if i < len(h_det.get('sunshine_duration', [])) else None
        sun_minuti = (sun_sec or 0) / 60
        
        if alba_piu_2 <= ora_dt and ora_dt.hour < 13:
            medie_sole[giorno_idx]['mattino'].append(sun_minuti)
        elif ora_dt.hour >= 13 and ora_dt <= tramonto_meno_2:
            medie_sole[giorno_idx]['pomeriggio'].append(sun_minuti)

    for g in medie_sole:
        for p in ['mattino', 'pomeriggio']:
            lst = medie_sole[g][p]
            medie_sole[g][p] = sum(lst) / len(lst) if lst else 0

    sintesi = {2: [], 3: [], 4: []}
    t_min = {2: 100, 3: 100, 4: 100}
    t_max = {2: -100, 3: -100, 4: -100}
    dew_max = {2: -100, 3: -100, 4: -100}
    windchill_min = {2: 100, 3: 100, 4: 100}
    
    dew_point_prev = None
    if len(orari) > 0 and indici_validi:
        primo_idx = indici_validi[0]
        if primo_idx > 0:
            dew_membri_prev = [h_eps[k][primo_idx - 1] for k in h_eps if k.startswith('dew_point_2m_member')]
            dew_point_prev = media_lista(dew_membri_prev)

    for i in indici_validi:
        ora_dt = datetime.fromisoformat(orari[i])
        ora_solare = ora_dt.hour
        giorno_idx = (ora_dt.date() - dt_oggi.date()).days
        
        t_membri = [h_eps[k][i] for k in h_eps if k.startswith('temperature_2m_member')]
        t_media = media_lista(t_membri)
        
        dew_membri = [h_eps[k][i] for k in h_eps if k.startswith('dew_point_2m_member')]
        dew_media = media_lista(dew_membri)
        
        ur_membri = [h_eps[k][i] for k in h_eps if k.startswith('relative_humidity_2m_member')]
        ur_media = media_lista(ur_membri)
        
        w_spd_membri = [h_eps[k][i] for k in h_eps if k.startswith('wind_speed_10m_member')]
        w_spd_media = media_lista(w_spd_membri)
        
        w_gst_membri = [h_eps[k][i] for k in h_eps if k.startswith('wind_gusts_10m_member')]
        w_gst_media = media_lista(w_gst_membri)
        
        w_dir = h_det.get('wind_direction_10m', [])[i] if i < len(h_det.get('wind_direction_10m', [])) else None
        w_dir_str = gradi_a_direzione(w_dir)
        
        prec_eps_membri = [h_eps[k][i] for k in h_eps if k.startswith('precipitation_member')]
        
        pct_1mm = percentuale_superamento(prec_eps_membri, 1.0)
        pct_3mm = percentuale_superamento(prec_eps_membri, 3.0)
        pct_5mm = percentuale_superamento(prec_eps_membri, 5.0)
        
        instabilita = "assente"
        if pct_5mm >= 10:      
            instabilita = "spiccata instabilità"
        elif pct_3mm >= 15:    
            instabilita = "marcata instabilità"
        elif pct_1mm >= 20:    
            instabilita = "possibile instabilità"

        tipo_prec = ""
        if instabilita != "assente":
            if inverno:
                if t_media < 2:
                    strati_quota = [
                        h_det.get('temperature_1000hPa', [])[i] if i < len(h_det.get('temperature_1000hPa', [])) else None,
                        h_det.get('temperature_975hPa', [])[i] if i < len(h_det.get('temperature_975hPa', [])) else None,
                        h_det.get('temperature_950hPa', [])[i] if i < len(h_det.get('temperature_950hPa', [])) else None,
                        h_det.get('temperature_925hPa', [])[i] if i < len(h_det.get('temperature_925hPa', [])) else None,
                        h_det.get('temperature_900hPa', [])[i] if i < len(h_det.get('temperature_900hPa', [])) else None,
                        h_det.get('temperature_850hPa', [])[i] if i < len(h_det.get('temperature_850hPa', [])) else None,
                        h_det.get('temperature_800hPa', [])[i] if i < len(h_det.get('temperature_800hPa', [])) else None
                    ]
                    inversione_presente = any(t > 1 for t in strati_quota if t is not None)
                    if inversione_presente:
                        if t_media > 0: tipo_prec = "pioggia (a causa di inversione termica in quota)"
                        else: tipo_prec = "PERICOLO PIOGGIA CONGELANTE (Gelicidio per inversione termica)"
                    else: tipo_prec = "neve"
                else: tipo_prec = "pioggia"
            else:
                cape = h_det.get('cape', [])[i] if i < len(h_det.get('cape', [])) else 0
                if cape is None: cape = 0
                if cape > 400: tipo_prec = "temporale"
                else: tipo_prec = "rovesci"

        vento_evento = ""
        if w_spd_media >= 15 or w_gst_media > 30:
            if dew_point_prev is not None:
                crollo_dew = dew_point_prev - dew_media >= 2
                if w_dir_str in ['NW', 'N', 'W'] and w_gst_media > 25 and crollo_dew:
                    vento_evento = "improvviso rinforzo per probabile Föhn"
                elif w_dir_str in ['E', 'NE', 'SE'] and w_gst_media > 20 and not crollo_dew:
                    vento_evento = "ventilazione umida orientale"
            
            if not inverno and w_gst_media > 30:
                if instabilita != "assente":
                    vento_evento = "raffiche dovute agli outflow temporaleschi"
                else:
                    vento_evento = "outflow di temporali vicini"
                    
            if not vento_evento and w_spd_media >= 15:
                vento_evento = "rinforzo della ventilazione"
            
        dew_point_prev = dew_media

        alba = datetime.fromisoformat(sunrise_str[giorno_idx - 2])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx - 2])
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

        t_min[giorno_idx] = min(t_min[giorno_idx], t_media)
        t_max[giorno_idx] = max(t_max[giorno_idx], t_media)
        if estate: dew_max[giorno_idx] = max(dew_max[giorno_idx], dew_media)
        elif inverno:
            app_t = h_det.get('apparent_temperature', [])[i] if i < len(h_det.get('apparent_temperature', [])) else t_media
            if app_t is not None: windchill_min[giorno_idx] = min(windchill_min[giorno_idx], app_t)

        record = f"Ore {ora_solare}: T={t_media}°C."
        if cielo: record += f" Cielo {cielo}."
        if instabilita != "assente": record += f" Rilevata {instabilita} con {tipo_prec}."
        if vento_evento: record += f" {vento_evento}."
        if nebbia: record += f" {nebbia}."
        
        sintesi[giorno_idx].append(record)

    disagio = {2: "", 3: "", 4: ""}
    for g in [2, 3, 4]:
        if estate and t_max[g] != -100:
            disagio[g] = calcola_disagio_caldo(t_max[g], dew_max[g])
        elif inverno and windchill_min[g] != 100:
            disagio[g] = calcola_disagio_freddo(windchill_min[g])

    oggi_str = formatta_data_it(dt_oggi)
    
    giorni_str = {
        2: formatta_data_it(dt_oggi + timedelta(days=2)),
        3: formatta_data_it(dt_oggi + timedelta(days=3)),
        4: formatta_data_it(dt_oggi + timedelta(days=4))
    }

    testo_per_ia = ""
    for g in [2, 3, 4]:
        if not sintesi[g]: continue
        testo_per_ia += f"GIORNO: {giorni_str[g]}\n"
        testo_per_ia += f"- Temperatura Minima: {t_min[g]}°C\n"
        testo_per_ia += f"- Temperatura Massima: {t_max[g]}°C {disagio[g]}\n"
        testo_per_ia += "CRONISTORIA DEGLI EVENTI:\n"
        testo_per_ia += "\n".join(sintesi[g]) + "\n\n"

    bollettino_finale = interpella_gemini(testo_per_ia, oggi_str, giorni_str)
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "Markdown"})
        if risposta_tg.status_code == 200:
            print("Bollettino a medio termine inviato con successo!")
        else:
            print(f"Errore Telegram: {risposta_tg.text}")
    else:
        print("Errore: Token o Chat ID mancanti! Stampo a video:")
        print("-------------------------------------------------")
        print(bollettino_finale)

if __name__ == "__main__":
    main()
