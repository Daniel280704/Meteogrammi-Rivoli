import os
import requests
import metview as mv

def invia_telegram(file_path: str, caption: str):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id: 
        print("Credenziali Telegram mancanti.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": caption}
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as photo:
                requests.post(url, data=payload, files={"photo": photo})
            print("📸 Immagine inviata su Telegram!")
        except Exception as e:
            print(f"Errore invio Telegram: {e}")

def genera_mappa_test_locale(file_start: str, file_end: str):
    print(f"Leggo i file locali: {file_start} e {file_end}...")
    
    # Impostazioni mappa Piemonte
    coast = mv.mcoast(
        map_coastline_colour="brown", 
        map_coastline_thickness=2, 
        map_coastline_resolution="high",
        map_boundaries="on", 
        map_boundaries_colour="brown", 
        map_boundaries_thickness=2,
        map_administrative_boundaries="on", 
        map_administrative_boundaries_colour="brown",
        map_administrative_boundaries_thickness=1, 
        map_grid="off", 
        map_label="off"
    )
    
    view = mv.geoview(
        map_area_definition="corners", 
        area=[43.5, 6.0, 46.8, 10.5], 
        coastlines=coast, 
        subpage_x_position=5, 
        subpage_y_position=12,   
        subpage_x_length=75, 
        subpage_y_length=80     
    )

    # Capoluoghi e Rivoli
    lats = [45.07, 44.38, 44.90, 44.91, 45.32, 45.45, 45.56, 45.92]
    lons = [7.68,  7.55,  8.20,  8.61,  8.42,  8.61,  8.05,  8.55]
    sigle = ["TO", "CN", "AT", "AL", "VC", "NO", "BI", "VB"]

    capoluoghi = mv.input_visualiser(input_plot_type="geo_points", input_longitude_values=lons, input_latitude_values=lats)
    stile_capoluoghi = mv.msymb(legend="off", symbol_type="text", symbol_text_list=sigle, symbol_text_font_colour="brown", symbol_text_font_size=0.5, symbol_text_font_style="bold")

    rivoli_point = mv.input_visualiser(input_plot_type="geo_points", input_longitude_values=[7.51], input_latitude_values=[45.07])
    stile_rivoli = mv.msymb(legend="off", symbol_type="marker", symbol_colour="brown", symbol_height=0.4, symbol_marker_index=15)

    # Stile Pioggia
    tp_style = mv.mcont(
        legend="on", contour="off", contour_shade="on",           
        contour_shade_technique="polygon_shading", contour_shade_method="area_fill",
        contour_level_selection_type="level_list",
        contour_level_list=[1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200, 300],
        contour_shade_colour_method="list",
        contour_shade_colour_list=[
            "RGB(0.6, 0.8, 1.0)", "RGB(0.0, 0.3, 1.0)", "RGB(0.4, 0.9, 0.4)", "RGB(0.0, 0.6, 0.0)", 
            "RGB(0.6, 0.8, 0.0)", "RGB(1.0, 0.9, 0.0)", "RGB(0.9, 0.7, 0.0)", "RGB(1.0, 0.6, 0.0)", 
            "RGB(1.0, 0.4, 0.0)", "RGB(1.0, 0.2, 0.0)", "RGB(1.0, 0.2, 0.2)", "RGB(0.7, 0.0, 0.0)", 
            "RGB(0.8, 0.2, 1.0)", "RGB(0.5, 0.0, 0.8)", "RGB(0.3, 0.0, 0.5)"
        ]
    )
    
    legend = mv.mlegend(
        legend_display_type="continuous", legend_box_mode="positional", 
        legend_box_x_position=26.5, legend_box_y_position=3.0, 
        legend_box_x_length=1.5, legend_box_y_length=14.0, legend_text_font_size=0.4
    )

    try:
        # Calcolo ensemble mean per i due file
        tp_start_ens = mv.mean(mv.read(file_start))
        tp_end_ens = mv.mean(mv.read(file_end))
        
        # Sottrazione per ottenere l'accumulo tra i due step
        tp_diff_mean = tp_end_ens - tp_start_ens
        
        title = mv.mtext(
            text_lines=["TEST LOCALE: ICON-CH2 EPS - Precipitazioni Medie", "Accumulo tra step 55 e step 101"], 
            text_font_size=0.5, text_colour='black'
        )
        
        PNG_OUTPUT = "test_rendering_metview"
        png = mv.png_output(output_name=PNG_OUTPUT, output_width=1200)
        mv.setoutput(png)
        mv.plot(view, tp_diff_mean, tp_style, capoluoghi, stile_capoluoghi, rivoli_point, stile_rivoli, legend, title)
        
        file_generato = f"{PNG_OUTPUT}.1.png"
        invia_telegram(file_generato, "🌧 Test Locale Mappa ICON-CH2: Accumulo pioggia da step 55 a step 101.")
        
    except Exception as e:
        print(f"❌ Errore durante l'elaborazione di Metview: {e}")

if __name__ == "__main__":
    FILE_1 = "icon-ch2-eps-202607230600-55-tot_prec-perturb.grib2"
    FILE_2 = "icon-ch2-eps-202607230600-101-tot_prec-perturb.grib2"
    
    if os.path.exists(FILE_1) and os.path.exists(FILE_2):
        genera_mappa_test_locale(FILE_1, FILE_2)
    else:
        print("ATTENZIONE: Non trovo i file GRIB. Controlla che i nomi siano esatti e nella radice della cartella.")