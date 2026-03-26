from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import pandas as pd
import re
import os
from fpdf import FPDF

app = FastAPI()

# --- KONFIGURACJA ŚCIEŻEK ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- LOGIKA ŁADOWANIA DANYCH ---
def load_base_config():
    try:
        path = os.path.join(BASE_DIR, 'base_config.csv')
        df = pd.read_csv(path, sep=';', decimal=',', index_col='klucz')
        return df['wartosc'].to_dict()
    except:
        return {}

def load_producer_list(prod_id):
    try:
        file_path = os.path.join(BASE_DIR, 'cenniki', f'producent_{prod_id}.csv')
        df = pd.read_csv(file_path, sep=';', decimal=',', header=None, dtype=str)
        df.columns = ['kod', 'ilosc', 'c_l', 'c_o', 'szer']
        return df
    except:
        return None

# --- TRASY (ROUTES) ---

# TO JEST TA BRAKUJĄCA TRASA, KTÓRA NAPRAWI 404
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"title": "Antyramy.eu - Kalkulator"}
    )

@app.get("/api/codes")
async def get_codes(prod_id: str):
    df = load_producer_list(prod_id)
    if df is not None:
        return {"codes": df['kod'].dropna().unique().tolist()}
    return {"codes": []}

@app.get("/api/calculate")
async def calculate(prod_id: str, kod: str, szer: float, wys: float):
    df_prod = load_producer_list(prod_id)
    config = load_base_config()
    
    if df_prod is None or not config:
        return {"error": "Błąd danych cennika."}

    wybrana = df_prod[df_prod['kod'] == kod]
    if wybrana.empty: return {"error": "Brak kodu."}

    l = wybrana.iloc[0]
    sz_listwy = float(str(l['szer']).replace(',', '.'))
    c_l = float(str(l['c_l']).replace(',', '.'))
    c_o = float(str(l['c_o']).replace(',', '.'))

    obwod = ((2 * szer) + (2 * wys) + (8 * sz_listwy)) / 100
    pow_m2 = (szer * wys) / 10000
    VAT = 1.23

    return {
        "kod": l['kod'],
        "results": {
            "listwa": round((c_l * (1 + config.get('marza_listwa', 0.5))) * VAT * obwod, 2),
            "oprawa": round((c_o * (1 + config.get('marza_oprawa', 0.3))) * VAT * obwod, 2),
            "float": round((config.get('float', 0) * VAT) * pow_m2, 2),
            "anty": round((config.get('anty', 0) * VAT) * pow_m2, 2),
            "hdf": round((config.get('hdf', 0) * VAT) * pow_m2, 2),
            "karton": round((config.get('karton', 0) * VAT) * pow_m2, 2),
            "pp": round((config.get('pp', 0) * VAT) * pow_m2, 2)
        }
    }

@app.get("/api/pdf")
async def generate_pdf(kod: str, s: float, w: float, suma: float, opis: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(w=0, h=10, text="WYCENA OPRAWY - ANTYRAMY.EU", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(w=0, h=10, text=f"Kod listwy: {kod}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(w=0, h=10, text=f"Wymiary: {int(s)} x {int(w)} cm", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.multi_cell(w=0, h=10, text=f"Elementy: {opis.replace('|', ', ')}")
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(w=0, h=10, text=f"SUMA: {suma:.2f} PLN")
    
    return Response(
        content=bytes(pdf.output()), 
        media_type="application/pdf", 
        headers={"Content-Disposition": f"attachment; filename=wycena_{kod}.pdf"}
    )