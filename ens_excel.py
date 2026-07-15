#!/usr/bin/env python3
import os
import sys
import requests
import pandas as pd
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

LAT = 45.073475
LON = 7.543461
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"

def fetch_data():
    """Scarica i dati ensemble da Open-Meteo includendo tutti i parametri richiesti."""
    variabili = "temperature_2m,precipitation,dew_point_2m,relative_humidity_2m,freezing_level_height"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "models": "icon_d2",
        "hourly": variabili,
        "forecast_days": 2,
        "timezone": "Europe/Rome"
    }
    print("⏳ Download dati da Open-Meteo in corso...")
    resp = requests.get(ENSEMBLE_URL, params=params, timeout=90)
    resp.raise_for_status()
    return resp.json()

def genera_excel(data, out_path):
    """Elabora i dati JSON aggregando min/max/media e calcolando le probabilità di pioggia."""
    print("📊 Generazione del file Excel in corso...")
    df = pd.DataFrame(data['hourly'])
    df['time'] = pd.to_datetime(df['time'])

    # Creazione del dataframe riassuntivo
    summary_df = pd.DataFrame({'Data_Ora': df['time'].dt.strftime('%Y-%m-%d %H:%M')})

    # Dizionario delle variabili da calcolare
    metriche_base = {
        'temperature_2m': ('Temp', '°C'),
        'dew_point_2m': ('DewPoint', '°C'),
        'relative_humidity_2m': ('Umidita', '%'),
        'freezing_level_height': ('ZeroTermico', 'm'),
        'precipitation': ('Precip', 'mm')
    }

    # Calcolo Min, Max, Media per ciascuna variabile
    for var, (nome, unita) in metriche_base.items():
        cols = [c for c in df.columns if var in c]
        if cols:
            summary_df[f'{nome} Min ({unita})'] = df[cols].min(axis=1)
            summary_df[f'{nome} Media ({unita})'] = df[cols].mean(axis=1)
            summary_df[f'{nome} Max ({unita})'] = df[cols].max(axis=1)

    # Calcolo Probabilità di Precipitazione (da 1 a 30 mm)
    precip_cols = [c for c in df.columns if 'precipitation' in c]
    if precip_cols:
        for p in range(1, 31):
            # Conta quanti membri superano o eguagliano la soglia 'p' e divide per il numero di membri
            summary_df[f'Prob Pioggia >{p}mm'] = (df[precip_cols] >= p).sum(axis=1) / len(precip_cols)

    # Scrittura su Excel
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Analisi_Ensemble', index=False)

    # --- Formattazione e Stili con OpenPyXL ---
    wb = openpyxl.load_workbook(out_path)
    ws = wb['Analisi_Ensemble']
    ws.freeze_panes = "B2" # Blocca la prima riga e la prima colonna
    
    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    alt_row_fill = PatternFill(start_color="F2F4F4", end_color="F2F4F4", fill_type="solid")
    border = Border(left=Side(style='thin', color='D5D8DC'), right=Side(style='thin', color='D5D8DC'), 
                    top=Side(style='thin', color='D5D8DC'), bottom=Side(style='thin', color='D5D8DC'))
    center_align = Alignment(horizontal="center", vertical="center")

    # Stile intestazione
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = border
        
    # Adattamento larghezza colonne e stili righe
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        intestazione = str(ws.cell(row=1, column=col[0].column).value)
        
        for i, cell in enumerate(col):
            if cell.value: 
                max_length = max(max_length, len(str(cell.value)))
            
            if i > 0: # Righe dati
                cell.border = border
                cell.alignment = center_align
                if (i + 1) % 2 == 0: 
                    cell.fill = alt_row_fill
                
                # Formattazione numerica
                if isinstance(cell.value, (int, float)):
                    if "Prob" in intestazione:
                        cell.number_format = '0.0%' # Percentuale per probabilità
                    elif "ZeroTermico" in intestazione:
                        cell.number_format = '#,##0' # Interi per lo zero termico
                    else:
                        cell.number_format = '0.00' # Decimali per temp, umidità, precipitazioni

        # Larghezza colonna basata sull'intestazione o sui dati
        lunghezza_adattata = max(len(intestazione) + 2, max_length + 2)
        ws.column_dimensions[column].width = min(lunghezza_adattata, 20) # Max 20 per non renderle enormi

    wb.save(out_path)
    print(f"✅ File salvato in: {out_path}")

def invia_documento_telegram(percorso_file, didascalia):
    """Invia il file Excel tramite le API di Telegram (sendDocument)."""
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Credenziali Telegram mancanti. Salto l'invio.", file=sys.stderr)
        return

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    print("📤 Invio file su Telegram in corso...")
    
    try:
        with open(percorso_file, "rb") as documento:
            resp = requests.post(
                url, 
                data={"chat_id": chat_id, "caption": didascalia}, 
                files={"document": documento},
                timeout=60
            )
            resp.raise_for_status()
        print(f"✅ Inviato {percorso_file} su Telegram!")
    except Exception as e:
        print(f"❌ Errore invio Telegram: {e}", file=sys.stderr)

def main():
    out_path = "Dati_Ensemble_Rivoli_ICON_D2.xlsx"
    try:
        dati = fetch_data()
        genera_excel(dati, out_path)
        
        ora_esecuzione = datetime.now().strftime("%d/%m/%Y alle %H:%M")
        didascalia = f"📉 Dati Tabellari ICON-D2 EPS\n📍 Rivoli (TO) - Aggiornato il {ora_esecuzione}\n\nTermiche, DewPoint, UR%, Zero Termico e Probabilità di Precipitazione"
        
        invia_documento_telegram(out_path, didascalia)
    except Exception as e:
        print(f"❌ Errore critico: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()