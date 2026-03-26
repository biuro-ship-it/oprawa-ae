from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import pandas as pd
import re
import os
from fpdf import FPDF

app = FastAPI()

# --- DIAGNOSTYKA ŚCIEŻEK ---
# Vercel montuje aplikację w /var/task
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print(f"DEBUG: BASE_DIR is {BASE_DIR}")
print(f"DEBUG: Content of BASE_DIR: {os.listdir(BASE_DIR)}")

# Próbujemy znaleźć folder templates
templates_dir = os.path.join(BASE_DIR, "templates")
if not os.path.exists(templates_dir):
    # Jeśli Vercel wrzucił templates do api/
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

templates = Jinja2Templates(directory=templates_dir)

VAT = 1.23

def clean_pl(text):
    pl_map = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return str(text).translate(pl_map)

def load_data():
    try:
        csv_path = os.path.join(BASE_DIR, 'cennik.csv')
        if not os.path.exists(csv_path):
            return None, None
        df_raw = pd.read_csv(csv_path, sep=';', decimal=',', header=None, dtype=str)
        
        def get_val_footer(keyword, col_idx):
            mask = df_raw[0].astype(str).str.lower().str.strip().str.contains(keyword.lower(), na=False)
            rows = df_raw[mask]
            if not rows.empty:
                val = str(rows.iloc[0, col_idx]).replace(',', '.')
                try: return float(val)
                except: return 0.0
            return 0.0

        prices = {
            'float': get_val_footer('float', 2),
            'hdf': get_val_footer('hdf', 2),
            'antyreflex': get_val_footer('anty', 2),
            'paspartu': get_val_footer('pas', 2),
            'marza_listwa': get_val_footer('mar', 2) / 100 if get_val_footer('mar', 2) > 0 else 0.5,
            'marza_oprawa': get_val_footer('mar', 3) / 100 if get_val_footer('mar', 3) > 0 else 0.3
        }

        df_frames = df_raw.iloc[2:].copy()
        stopka_mask = df_frames[0].astype(str).str.lower().str.contains('float|hdf|anty|pas|mar', na=False)
        if stopka_mask.any():
            stopka_idx = stopka_mask.idxmax()
            df_frames = df_frames.loc[:stopka_idx-1]
        
        df_frames.columns = ['kod', 'ilosc_mb', 'cena_l_netto', 'cena_o_netto', 'szerokosc']
        df_frames['kod'] = df_frames['kod'].astype(str).str.strip()
        return df_frames, prices
    except Exception as e:
        print(f"ERROR: load_data failed: {e}")
        return None, None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        return HTMLResponse(content=f"Błąd szablonu: {e}. Szukano w: {templates_dir}", status_code=500)

@app.get("/api/calculate")
async def calculate(query: str):
    df, config = load_data()
    if df is None: return {"error": "Nie znaleziono pliku cennik.csv"}

    liczby = re.findall(r'\d+', query)
    if not liczby: return {"error": "Wpisz kod."}

    kod_szukany = liczby[0]
    wybrana = df[df['kod'] == kod_szukany]
    
    if wybrana.empty: return {"error": f"Brak kodu {kod_szukany}"}

    l = wybrana.iloc[0]
    szer = float(liczby[1]) if len(liczby) >= 2 else 30.0
    wys = float(liczby[2]) if len(liczby) >= 3 else 40.0
    
    sz_listwy = float(str(l['szerokosc']).replace(',', '.'))
    c_l_netto = float(str(l['cena_l_netto']).replace(',', '.'))
    c_o_netto = float(str(l['cena_o_netto']).replace(',', '.'))

    obwod_m = ((2 * szer) + (2 * wys) + (8 * sz_listwy)) / 100
    pow_m2 = (szer * wys) / 10000

    return {
        "kod": l['kod'], "szer": szer, "wys": wys, "obwod": round(obwod_m, 2), "pow": round(pow_m2, 3),
        "results": {
            "listwa": round((c_l_netto * (1 + config['marza_listwa'])) * VAT * obwod_m, 2),
            "oprawa": round((c_o_netto * (1 + config['marza_oprawa'])) * VAT * obwod_m, 2),
            "float": round((config['float'] * VAT) * pow_m2, 2),
            "anty": round((config['antyreflex'] * VAT) * pow_m2, 2),
            "hdf": round((config['hdf'] * VAT) * pow_m2, 2),
            "pp": round((config['paspartu'] * VAT) * pow_m2, 2)
        }
    }

@app.get("/api/pdf")
async def generate_pdf(kod: str, s: float, w: float, suma: float, opis: str):
    # Używamy fpdf2 dla lepszej stabilności
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "WYCENA OPRAWY - ANTYRAMY.EU", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, clean_pl(f"Kod listwy: {kod}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, clean_pl(f"Wymiary: {int(s)} x {int(w)} cm"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.multi_cell(0, 10, clean_pl(f"Wybrane elementy:\n{opis.replace('|', ', ')}"))
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"SUMA: {suma:.2f} PLN", new_x="LMARGIN", new_y="NEXT")
    
    return Response(content=pdf.output(), media_type="application/pdf", 
                    headers={"Content-Disposition": f"attachment; filename=wycena_{kod}.pdf"})