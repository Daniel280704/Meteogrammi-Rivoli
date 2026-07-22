import os
import sys
import math
import requests
from datetime import datetime
from groq import Groq

# Coordinate - Rivoli (TO)
LAT = 45.0734521841099
LON = 7.543386286825349

def scomposizione_vettoriale(speed_kmh, direction_deg):
    if speed_kmh is None or direction_deg is None:
        return 0.0, 0.0
    speed_ms = speed_kmh / 3.6
    rad = math.radians(direction_deg)
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return u, v

def calcola_vettore_traslazione(u, v):
    speed_ms = math.sqrt(u**2 + v**2)
    speed_kmh = speed_ms * 3.6
    direction_deg = (math.degrees(math.atan2(u, v)) + 360) % 360
    return speed_kmh, direction_deg

def magnitudo_shear(u1, v1, u2, v2):
    if None in (u1, v1, u2, v2):
        return None
    return math.sqrt((u2 - u1)**2 + (v2 - v1)**2)

def classificazione_traslazione_avverbio(kmh):
    if kmh < 15: return "molto lentamente, risultando quasi stazionario"
    if kmh < 30: return "lentamente"
    if kmh < 50: return "rapidamente"
    return "molto rapidamente"

def formatta_direzione_bussola(gradi):
    direzioni = ["nord", "nord-est", "est", "sud-est", "sud", "sud-ovest", "ovest", "nord-ovest"]
    indice = round(gradi / 45) % 8
    return direzioni[indice]

def arrotonda_decina(valore):
    if valore is None: return 0
    v = int(round(valore))
    if v < 10: return v
    return int(round(v / 10.0) * 10)

def check_probabilita_precipitazione():
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
    except: 
        return []

def fetch_dati_termodinamici():
    url = "https://api.open-meteo.com/v1/forecast"
    hourly_params = (
        "precipitation_probability," 
        "temperature_2m,relative_humidity_2m,dew_point_2m,wind_gusts_10m,lightning_potential,updraft,convective_cloud_base,convective_cloud_top,cape,freezing_level_height,"
        "wind_speed_1000hPa,wind_direction_1000hPa,wind_speed_850hPa,wind_direction_850hPa,wind_speed_700hPa,wind_direction_700hPa,wind_speed_500hPa,wind_direction_500hPa"
    )
    params = {"latitude": LAT, "longitude": LON, "models": "dwd_icon_d2,meteoswiss_icon_ch2", "hourly": hourly_params, "timezone": "Europe/Rome", "forecast_days": 3}
    return requests.get(url, params=params, timeout=40).json()['hourly']

def fetch_ecmwf_pwat():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT, "longitude": LON,
        "models": "ecmwf_ifs",
        "hourly": "total_column_integrated_water_vapour",
        "timezone": "Europe/Rome",
        "forecast_days": 3
    }
    try:
        return requests.get(url, params=params, timeout=30).json()['hourly']
    except: 
        return None

def media_sicura(lista):
    valori = [x for x in lista if x is not None]
    return sum(valori) / len(valori) if valori else None

def max_sicuro(lista):
    valori = [x for x in lista if x is not None]
    return max(valori) if valori else 0

def min_sicuro(lista):
    valori = [x for x in lista if x is not None]
    return min(valori) if valori else 0

def stima_intensita_pioggia(pwat):
    if pwat >= 40: return "pioggia violenta a carattere di nubifragio"
    if pwat >= 30: return "pioggia molto forte"
    return "pioggia forte"

def stima_grandine_pubblico(cape, updraft, dls, zero_termico, spessore_nube):
    cape = cape or 0
    updraft = updraft or 0
    dls = dls or 0
    spessore_nube = spessore_nube or 0
    
    if cape < 200 or spessore_nube < 3000:
        return "assente"
    if updraft > 15 or cape > 2500 or (cape > 1500 and dls > 25):
        return "potenzialmente di grandi dimensioni (fino a 5 cm o oltre)"
    if updraft > 8 or cape > 1500 or (cape > 1000 and dls > 20):
        return "di medie dimensioni (fino a 5 cm)"
    if updraft > 4 or cape > 800 or (cape > 500 and dls > 15):
        return "di piccole dimensioni"
    if updraft > 1.5 or cape > 400:
        if zero_termico is not None and zero_termico > 4000:
            return "molto piccola o assente"
        return "di piccole dimensioni"
    return "assente"

def ora_con_articolo(ora):
    if ora == 0: return "la mezzanotte"
    elif ora == 1: return "l'una"
    else: return f"le {ora}"

def formatta_fascia_oraria(ora_str):
    ora_centrale = int(ora_str.split(":")[0])
    ora_prima = (ora_centrale - 1) % 24
    ora_dopo = (ora_centrale + 1) % 24
    return f"tra {ora_con_articolo(ora_prima)} e {ora_con_articolo(ora_dopo)}"

def interpella_groq_semplice(giorno_str, fascia, tipo_pioggia, max_vento_arrotondato, trasl_kmh, trasl_dir, grandine_str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: return "Errore: Manca la chiave API di Groq."
    client = Groq(api_key=api_key)
    
    velocita_str = classificazione_traslazione_avverbio(trasl_kmh)
    dir_testuale = formatta_direzione_bussola(trasl_dir)
    
    prompt = f"""
    Sei un meteorologo che parla al pubblico in modo diretto e chiaro. Per la giornata del {giorno_str} a Rivoli sono previsti fenomeni.

    DEVI CREARE UN UNICO PARAGRAFO FLUIDO SEGUENDO ESATTAMENTE QUESTE REGOLE:
    
    1. INIZIA TESTUALMENTE COSÌ E NON CAMBIARE UNA VIRGOLA (sostituisci solo i valori fra parentesi se non sono corretti, la struttura deve rimanere intatta): 
       "Dagli ultimi aggiornamenti sembrerebbero possibili rovesci o temporali {fascia}, potenzialmente accompagnati da {tipo_pioggia} e raffiche di vento fino a {max_vento_arrotondato} km/h."
    2. GRANDINE: Aggiungi "La grandine dovrebbe risultare {grandine_str}." (Nota: se il dato dice assente, scrivi semplicemente "La grandine dovrebbe risultare assente.")
    3. TRASLAZIONE: Aggiungi "Il sistema temporalesco traslerà {velocita_str} verso {dir_testuale}."
    4. CONCLUSIONE OBBLIGATORIA (Copia e incolla testualmente): "Attenzione: considera che si tratta di fenomenologia localizzata e difficilmente prevedibile, non è dunque da escludere che le precipitazioni interessino maggiormente i comuni limitrofi o lascino addirittura completamente all'asciutto la tua zona."
    
    IMPORTANTE: Unisci queste frasi per formare un unico blocco di testo leggibile. NON USARE HTML, NON SCRIVERE ALTRO. NON USARE TERMINI TECNICI E NON CREARE LISTE.
    """
    try:
        return client.chat.completions.create(messages=[{"role":"user","content":prompt}], model="llama-3.3-70b-versatile", temperature=0.2).choices[0].message.content
    except Exception as e:
        return f"Errore AI Groq: {e}"

def main():
    FILE_LOCK = "lock_temporali_semplice.txt"
    oggi = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(FILE_LOCK):
        with open(FILE_LOCK, "r") as f:
            if f.read().strip() == oggi: 
                print("✅ Analisi temporali già inviata oggi. Esecuzione terminata per evitare spam.")
                sys.exit(0)

    giorni = check_probabilita_precipitazione()
    if not giorni: return
    
    hourly = fetch_dati_termodinamici()
    hourly_ecmwf = fetch_ecmwf_pwat()
    
    corpo_messaggio = ""
    inviato_almeno_uno = False
    adesso = datetime.now()
    
    for data_str in giorni:
        indici_giorno = [i for i, t in enumerate(hourly['time']) if t.startswith(data_str)]
        if not indici_giorno: continue
        
        # FILTRO FONDAMENTALE: scarta le ore già passate
        indici_futuri = [i for i in indici_giorno if datetime.fromisoformat(hourly['time'][i]) >= adesso.replace(minute=0, second=0, microsecond=0)]
        
        if not indici_futuri:
            continue
        
        idx_picco = -1
        
        for i in indici_futuri:
            p_d2 = hourly.get('precipitation_probability_dwd_icon_d2', [])
            p_ch2 = hourly.get('precipitation_probability_meteoswiss_icon_ch2', [])
            
            val_d2 = p_d2[i] if len(p_d2) > i and p_d2[i] is not None else 0
            val_ch2 = p_ch2[i] if len(p_ch2) > i and p_ch2[i] is not None else 0
            
            if (val_d2 >= 15 or val_ch2 >= 15) or (val_d2 >= 10 and val_ch2 >= 10):
                idx_picco = i
                break
        
        if idx_picco == -1:
            idx_16 = [i for i in indici_futuri if hourly['time'][i].endswith("16:00")]
            if idx_16:
                idx_picco = idx_16[0]
            else:
                print(f"[{data_str}] Rischio temporalesco nullo nelle ore rimanenti. Salto.")
                continue
            
        indici_attivi = [idx for idx in range(idx_picco - 3, idx_picco + 1) if 0 <= idx < len(hourly['time'])]
        
        cape = max_sicuro([hourly['cape_dwd_icon_d2'][i] for i in indici_attivi])
        updraft = max_sicuro([hourly['updraft_dwd_icon_d2'][i] for i in indici_attivi])
        gust = max_sicuro([hourly['wind_gusts_10m_dwd_icon_d2'][i] for i in indici_attivi])
        vento_arrotondato = arrotonda_decina(gust)
        
        min_base = min_sicuro([hourly['convective_cloud_base_dwd_icon_d2'][i] for i in indici_attivi])
        max_top = max_sicuro([hourly['convective_cloud_top_dwd_icon_d2'][i] for i in indici_attivi])
        spessore = (max_top - min_base) if min_base and max_top else 0
        z_termico = media_sicura([hourly['freezing_level_height_dwd_icon_d2'][i] for i in indici_attivi])

        if hourly_ecmwf:
            pwat = max_sicuro([hourly_ecmwf['total_column_integrated_water_vapour'][i] for i in indici_attivi if i < len(hourly_ecmwf['total_column_integrated_water_vapour'])])
        else:
            pwat = 0
            
        tipo_pioggia = stima_intensita_pioggia(pwat)

        u_10, v_10 = [], []
        u_850, v_850 = [], []
        u_700, v_700 = [], []
        u_500, v_500 = [], []

        for i in indici_attivi:
            w_speed_10 = hourly['wind_speed_1000hPa_dwd_icon_d2'][i] if hourly['wind_speed_1000hPa_dwd_icon_d2'][i] else 0
            w_dir_10 = hourly['wind_direction_1000hPa_dwd_icon_d2'][i] if hourly['wind_direction_1000hPa_dwd_icon_d2'][i] else 0
            w_speed_850 = hourly['wind_speed_850hPa_dwd_icon_d2'][i] if hourly['wind_speed_850hPa_dwd_icon_d2'][i] else 0
            w_dir_850 = hourly['wind_direction_850hPa_dwd_icon_d2'][i] if hourly['wind_direction_850hPa_dwd_icon_d2'][i] else 0
            w_speed_700 = hourly['wind_speed_700hPa_dwd_icon_d2'][i] if hourly['wind_speed_700hPa_dwd_icon_d2'][i] else 0
            w_dir_700 = hourly['wind_direction_700hPa_dwd_icon_d2'][i] if hourly['wind_direction_700hPa_dwd_icon_d2'][i] else 0
            w_speed_500 = hourly['wind_speed_500hPa_dwd_icon_d2'][i] if hourly['wind_speed_500hPa_dwd_icon_d2'][i] else 0
            w_dir_500 = hourly['wind_direction_500hPa_dwd_icon_d2'][i] if hourly['wind_direction_500hPa_dwd_icon_d2'][i] else 0

            u, v = scomposizione_vettoriale(w_speed_10, w_dir_10)
            u_10.append(u); v_10.append(v)
            u, v = scomposizione_vettoriale(w_speed_850, w_dir_850)
            u_850.append(u); v_850.append(v)
            u, v = scomposizione_vettoriale(w_speed_700, w_dir_700)
            u_700.append(u); v_700.append(v)
            u, v = scomposizione_vettoriale(w_speed_500, w_dir_500)
            u_500.append(u); v_500.append(v)

        avg_u10, avg_v10 = sum(u_10)/len(u_10), sum(v_10)/len(v_10)
        avg_u850, avg_v850 = sum(u_850)/len(u_850), sum(v_850)/len(v_850)
        avg_u700, avg_v700 = sum(u_700)/len(u_700), sum(v_700)/len(v_700)
        avg_u500, avg_v500 = sum(u_500)/len(u_500), sum(v_500)/len(v_500)

        dls = magnitudo_shear(avg_u10, avg_v10, avg_u500, avg_v500)
        trasl_kmh, trasl_dir = calcola_vettore_traslazione((avg_u850+avg_u700+avg_u500)/3, (avg_v850+avg_v700+avg_v500)/3)
        
        grandine_str = stima_grandine_pubblico(cape, updraft, dls, z_termico, spessore)
        ora_stringa = datetime.fromisoformat(hourly['time'][idx_picco]).strftime('%H:%M')
        fascia = formatta_fascia_oraria(ora_stringa)
        
        giorno_formattato = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        testo = interpella_groq_semplice(giorno_formattato, fascia, tipo_pioggia, vento_arrotondato, trasl_kmh, trasl_dir, grandine_str)
        
        if not testo.startswith("Errore AI Groq"):
            testo = testo.replace('<', '&lt;').replace('>', '&gt;')
        
        corpo_messaggio += f"📅 <b>{giorno_formattato}</b>\n\n{testo}\n\n➖➖➖➖➖➖➖➖➖➖\n\n"
        inviato_almeno_uno = True

    if inviato_almeno_uno:
        corpo_messaggio = corpo_messaggio.rstrip("➖➖➖➖➖➖➖➖➖➖\n\n")
        titolo = "⛈ <b>Avviso per possibili temporali</b>\n\n"
        messaggio_telegram = titolo + corpo_messaggio
        
        token = os.getenv('TELEGRAM_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if token and chat_id:
            res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={
                "chat_id": chat_id, "text": messaggio_telegram, "parse_mode": "HTML"
            })
            if res.status_code == 200:
                with open(FILE_LOCK, "w") as f: f.write(oggi)

if __name__ == "__main__":
    main()
