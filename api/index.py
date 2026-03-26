import os
import pandas as pd
import re
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fpdf import FPDF

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- MODELE DANYCH ---
class ConfigUpdate(BaseModel):
    haslo: str
    float: float
    anty: float
    hdf: float
    karton: float
    pp: float
    marza_listwa: float
    marza_oprawa: float

# --- LOGIKA ŁADOWANIA DANYCH ---
def load_base_config():
    config = {
        'float': 45.0, 'anty': 65.0, 'hdf': 25.0, 'karton': 15.0, 'pp': 40.0,
        'marza_listwa': 0.5, 'marza_oprawa': 0.3
    }
    try:
        path = os.path.join(BASE_DIR, 'base_config.csv')
        if os.path.exists(path):
            df = pd.read_csv(path, sep=';', decimal=',', header=None)
            for _, row in df.iterrows():
                klucz = str(row[0]).strip().lower()
                wartosc = str(row[1]).replace(',', '.').strip()
                if klucz in config:
                    try: config[klucz] = float(wartosc)
                    except: pass
    except Exception as e:
        print(f"Błąd ładowania config: {e}")
    return config

def load_producer_list(prod_id):
    try:
        file_path = os.path.join(BASE_DIR, 'cenniki', f'producent_{prod_id}.csv')
        if not os.path.exists(file_path): return None
        df_raw = pd.read_csv(file_path, sep=';', decimal=',', header=None, dtype=str)
        df = df_raw.iloc[2:].copy()
        stopka_mask = df[0].astype(str).str.lower().str.contains('float|hdf|anty|pas|mar', na=False)
        if stopka_mask.any(): df = df.loc[:stopka_mask.idxmax()-1]
        df = df.iloc[:, :5]
        if len(df.columns) < 5:
            for i in range(len(df.columns), 5): df[i] = "0"
        df.columns = ['kod', 'ilosc', 'c_l', 'c_o', 'szer']
        df['kod'] = df['kod'].astype(str).str.strip()
        return df
    except:
        return None

# --- TRASY APLIKACJI KLIENTA ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/codes")
async def get_codes(prod_id: str):
    df = load_producer_list(prod_id)
    if df is not None:
        return {"codes": [k for k in df['kod'].unique().tolist() if k and str(k).lower() != 'nan']}
    return {"codes": []}

@app.get("/api/calculate")
async def calculate(prod_id: str, kod: str, szer: float, wys: float):
    try:
        df_prod = load_producer_list(prod_id)
        config = load_base_config()
        if df_prod is None: return {"error": f"Brak cennika."}
        wybrana = df_prod[df_prod['kod'] == kod]
        if wybrana.empty: return {"error": f"Brak kodu."}
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
                "listwa": round((c_l * (1 + config['marza_listwa'])) * VAT * obwod, 2),
                "oprawa": round((c_o * (1 + config['marza_oprawa'])) * VAT * obwod, 2),
                "float": round((config['float'] * VAT) * pow_m2, 2),
                "anty": round((config['anty'] * VAT) * pow_m2, 2),
                "hdf": round((config['hdf'] * VAT) * pow_m2, 2),
                "karton": round((config['karton'] * VAT) * pow_m2, 2),
                "pp": round((config['pp'] * VAT) * pow_m2, 2)
            }
        }
    except Exception as e:
        return {"error": str(e)}

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
    pdf.multi_cell(w=0, h=10, text=f"Elementy:\n{opis.replace('|', ', ')}")
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(w=0, h=10, text=f"SUMA: {suma:.2f} PLN")
    return Response(content=bytes(pdf.output()), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=wycena_{kod}.pdf"})


# --- TRASY ADMINA ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")

@app.get("/api/admin/config")
async def get_admin_config():
    return load_base_config()

@app.post("/api/admin/config")
async def save_admin_config(data: ConfigUpdate):
    # Proste zabezpieczenie hasłem (do zmiany na produkcję)
    if data.haslo != "shipit2026":
        return {"error": "Błędne hasło administratora!"}
    
    try:
        path = os.path.join(BASE_DIR, 'base_config.csv')
        # Zapis do pliku CSV (Działa na stałe lokalnie, na Vercel tylko do restartu serwera)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"float;{data.float};Cena za m2 szkła float\n")
            f.write(f"anty;{data.anty};Cena za m2 antyrefleksu\n")
            f.write(f"hdf;{data.hdf};Cena za m2 płyty HDF\n")
            f.write(f"karton;{data.karton};Cena za m2 tyłu karton\n")
            f.write(f"pp;{data.pp};Cena za m2 Passe-partout\n")
            f.write(f"marza_listwa;{data.marza_listwa};Marża na sama listwe\n")
            f.write(f"marza_oprawa;{data.marza_oprawa};Marża na listwe w ramie\n")
        return {"success": True, "message": "Zapisano zmiany pomyślnie!"}
    except Exception as e:
        return {"error": f"Błąd zapisu: {str(e)}"}