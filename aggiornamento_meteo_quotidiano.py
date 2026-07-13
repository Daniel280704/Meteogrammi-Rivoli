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

# ---------------------------------------------------------------------------
# UTILITY DI RETE E FORMATTAZIONE
# ---------------------------------------------------------------------------

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

def gradi_a_direzione(gradi):
    if gradi is None: return "N/D"
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'N']
    return dirs[int(round(gradi / 45.0)) % 8]

# ---------------------------------------------------------------------------
# UNICA LOGICA "DETERMINISTICA" CHE RESTA IN PYTHON: il disagio termico è un
# indice tabellare preciso (tipo heat-index), non un giudizio interpretativo.
# Lo teniamo qui per evitare che Grok "inventi" un valore leggermente diverso
# ogni volta: glielo forniamo già calcolato e lui deve solo riportarlo.
# ---------------------------------------------------------------------------

def calcola_disagio_caldo(t_aria, dew_point):
    if t_aria >= 40 and dew_point >= 15: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 38 and dew_point >= 18: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 36 and dew_point >= 20: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 34 and dew_point >= 22: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 32 and dew_point >= 24: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 30 and dew_point >= 25: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 28 and dew_point >= 26: return "(disagio estremo 🟣 - ELEVATO PERICOLO)"
    elif t_aria >= 38 and dew_point >= 12: return "(disagio forte 🔴)"
    elif t_aria >= 36 and dew_point >= 15: return "(disagio forte 🔴)"
    elif t_aria >= 34 and dew_point >= 18: return "(disagio forte 🔴)"
    elif t_aria >= 32 and dew_point >= 20: return "(disagio forte 🔴)"
    elif t_aria >= 30 and dew_point >= 22: return "(disagio forte 🔴)"
    elif t_aria >= 28 and dew_point >= 24: return "(disagio forte 🔴)"
    elif t_aria >= 26 and dew_point >= 25: return "(disagio forte 🔴)"
    elif t_aria >= 36 and dew_point >= 10: return "(disagio marcato 🟠)"
    elif t_aria >= 34 and dew_point >= 13: return "(disagio marcato 🟠)"
    elif t_aria >= 32 and dew_point >= 16: return "(disagio marcato 🟠)"
    elif t_aria >= 30 and dew_point >= 18: return "(disagio marcato 🟠)"
    elif t_aria >= 28 and dew_point >= 20: return "(disagio marcato 🟠)"
    elif t_aria >= 26 and dew_point >= 22: return "(disagio marcato 🟠)"
    elif t_aria >= 24 and dew_point >= 24: return "(disagio marcato 🟠)"
    elif t_aria >= 32 and dew_point >= 8: return "(disagio lieve 🟡)"
    elif t_aria >= 30 and dew_point >= 11: return "(disagio lieve 🟡)"
    elif t_aria >= 28 and dew_point >= 13: return "(disagio lieve 🟡)"
    elif t_aria >= 26 and dew_point >= 15: return "(disagio lieve 🟡)"
    elif t_aria >= 24 and dew_point >= 17: return "(disagio lieve 🟡)"
    elif t_aria >= 22 and dew_point >= 19: return "(disagio lieve 🟡)"
    else:
        return "(nessun disagio o caldo tollerabile 🟢)"

def calcola_disagio_freddo(windchill):
    if windchill < -40: return "(disagio estremo da freddo 🥶)"
    elif windchill < -25: return "(disagio forte da freddo 🥶)"
    elif windchill < -10: return "(disagio marcato da freddo 🥶)"
    elif windchill < 0: return "(disagio lieve da freddo 🥶)"
    else:
        return "(nessun disagio o freddo tollerabile 🟢)"

# ---------------------------------------------------------------------------
# STATISTICHE SUGLI ENSEMBLE (pura matematica, nessuna interpretazione)
# ---------------------------------------------------------------------------

def media_lista(lista):
    v = [x for x in lista if x is not None]
    return round(sum(v) / len(v), 1) if v else None

def min_lista(lista):
    v = [x for x in lista if x is not None]
    return round(min(v), 1) if v else None

def max_lista(lista):
    v = [x for x in lista if x is not None]
    return round(max(v), 1) if v else None

def n_membri(lista):
    return len([x for x in lista if x is not None])

def pct_superamento(lista, soglia):
    v = [x for x in lista if x is not None]
    if not v: return 0
    return round((sum(1 for x in v if x >= soglia) / len(v)) * 100)

def n_superamento(lista, soglia):
    v = [x for x in lista if x is not None]
    return sum(1 for x in v if x >= soglia)

# ---------------------------------------------------------------------------
# CHIAMATA A GROK (xAI) — qui avviene il "ragionamento meteorologico"
# ---------------------------------------------------------------------------

MODELLO_GROK = os.getenv("GROK_MODEL", "grok-4.3")

REGOLE_METEO = """
SEI UN METEOROLOGO PROFESSIONISTA. Ricevi dati grezzi orari (medie, minimi, massimi e
percentuali di superamento soglia calcolate sull'ensemble ICON-D2/CH2 di MeteoSwiss, più
il run deterministico) relativi a Rivoli (TO), Piemonte. Il tuo compito è LEGGERE i numeri,
INCROCIARLI TRA LORO come farebbe un previsore umano, e scrivere un bollettino discorsivo.
Non ti viene fornita alcuna etichetta già pronta (tranne il disagio termico): sei tu a dover
decidere se e come descrivere instabilità, tipo di precipitazione, vento, nuvolosità, nebbia,
integrando le informazioni invece di applicarle in modo rigido e sequenziale.

LEGENDA DEI CAMPI DI OGNI RIGA ORARIA:
- T=media(min–max membri)°C → temperatura a 2m, media d'ensemble e range tra i membri (il
  range ampio indica bassa affidabilità/alta incertezza su quell'ora, il range stretto alta
  concordanza)
- DP=°C → dew point (punto di rugiada) medio
- APP=°C → temperatura apparente/percepita media
- RH=% → umidità relativa media
- W=vel/raffica km/h (direzione) → vento medio, raffica media, direzione cardinale
- SUN=min → minuti di soleggiamento effettivo in quell'ora (0–60, 0=cielo coperto, 60=sole
  pieno per l'intera ora); GIORNO=SI/NO indica se l'ora ricade nella finestra diurna utile
  (tra due ore dopo l'alba e due ore prima del tramonto)
- PREC_D2=mm medi [>=1mm: n%, >=3mm: n%, >=5mm: n%, membri attivi: x/y] → precipitazione
  media dell'ensemble ICON-D2 e percentuale di membri che superano le soglie di 1/3/5 mm in
  quell'ora, con conteggio membri con dato valido
- PREC_CH2=... (se presente) → stesso identico significato ma calcolato sull'ensemble
  ICON-CH2, un modello a copertura leggermente diversa: usalo come CONFERMA incrociata del
  D2. Se CH2 non è disponibile per quell'esecuzione, il campo non compare: basati solo su D2.
- CAPE=J/kg → energia potenziale convettiva disponibile (dal run deterministico)
- Q:1000=...,975=...,...,800=°C → SOLO nelle ore fredde (T media sotto i 2°C), temperature ai
  livelli di pressione da 1000 a 800 hPa, per capire se in quota c'è uno strato caldo
  (inversione termica) sopra una colonna d'aria fredda al suolo

REGOLE DI INTERPRETAZIONE METEOROLOGICA DA APPLICARE (equivalenti a quelle che prima
applicava un codice Python rigido — ora le applichi tu, con più capacità di integrare i segnali
e gestire i casi limite/ambigui con buon senso):

1) NUVOLOSITÀ (solo ore con GIORNO=SI): usa i minuti di sole SUN per farti un'idea
   dell'andamento del cielo nelle varie fasi del giorno (mattina/ore centrali/pomeriggio/sera),
   non ora per ora. Come riferimento di massima: <10 min/h → molto nuvoloso o coperto; 10–25 →
   irregolarmente o molto nuvoloso; 25–40 → parzialmente o irregolarmente nuvoloso; 40–50 →
   parzialmente nuvoloso; 50–57 → poco nuvoloso; >57 → sereno. Usa questi termini con
   naturalezza, variando la costruzione della frase: è VIETATO ripetere la parola "cielo" a
   distanza ravvicinata nello stesso paragrafo.

2) INSTABILITÀ CONVETTIVA — SOLO nel semestre maggio-settembre: valuta se più membri
   dell'ensemble (D2, e se presente anche CH2 per conferma incrociata) superano 1 mm in
   un'ora: se la concordanza è bassa (pochi membri, percentuali basse su tutte le soglie) il
   segnale è debole o assente e NON va citato; se cresce il numero di membri concordi e le
   percentuali di superamento a 3-5mm, il segnale è più solido. Traduci il livello di accordo
   in un tono probabilistico onesto (es. "un aumento dell'instabilità con possibili rovesci
   (60%)"), scegliendo tu la percentuale più rappresentativa in base a quanto i membri
   concordano complessivamente nella fascia oraria più critica — se più ore della stessa fase
   del giorno sono instabili, riassumile in un'unica indicazione con la probabilità più alta,
   senza elencare gli orari. Se CAPE supera circa 200 J/kg nelle ore instabili, il fenomeno può
   assumere carattere di rovescio o temporale; con CAPE più basso resta un semplice rovescio.

3) PERTURBAZIONE INVERNALE/AUTUNNALE — SOLO nel semestre ottobre-aprile: se una quota
   consistente e concorde dei membri (D2, confermata da CH2 se presente) supera 1 mm/h per più
   ore consecutive, si tratta di transito perturbato: NON usare mai la parola "instabilità" né
   percentuali probabilistiche in questo caso, è un fenomeno organizzato e non convettivo.
   Aggrega le fasce orarie coinvolte, valuta l'intensità media delle precipitazioni (debole
   sotto i 2 mm/h, moderata tra 2 e 5 mm/h, forte sopra i 5 mm/h, con possibili variazioni nel
   tempo) e individua SEMPRE l'orario del picco di intensità massima, citandolo con il valore
   in mm/h.
   Tipo di precipitazione: se la temperatura è sotto i 2°C, guarda i dati Q ai vari livelli di
   pressione — se qualche livello resta sopra 1°C mentre al suolo fa freddo, c'è un'inversione
   termica: se la T al suolo è comunque sopra 0°C parla di "pioggia dovuta a inversione termica
   in quota", se invece la T al suolo è sotto 0°C segnala chiaramente il PERICOLO di pioggia
   congelante/gelicidio; se non c'è inversione (tutti i livelli freddi) è neve. Sopra i 2°C è
   pioggia normale. Usa il buon senso per le fasi di transizione (es. temperatura vicina alla
   soglia, quota in oscillazione).

4) VENTO: classifica l'intensità dalla raffica/velocità media (indicativamente: oltre 75
   km/h di raffica o 40 di media = tempestosa; 55/30 = forte; 40/20 = modesta; sotto = blanda).
   Se siamo in un'ora estiva già coinvolta da instabilità/temporale, NON descrivere
   separatamente il vento: è implicito nel fenomeno convettivo. Cerca anche pattern dinamici
   confrontando un'ora con la precedente: un aumento deciso di raffica con provenienza da
   NW/N/W accompagnato da un calo del punto di rugiada suggerisce un possibile Föhn (vento
   secco e mite/caldo); un aumento di umidità relativa con provenienza da E/NE/SE suggerisce
   vento umido orientale. Cita il vento nel testo solo se l'intensità è modesta o superiore.

5) NEBBIA: se il punto di rugiada è molto vicino alla temperatura (scarto di circa 1°C o
   meno), l'umidità relativa è molto alta (95%+) e il vento è debole (sotto 10 km/h), è
   plausibile una formazione di nebbia, soprattutto nelle ore più fredde della giornata.

6) DISAGIO TERMICO: ti viene fornito già calcolato (valore e dicitura con emoji): riportalo
   ESATTAMENTE come scritto, accostato alla temperatura massima, senza modificarlo o
   ricalcolarlo.

REGOLE FERREE DI SCRITTURA E IMPAGINAZIONE (PENA IL FALLIMENTO):
1. TITOLO: inizia ESATTAMENTE con "<b>Aggiornamento meteo di {oggi_str}</b>", poi una riga
   vuota, poi il primo paragrafo. Lascia una riga vuota anche tra i due paragrafi.
2. STRUTTURA: esattamente due paragrafi discorsivi: il primo per la giornata di oggi, il
   secondo per quella di domani.
3. DIVIETO ASSOLUTO di elencare temperature o dati ora per ora: sintetizza per fasi della
   giornata ("in mattinata", "nelle ore centrali", "nel pomeriggio", "in serata").
4. Cita solo la temperatura minima e la temperatura massima di ciascuna giornata (fornite nei
   dati), mai valori intermedi.
5. FLUIDITÀ: evita ripetizioni ravvicinate delle stesse parole, il testo deve scorrere in modo
   naturale e professionale, come un vero bollettino meteo.
6. DIVIETO ASSOLUTO DI MARKDOWN: niente asterischi (*), underscore (_) o simili — Telegram
   va in crash. Usa solo testo pulito e il tag HTML <b> per il titolo.
7. Se dai dati non emerge nulla di rilevante (niente instabilità, niente perturbazione, vento
   blando, cielo sereno) scrivi comunque un paragrafo scorrevole che descriva la giornata
   stabile, senza inventare fenomeni.

ESEMPIO DI STILE ESTIVO DA IMITARE (il contenuto è solo un esempio, i dati reali sono sotto):
<b>Aggiornamento meteo di domenica 12 luglio</b>

La giornata odierna si apre con stabilità atmosferica. Le minime si assestano sui 19°C.
Durante le ore di luce il cielo si manterrà in prevalenza sereno, portando la massima a 33°C
(disagio marcato 🟠). Nel tardo pomeriggio si segnala un aumento dell'instabilità con possibili
rovesci o temporali (40%). In serata situazione in miglioramento.

La giornata di domani seguirà un copione simile...

ESEMPIO DI STILE INVERNALE DA IMITARE:
<b>Aggiornamento meteo di domenica 12 dicembre</b>

La giornata odierna vedrà un progressivo peggioramento. Le temperature oscilleranno tra una
minima di 4°C e una massima di 8°C (nessun disagio o freddo tollerabile 🟢). Dal pomeriggio è
atteso il transito di una perturbazione con piogge deboli, che si intensificheranno in serata
divenendo moderate. Il picco massimo delle precipitazioni è atteso intorno alle 21:00 con circa
4.5 mm/h. La ventilazione si manterrà forte umida orientale.

La giornata di domani...
"""

def interpella_groq(dati_testuali, oggi_str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "Errore: GROQ_API_KEY non trovata."
        
    client = Groq(api_key=api_key)

    prompt_sistema = REGOLE_METEO.format(oggi_str=oggi_str)

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.25,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Errore AI Groq: {e}"

# ---------------------------------------------------------------------------
# COSTRUZIONE DELLA RIGA ORARIA GREZZA (nessuna interpretazione, solo numeri)
# ---------------------------------------------------------------------------

def costruisci_riga_oraria(ora_dt, giorno_label, t_mean, t_min, t_max, dew_mean, app_mean,
                            ur_mean, w_spd_mean, w_gst_mean, w_dir_str, sun_min, giorno_flag,
                            prec_d2_mean, pct_d2_1, pct_d2_3, pct_d2_5, n_d2,
                            prec_ch2_mean, pct_ch2_1, pct_ch2_3, pct_ch2_5, n_ch2,
                            cape, strati_quota):
    riga = (f"[{giorno_label}] {ora_dt.strftime('%H:%M')}: "
            f"T={t_mean}({t_min}-{t_max})°C DP={dew_mean}°C APP={app_mean}°C RH={ur_mean}% "
            f"W={w_spd_mean}/{w_gst_mean}km/h({w_dir_str}) SUN={sun_min}min GIORNO={'SI' if giorno_flag else 'NO'} "
            f"PREC_D2={prec_d2_mean}mm[>=1mm:{pct_d2_1}%,>=3mm:{pct_d2_3}%,>=5mm:{pct_d2_5}%,n={n_d2}]")
    if prec_ch2_mean is not None:
        riga += f" PREC_CH2={prec_ch2_mean}mm[>=1mm:{pct_ch2_1}%,>=3mm:{pct_ch2_3}%,>=5mm:{pct_ch2_5}%,n={n_ch2}]"
    riga += f" CAPE={cape}J/kg"
    if strati_quota:
        parti = [f"{lvl}={v}" for lvl, v in strati_quota if v is not None]
        if parti:
            riga += " Q:" + ",".join(parti)
    return riga

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    mese_corrente = datetime.now().month
    inverno = mese_corrente in [10, 11, 12, 1, 2, 3, 4]
    estate = mese_corrente in [5, 6, 7, 8, 9]

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
            "hourly": "wind_direction_10m,cape,sunshine_duration,temperature_1000hPa,temperature_975hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa",
            "daily": "sunrise,sunset",
            "models": "icon_d2",
            "timezone": "Europe/Rome", "forecast_days": 2
        })

        dati_eps_d2 = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,dew_point_2m,apparent_temperature",
            "models": "icon_d2",
            "timezone": "Europe/Rome", "forecast_days": 2
        })

        ch2_disponibile = True
        try:
            dati_eps_ch2 = scarica_dati_con_retry("https://ensemble-api.open-meteo.com/v1/ensemble", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "precipitation",
                "models": "meteoswiss_icon_ch2_ensemble",
                "timezone": "Europe/Rome", "forecast_days": 2
            })
            dati_det_ch2 = scarica_dati_con_retry("https://api.open-meteo.com/v1/forecast", params={
                "latitude": LAT, "longitude": LON,
                "hourly": "sunshine_duration",
                "models": "meteoswiss_icon_ch2",
                "timezone": "Europe/Rome", "forecast_days": 2
            })
            if 'hourly' not in dati_eps_ch2 or 'hourly' not in dati_det_ch2:
                ch2_disponibile = False
        except Exception:
            ch2_disponibile = False

    except Exception as e:
        print(f"❌ Errore fatale nel recupero dati Open-Meteo: {e}")
        return

    h_det = dati_det.get('hourly', {})
    h_eps_d2 = dati_eps_d2.get('hourly', {})
    h_eps_ch2 = dati_eps_ch2.get('hourly', {}) if ch2_disponibile else {}
    h_det_ch2 = dati_det_ch2.get('hourly', {}) if ch2_disponibile else {}
    orari = h_det.get('time', [])

    if not orari:
        print("❌ Errore: Dati orari non disponibili.")
        return

    sunrise_str = dati_det.get('daily', {}).get('sunrise', [])
    sunset_str = dati_det.get('daily', {}).get('sunset', [])

    righe_oggi = []
    righe_domani = []
    t_min_oggi, t_max_oggi = 100, -100
    t_min_domani, t_max_domani = 100, -100
    dew_max_oggi, dew_max_domani = -100, -100
    apparent_temperatures_medie = []

    for i in range(len(orari)):
        ora_dt = datetime.fromisoformat(orari[i])
        giorno_idx = 0 if i < 24 else 1

        t_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('temperature_2m_member')]
        t_mean, t_lo, t_hi = media_lista(t_membri), min_lista(t_membri), max_lista(t_membri)

        dew_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('dew_point_2m_member')]
        dew_mean = media_lista(dew_membri)

        app_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('apparent_temperature_member')]
        app_mean = media_lista(app_membri)
        apparent_temperatures_medie.append(app_mean if app_mean is not None else 0)

        ur_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('relative_humidity_2m_member')]
        ur_mean = media_lista(ur_membri)

        w_spd_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('wind_speed_10m_member')]
        w_spd_mean = media_lista(w_spd_membri)

        w_gst_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('wind_gusts_10m_member')]
        w_gst_mean = media_lista(w_gst_membri)

        w_dir = h_det.get('wind_direction_10m', [])[i] if i < len(h_det.get('wind_direction_10m', [])) else None
        w_dir_str = gradi_a_direzione(w_dir)

        prec_eps_d2_membri = [h_eps_d2[k][i] for k in h_eps_d2 if k.startswith('precipitation_member')]
        prec_d2_mean = media_lista(prec_eps_d2_membri) or 0.0
        pct_d2_1 = pct_superamento(prec_eps_d2_membri, 1.0)
        pct_d2_3 = pct_superamento(prec_eps_d2_membri, 3.0)
        pct_d2_5 = pct_superamento(prec_eps_d2_membri, 5.0)
        n_d2 = n_membri(prec_eps_d2_membri)

        prec_ch2_mean = pct_ch2_1 = pct_ch2_3 = pct_ch2_5 = n_ch2 = None
        if ch2_disponibile:
            prec_eps_ch2_membri = [h_eps_ch2[k][i] for k in h_eps_ch2 if k.startswith('precipitation_member')]
            if prec_eps_ch2_membri:
                prec_ch2_mean = media_lista(prec_eps_ch2_membri) or 0.0
                pct_ch2_1 = pct_superamento(prec_eps_ch2_membri, 1.0)
                pct_ch2_3 = pct_superamento(prec_eps_ch2_membri, 3.0)
                pct_ch2_5 = pct_superamento(prec_eps_ch2_membri, 5.0)
                n_ch2 = n_membri(prec_eps_ch2_membri)

        cape = h_det.get('cape', [])[i] if i < len(h_det.get('cape', [])) else None
        cape = round(cape) if cape is not None else 0

        if ch2_disponibile and h_det_ch2.get('sunshine_duration'):
            sun_sec = h_det_ch2['sunshine_duration'][i] if i < len(h_det_ch2['sunshine_duration']) else 0
        else:
            sun_sec = h_det.get('sunshine_duration', [])[i] if i < len(h_det.get('sunshine_duration', [])) else 0
        sun_min = round((sun_sec or 0) / 60)

        alba = datetime.fromisoformat(sunrise_str[giorno_idx])
        tramonto = datetime.fromisoformat(sunset_str[giorno_idx])
        giorno_flag = (alba + timedelta(hours=2)) <= ora_dt <= (tramonto - timedelta(hours=2))

        strati_quota = None
        if t_mean is not None and t_mean < 3:
            livelli = ['1000hPa', '975hPa', '950hPa', '925hPa', '900hPa', '850hPa', '800hPa']
            strati_quota = []
            for lvl in livelli:
                arr = h_det.get(f'temperature_{lvl}', [])
                v = round(arr[i], 1) if i < len(arr) and arr[i] is not None else None
                strati_quota.append((lvl, v))

        giorno_label = "OGGI" if giorno_idx == 0 else "DOMANI"
        riga = costruisci_riga_oraria(
            ora_dt, giorno_label, t_mean, t_lo, t_hi, dew_mean, app_mean, ur_mean,
            w_spd_mean, w_gst_mean, w_dir_str, sun_min, giorno_flag,
            prec_d2_mean, pct_d2_1, pct_d2_3, pct_d2_5, n_d2,
            prec_ch2_mean, pct_ch2_1, pct_ch2_3, pct_ch2_5, n_ch2,
            cape, strati_quota
        )

        if giorno_idx == 0:
            righe_oggi.append(riga)
            if t_mean is not None:
                t_min_oggi = min(t_min_oggi, t_mean)
                t_max_oggi = max(t_max_oggi, t_mean)
            if dew_mean is not None and estate:
                dew_max_oggi = max(dew_max_oggi, dew_mean)
        else:
            righe_domani.append(riga)
            if t_mean is not None:
                t_min_domani = min(t_min_domani, t_mean)
                t_max_domani = max(t_max_domani, t_mean)
            if dew_mean is not None and estate:
                dew_max_domani = max(dew_max_domani, dew_mean)

    disagio_oggi = ""
    disagio_domani = ""
    if estate:
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

    testo_per_ia = f"""GIORNO 1 ({oggi_str}):
- Temperatura minima: {t_min_oggi}°C
- Temperatura massima: {t_max_oggi}°C {disagio_oggi}
DATI ORARI GREZZI:
{chr(10).join(righe_oggi)}

GIORNO 2 ({domani_str}):
- Temperatura minima: {t_min_domani}°C
- Temperatura massima: {t_max_domani}°C {disagio_domani}
DATI ORARI GREZZI:
{chr(10).join(righe_domani)}
"""

    bollettino_finale = interpella_grok(testo_per_ia, oggi_str)

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        risposta_tg = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": bollettino_finale, "parse_mode": "HTML"})
        if risposta_tg.status_code == 200:
            print("Bollettino inviato con successo!")
            with open(FILE_LOCK, "w") as f:
                f.write(oggi_str_lock)
        else:
            print(f"Errore Telegram: {risposta_tg.text}")
    else:
        print("Errore: Token o Chat ID mancanti! Stampo a video:")
        print("-------------------------------------------------")
        print(bollettino_finale)

if __name__ == "__main__":
    main()
