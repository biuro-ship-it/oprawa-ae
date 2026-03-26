from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import pandas as pd
import re
import os
from fpdf import FPDF

app = FastAPI()

# --- ŚCIEŻKI ---
# Vercel montuje pliki w /var/task
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates_path = os.path.join(BASE_DIR, "templates")

# Inicjalizacja szablonów
templates = Jinja2Templates(directory=templates_path)

VAT = 1.23

def clean_pl(text):
    if not text: return ""
    pl_map = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return str(text).translate(pl_map)

def load_data():
    try:
        csv_path = os.path.join(BASE_DIR, 'cennik.csv')
        if not os.path.exists(csv_path):
            print(f"BŁĄD: Nie znaleziono pliku {csv_path}")
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
        print(f"BŁĄD load_data: {e}")
        return None, None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Nowoczesny sposób przekazywania requestu w FastAPI
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"title": "Antyramy.eu"}
    )

@app.get("/api/calculate")
async def calculate(query: str):
    df, config = load_data()
    if df is None: return {"error": "Problem z plikiem cennika na serwerze."}

    liczby = re.findall(r'\d+', query)
    if not liczby: return {"error": "Podaj kod listwy."}

    kod_szukany = liczby[0]
    wybrana = df[df['kod'] == kod_szukany]
    
    if wybrana.empty: return {"error": f"Nie znaleziono listwy {kod_szukany}"}

    l = wybrana.iloc[0]
    szer = float(liczby[1]) if len(liczby) >= 2 else 30.0
    wys = float(liczby[2]) if len(liczby) >= 3 else 40.0
    
    try:
        sz_listwy = float(str(l['szerokosc']).replace(',', '.'))
        c_l_netto = float(str(l['cena_l_netto']).replace(',', '.'))
        c_o_netto = float(str(l['cena_o_netto']).replace(',', '.'))
    except:
        return {"error": "Błąd danych w cenniku."}

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
    pdf = FPDF()
    pdf.add_page()
    # fpdf2 używa 'text' zamiast pozycyjnych argumentów dla pełnej jasności
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(w=0, h=10, text="WYCENA OPRAWY - ANTYRAMY.EU", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(w=0, h=10, text=clean_pl(f"Kod listwy: {kod}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(w=0, h=10, text=clean_pl(f"Wymiary: {int(s)} x {int(w)} cm"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.multi_cell(w=0, h=10, text=clean_pl(f"Elementy: {opis.replace('|', ', ')}"))
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(w=0, h=10, text=f"SUMA: {suma:.2f} PLN")
    
    # fpdf2 zwraca bytes przy wywołaniu output() bez argumentów
    return Response(
        content=bytes(pdf.output()), 
        media_type="application/pdf", 
        headers={"Content-Disposition": f"attachment; filename=wycena_{kod}.pdf"}
    )