import os
import sys
import math
import requests
from datetime import datetime, timedelta
from groq import Groq

# Coordinate - Rivoli (TO)
LAT = 45.0734521841099
LON = 7.543386286825349

def scomposizione_vettoriale(speed_kmh, direction_deg):
    """Converte velocità e direzione di provenienza in vettori U e V (m/s)."""
    if speed_kmh is None or direction_deg is None:
        return 0.0, 0.0
    speed_ms = speed_kmh / 3.6
    rad = math.radians(direction_deg)
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return u, v

def calcola_vettore_traslazione(u, v):
    """Calcola la velocità (km/h) e la direzione VERSO CUI punta il vettore (gradi)."""
    speed_ms = math.sqrt(u**2 + v**2)
    speed_kmh = speed_ms * 3.6
    direction_deg = (math.degrees(math.atan2(u, v)) + 360) % 360
    return speed_kmh, direction_deg

def magnitudo_shear(u1, v1, u2, v2):
    """Calcola la magnitudo (m/s) della differenza vettoriale."""
    if None in (u1, v1, u2, v2):
        return None
    return math.sqrt((u2 - u1)**2 + (v2 - v1)**2)

def check_probabilita_precipitazione():
    """
    Controlla la probabilità di precipitazione massima GIORNALIERA per D2 e CH2.
    Restituisce i giorni (oggi e/o domani) che superano le soglie:
    >= 15% su almeno un modello, oppure >= 10% su entrambi.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT, "longitude": LON,
        "daily": "precipitation_probability_max",
        "models": "dwd_icon_d2,meteoswiss_icon_ch2",
        "timezone": "Europe/Rome",
        "forecast_days": 3
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        
        times = daily.get("time", [])
        prob_d2 = daily.get("precipitation_probability_max_dwd_icon_d2", [])
        prob_ch2 = daily.get("precipitation_probability_max_meteoswiss_icon_ch2", [])
        
        giorni_validi = []
        
        for i in range(min(2, len(times))):
            d2_val = prob_d2[i] if len(prob_d2) > i and prob_d2[i] is not None else 0
            ch2_val = prob_ch2[i] if len(prob_ch2) > i and prob_ch2[i] is not None else 0
            
            if (d2_val >= 15 or ch2_val >= 15) or (d2_val >= 10 and ch2_val >= 10):
                giorni_validi.append(times[i])
                
        return giorni_validi
    except Exception as e:
        print(f"⚠️ Errore nel download Probabilità Precipitazione: {e}")
        return []

def fetch_dati_termodinamici():
    """Scarica la colonna termodinamica avanzata (ICON-D2) e la probabilità oraria di entrambi i modelli."""
    url = "https://api.open-meteo.com/v1/forecast"
    hourly_params = (
        "precipitation_probability," 
        "temperature_2m,relative_humidity_2m,dew_point_2m,wind_gusts_10m,lightning_potential,updraft,convective_cloud_base,convective_cloud_top,cape,freezing_level_height,"
        "temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa,temperature_700hPa,temperature_600hPa,temperature_500hPa,temperature_400hPa,temperature_300hPa,temperature_250hPa,temperature_200hPa,"
        "relative_humidity_1000hPa,relative_humidity_975hPa,relative_humidity_950hPa,relative_humidity_925hPa,relative_humidity_900hPa,relative_humidity_850hPa,relative_humidity_800hPa,relative_humidity_700hPa,relative_humidity_600hPa,relative_humidity_500hPa,relative_humidity_400hPa,relative_humidity_300hPa,relative_humidity_250hPa,relative_humidity_200hPa,"
        "wind_speed_1000hPa,wind_speed_975hPa,wind_speed_950hPa,wind_speed_925hPa,wind_speed_900hPa,wind_speed_850hPa,wind_speed_800hPa,wind_speed_700hPa,wind_speed_600hPa,wind_speed_500hPa,wind_speed_400hPa,wind_speed_300hPa,wind_speed_250hPa,wind_speed_200hPa,"
        "wind_direction_1000hPa,wind_direction_975hPa,wind_direction_950hPa,wind_direction_925hPa,wind_direction_900hPa,wind_direction_850hPa,wind_direction_800hPa,wind_direction_700hPa,wind_direction_600hPa,wind_direction_500hPa,wind_direction_400hPa,wind_direction_300hPa,wind_direction_250hPa,wind_direction_200hPa,"
        "geopotential_height_1000hPa,geopotential_height_975hPa,geopotential_height_950hPa,geopotential_height_925hPa,geopotential_height_900hPa,geopotential_height_850hPa,geopotential_height_800hPa,geopotential_height_700hPa,geopotential_height_600hPa,geopotential_height_500hPa,geopotential_height_400hPa,geopotential_height_300hPa,geopotential_height_250hPa,geopotential_height_200hPa"
    )
    
    params = {
        "latitude": LAT, "longitude": LON, 
        "models": "dwd_icon_d2,meteoswiss_icon_ch2", 
        "hourly": hourly_params,
        "timezone": "Europe/Rome", "forecast_days": 3
    }
    resp = requests.get(url, params=params, timeout=40)
    resp.raise_for_status()
    return resp.json()['hourly']

def media_sicura(lista):
    valori_validi = [x for x in lista if x is not None]
    return sum(valori_validi) / len(valori_validi) if valori_validi else None

def max_sicuro(lista):
    valori_validi = [x for x in lista if x is not None]
    return max(valori_validi) if valori_validi else None

def min_sicuro(lista):
    valori_validi = [x for x in lista if x is not None]
    return min(valori_validi) if valori_validi else None

def stima_grandine(cape, updraft, dls, zero_termico, spessore_nube):
    cape = cape or 0
    updraft = updraft or 0
    dls = dls or 0
    spessore_nube = spessore_nube or 0
    
    if cape < 200 or spessore_nube < 3000:
        return "Livello 0 su 5 - Assente (assenza di convezione profonda)"
    if updraft > 15 or cape > 2500 or (cape > 1500 and dls > 25):
        return "Livello 5 su 5 - ESTREMA (> 5 cm). Fortissimi updraft, rischio mesociclone isolato, chicchi distruttivi."
    if updraft > 8 or cape > 1500 or (cape > 1000 and dls > 20):
        return "Livello 4 su 5 - GROSSA (3 - 5 cm). Updraft intensi e sostenuti, probabili supercelle."
    if updraft > 4 or cape > 800 or (cape > 500 and dls > 15):
        return "Livello 3 su 5 - MEDIA (1.5 - 3 cm). Celle multicellulari ben organizzate, possibili accumuli al suolo."
    if updraft > 1.5 or cape > 400:
        if zero_termico is not None and zero_termico > 4000:
            return "Livello 1 su 5 - GRAUPEL/FUSIONE. Fusione dei piccoli chicchi per via dello zero termico molto alto."
        return "Livello 2 su 5 - PICCOLA (< 1.5 cm). Strutture a cella singola con rapido collasso precipitativo."
        
    return "Livello 0 su 5 - Assente o trascurabile."

def stima_downburst(rh_700, rh_500, lapse_rate, wind_gust, dls):
    rh_700 = rh_700 or 100
    rh_500 = rh_500 or 100
    lapse_rate = lapse_rate or 5.0
    wind_gust = wind_gust or 0
    dls = dls or 0
    
    rh_medio_secco = (rh_700 + rh_500) / 2

    if rh_medio_secco < 40 and lapse_rate > 7.5 and wind_gust > 80:
        return "Livello 5 su 5 - ESTREMO / MICROBURST. Aria secchissima in quota e gradienti violenti. Rischio venti distruttivi (> 100 km/h)."
    if rh_medio_secco < 50 and lapse_rate > 7.0 and wind_gust > 60:
        return "Livello 4 su 5 - GRAVE. Forti raffiche discendenti (Dry Downburst) alimentate da rapida evaporazione. Venti > 80 km/h."
    if wind_gust > 70 or (rh_medio_secco < 60 and lapse_rate > 6.5 and dls > 15):
        return "Livello 3 su 5 - FORTE. Wet/Dry Downburst capaci di sradicamenti isolati o danni minori (< 80 km/h)."
    if wind_gust > 50 or lapse_rate > 6.0:
        return "Livello 2 su 5 - MODERATO. Outflow classico da temporale estivo multicellulare (< 70 km/h)."
        
    return "Livello 1 su 5 - DEBOLE. Outflow boundary ordinario, brezze rinfrescanti o raffiche non pericolose."

def ora_con_articolo(ora):
    if ora == 0:
        return "la mezzanotte"
    elif ora == 1:
        return "l'una"
    else:
        return f"le {ora}"

def formatta_fascia_oraria(ora_str):
    """Prende un orario tipo '16:00' e restituisce 'tra le 15 e le 17' con gli articoli corretti."""
    ora_centrale = int(ora_str.split(":")[0])
    ora_prima = (ora_centrale - 1) % 24
    ora_dopo = (ora_centrale + 1) % 24
    return f"tra {ora_con_articolo(ora_prima)} e {ora_con_articolo(ora_dopo)}"

def interpella_groq_semplice(report_tecnico, giorno_str, fascia_oraria):
    """Genera un messaggio DIVULGATIVO per il pubblico generico, partendo dagli stessi dati tecnici."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: return "Errore: Manca la chiave API di Groq."
        
    client = Groq(api_key=api_key)
    
    prompt = f'''
    Sei un meteorologo che deve comunicare al pubblico generico (non esperti) il rischio maltempo per {giorno_str} a Rivoli (TO), zona Piemonte.

    Qui sotto trovi i dati tecnici e le stime di severità già calcolate algoritmicamente. Usali SOLO per capire la gravità della situazione, ma NON riportarli nel messaggio finale.

    DATI TECNICI (uso interno, non citare numeri né sigle):
    {report_tecnico}

    SCRIVI UN MESSAGGIO BREVE (massimo 3-4 frasi) SEGUENDO QUESTE REGOLE FERREE:

    1. LINGUAGGIO COMUNE: zero terminologia meteorologica tecnica. VIETATO scrivere parole come: downburst, cella singola, multicella, supercella, CAPE, shear, updraft, lapse rate, LCL, wind shear, o qualsiasi sigla. Parla come parleresti a un vicino di casa.
    2. SOLO FENOMENI, NON STRUTTURE: descrivi cosa potrebbe succedere (pioggia forte, grandine, vento, fulmini), mai come è fatto il temporale.
    3. CONDIZIONALE SEMPRE: usa sempre il condizionale ("potrebbe", "sarebbero possibili", "non è escluso che..."). Non affermare mai nulla come certo.
    4. INCERTEZZA ESPLICITA: usa la forma "Ricorda che si tratta solo di una possibilità" (mai "Ricordate", sempre la forma singolare "Ricorda"), e invita a monitorare gli aggiornamenti.
    5. FASCIA ORARIA: usa ESATTAMENTE e SOLO questa fascia oraria, copiala testualmente senza modificarla: "{fascia_oraria}". Non inventare altri orari e non scrivere mai orari nel formato tipo "14:00", usa solo la fascia fornita.
    6. GRANDINE: se dai dati risulta un rischio di grandine, menzionala solo con un aggettivo generico (es. "piccola", "di media dimensione", "di grandi dimensioni") SENZA fare esempi o paragoni concreti (niente piselli, palline da golf o simili).
    7. VENTO: se rilevante, indica solo l'intensità approssimativa in km/h (es. "raffiche fino a 70 km/h"), nessun altro numero tecnico.
    8. NIENTE CONSIGLI PRATICI: non aggiungere suggerimenti o precauzioni (niente "metti al riparo l'auto", "evita spostamenti" o simili). Limitati a descrivere cosa potrebbe accadere.
    9. NIENTE NUMERI TECNICI: non citare CAPE, shear, percentuali di probabilità o altri valori grezzi.
    10. TONO: rassicurante ma chiaro, senza allarmismo, in italiano semplice.
    '''

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Errore AI Groq: {e}"

def main():
    FILE_LOCK = "lock_temporali_semplice.txt"
    oggi_str_formato_iso = datetime.now().strftime("%Y-%m-%d")
    
    # 1. CONTROLLO SEMAFORO
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi_str_formato_iso:
                print("✅ Analisi temporali già inviata oggi. Esecuzione terminata per evitare spam.")
                sys.exit(0)

    print("Ricerca inneschi: Analisi probabilità massime precipitazione giornaliera D2/CH2...")
    giorni_validi = check_probabilita_precipitazione()
    
    if not giorni_validi:
        print("Analisi terminata: Nessuna probabilità di precipitazione rilevante nei prossimi giorni.")
        return

    print(f"Giorni con potenziale innesco individuati: {giorni_validi}")
    print("Scaricamento radiosondaggio predittivo completo 1000-200 hPa...")
    hourly = fetch_dati_termodinamici()
    
    corpo_messaggio = ""
    inviato_almeno_uno = False

    for data_str in giorni_validi:
        indici_giorno = [i for i, t in enumerate(hourly['time']) if t.startswith(data_str)]
        if not indici_giorno:
            continue
            
        idx_picco = -1
        
        for i in indici_giorno:
            prob_d2 = hourly.get('precipitation_probability_dwd_icon_d2', [])
            prob_ch2 = hourly.get('precipitation_probability_meteoswiss_icon_ch2', [])
            
            p_d2 = prob_d2[i] if len(prob_d2) > i and prob_d2[i] is not None else 0
            p_ch2 = prob_ch2[i] if len(prob_ch2) > i and prob_ch2[i] is not None else 0
            
            if (p_d2 >= 15 or p_ch2 >= 15) or (p_d2 >= 10 and p_ch2 >= 10):
                idx_picco = i
                break

        if idx_picco == -1:
            idx_picco = [i for i in indici_giorno if hourly['time'][i].endswith("16:00")][0]
            print(f"[{data_str}] Nessun innesco orario netto trovato, fallback alle 16:00.")

        indici_attivi = [idx for idx in range(idx_picco - 3, idx_picco + 1) if 0 <= idx < len(hourly['time'])]
        
        max_cape = max_sicuro([hourly['cape_dwd_icon_d2'][i] for i in indici_attivi])
        max_updraft = max_sicuro([hourly['updraft_dwd_icon_d2'][i] for i in indici_attivi])
        max_fulmini = max_sicuro([hourly['lightning_potential_dwd_icon_d2'][i] for i in indici_attivi])
        max_gust = max_sicuro([hourly['wind_gusts_10m_dwd_icon_d2'][i] for i in indici_attivi])
        
        min_base = min_sicuro([hourly['convective_cloud_base_dwd_icon_d2'][i] for i in indici_attivi])
        max_top = max_sicuro([hourly['convective_cloud_top_dwd_icon_d2'][i] for i in indici_attivi])
        spessore_nube = (max_top - min_base) if min_base is not None and max_top is not None else None

        z_termico = media_sicura([hourly['freezing_level_height_dwd_icon_d2'][i] for i in indici_attivi])
        
        t2m_max = max_sicuro([hourly['temperature_2m_dwd_icon_d2'][i] for i in indici_attivi])
        tdew_max = max_sicuro([hourly['dew_point_2m_dwd_icon_d2'][i] for i in indici_attivi])
        lcl_medio = 125 * (t2m_max - tdew_max) if t2m_max and tdew_max else None

        lrs_850_500 = []
        lrs_500_300 = []
        for i in indici_attivi:
            t850 = hourly['temperature_850hPa_dwd_icon_d2'][i]
            t500 = hourly['temperature_500hPa_dwd_icon_d2'][i]
            t300 = hourly['temperature_300hPa_dwd_icon_d2'][i]
            z850 = hourly['geopotential_height_850hPa_dwd_icon_d2'][i]
            z500 = hourly['geopotential_height_500hPa_dwd_icon_d2'][i]
            z300 = hourly['geopotential_height_300hPa_dwd_icon_d2'][i]
            
            if None not in (t850, t500, z850, z500) and z500 != z850:
                lrs_850_500.append((t850 - t500) / ((z500 - z850) / 1000.0))
            if None not in (t500, t300, z500, z300) and z300 != z500:
                lrs_500_300.append((t500 - t300) / ((z300 - z500) / 1000.0))
        
        lr_basso = max_sicuro(lrs_850_500)
        lr_alto = max_sicuro(lrs_500_300)

        rh_low = media_sicura([hourly[f'relative_humidity_{p}hPa_dwd_icon_d2'][i] for p in [1000, 925, 850] for i in indici_attivi])
        rh_mid = media_sicura([hourly[f'relative_humidity_{p}hPa_dwd_icon_d2'][i] for p in [700, 600, 500] for i in indici_attivi])
        rh_high = media_sicura([hourly[f'relative_humidity_{p}hPa_dwd_icon_d2'][i] for p in [400, 300, 200] for i in indici_attivi])
        
        rh_700_spec = min_sicuro([hourly['relative_humidity_700hPa_dwd_icon_d2'][i] for i in indici_attivi])
        rh_500_spec = min_sicuro([hourly['relative_humidity_500hPa_dwd_icon_d2'][i] for i in indici_attivi])

        u_10, v_10 = [], []
        u_850, v_850 = [], []
        u_700, v_700 = [], []
        u_500, v_500 = [], []

        for i in indici_attivi:
            u, v = scomposizione_vettoriale(hourly['wind_speed_1000hPa_dwd_icon_d2'][i], hourly['wind_direction_1000hPa_dwd_icon_d2'][i])
            u_10.append(u); v_10.append(v)
            u, v = scomposizione_vettoriale(hourly['wind_speed_850hPa_dwd_icon_d2'][i], hourly['wind_direction_850hPa_dwd_icon_d2'][i])
            u_850.append(u); v_850.append(v)
            u, v = scomposizione_vettoriale(hourly['wind_speed_700hPa_dwd_icon_d2'][i], hourly['wind_direction_700hPa_dwd_icon_d2'][i])
            u_700.append(u); v_700.append(v)
            u, v = scomposizione_vettoriale(hourly['wind_speed_500hPa_dwd_icon_d2'][i], hourly['wind_direction_500hPa_dwd_icon_d2'][i])
            u_500.append(u); v_500.append(v)

        avg_u10, avg_v10 = sum(u_10)/len(u_10), sum(v_10)/len(v_10)
        avg_u850, avg_v850 = sum(u_850)/len(u_850), sum(v_850)/len(v_850)
        avg_u700, avg_v700 = sum(u_700)/len(u_700), sum(v_700)/len(v_700)
        avg_u500, avg_v500 = sum(u_500)/len(u_500), sum(v_500)/len(v_500)
        
        lls = magnitudo_shear(avg_u10, avg_v10, avg_u850, avg_v850)
        dls = magnitudo_shear(avg_u10, avg_v10, avg_u500, avg_v500)
        
        u_cbl = (avg_u850 + avg_u700 + avg_u500) / 3
        v_cbl = (avg_v850 + avg_v700 + avg_v500) / 3
        trasl_kmh, trasl_dir = calcola_vettore_traslazione(u_cbl, v_cbl)

        stima_g = stima_grandine(max_cape, max_updraft, dls, z_termico, spessore_nube)
        stima_d = stima_downburst(rh_700_spec, rh_500_spec, lr_basso, max_gust, dls)

        ora_inizio_finestra = datetime.fromisoformat(hourly['time'][indici_attivi[0]]).strftime('%H:%M')
        ora_fine_finestra = datetime.fromisoformat(hourly['time'][indici_attivi[-1]]).strftime('%H:%M')

        report_lines = [
            f"Finestra Inflow Pre-Convettivo analizzata: {ora_inizio_finestra} - {ora_fine_finestra} (Innesco atteso attorno alle {ora_fine_finestra})"
        ]
        
        if max_cape and max_cape > 0: 
            report_lines.append(f"Max CAPE: {max_cape:.0f} J/kg")
        if max_updraft and max_updraft > 0: 
            report_lines.append(f"Max Updraft: {max_updraft:.1f} m/s")
        if max_fulmini and max_fulmini > 0: 
            report_lines.append(f"Lightning Potential Index: {max_fulmini:.1f}")
        if lcl_medio and lcl_medio > 0: 
            report_lines.append(f"LCL (Base Nubi Medio): {lcl_medio:.0f} m")
        if spessore_nube and spessore_nube > 0: 
            report_lines.append(f"Spessore Nube Convettiva (Max Estensione): {spessore_nube:.0f} m")
            
        if lr_basso is not None: report_lines.append(f"Lapse Rate Basso Massimo (850-500 hPa): {lr_basso:.1f} °C/km")
        if lr_alto is not None: report_lines.append(f"Lapse Rate Alto Massimo (500-300 hPa): {lr_alto:.1f} °C/km")
        if rh_low is not None and rh_mid is not None and rh_high is not None:
            report_lines.append(f"Umidità Layer (Bassa/Media/Alta): {rh_low:.0f}% / {rh_mid:.0f}% / {rh_high:.0f}%")
            
        if dls is not None: report_lines.append(f"Deep Layer Shear (0-6 km): {dls:.1f} m/s")
        if lls is not None: report_lines.append(f"Low Level Shear (0-1 km): {lls:.1f} m/s")
        if trasl_kmh is not None and trasl_dir is not None:
            report_lines.append(f"Vettore Traslazione: {trasl_kmh:.1f} km/h verso {trasl_dir:.0f}°")
            
        report_lines.append(f"\nANALISI ALGORITMICA SEVERITÀ:\nRischio Grandine: {stima_g}\nRischio Downburst: {stima_d}")
        
        report_dati = "\n".join(report_lines)
        
        giorno_formattato = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        print(f"[{giorno_formattato}] Elaborazione messaggio divulgativo tramite Groq...")
        fascia_oraria = formatta_fascia_oraria(ora_fine_finestra)
        responso = interpella_groq_semplice(report_dati, giorno_formattato, fascia_oraria)

        if responso and not responso.startswith("Errore AI Groq"):
            responso = responso.replace("<", "&lt;").replace(">", "&gt;")
        
        corpo_messaggio += f"📅 <b>{giorno_formattato}</b>\n\n{responso}\n\n➖➖➖➖➖➖➖➖➖➖\n\n"
        inviato_almeno_uno = True

    if inviato_almeno_uno:
        corpo_messaggio = corpo_messaggio.rstrip("➖➖➖➖➖➖➖➖➖➖\n\n")
        
        titolo = "⛈ <b>Avviso per possibili temporali</b>\n\n"
            
        messaggio_telegram = titolo + corpo_messaggio
        
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if token and chat_id:
            if "Errore AI Groq:" in messaggio_telegram:
                print("Blocco l'invio su Telegram a causa di un errore API nel responso.")
            else:
                res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={
                    "chat_id": chat_id,
                    "text": messaggio_telegram,
                    "parse_mode": "HTML"
                })
                
                if res.status_code == 200:
                    print("Messaggio divulgativo inviato con successo su Telegram!")
                    with open(FILE_LOCK, "w") as f:
                        f.write(oggi_str_formato_iso)
                else:
                    print(f"Errore invio Telegram: {res.text}")
        else:
            print(messaggio_telegram)

if __name__ == "__main__":
    main()
