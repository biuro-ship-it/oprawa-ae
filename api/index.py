import os
import pandas as pd
import re
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- FUNKCJA ŁADOWANIA GLOBALNYCH CEN ---
def load_base_config():
    try:
        path = os.path.join(BASE_DIR, 'base_config.csv')
        df = pd.read_csv(path, sep=';', decimal=',', index_col='klucz')
        return df['wartosc'].to_dict()
    except Exception as e:
        print(f"Błąd base_config: {e}")
        return {}

# --- FUNKCJA ŁADOWANIA CENNIKA PRODUCENTA ---
def load_producer_list(prod_id):
    try:
        # Zakładamy folder 'cenniki'
        file_path = os.path.join(BASE_DIR, 'cenniki', f'producent_{prod_id}.csv')
        df = pd.read_csv(file_path, sep=';', decimal=',', header=None, dtype=str)
        df.columns = ['kod', 'ilosc', 'c_l', 'c_o', 'szer']
        return df
    except:
        return None

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
        return {"error": "Błąd ładowania danych konfiguracyjnych."}

    wybrana = df_prod[df_prod['kod'] == kod]
    if wybrana.empty: return {"error": "Brak kodu."}

    l = wybrana.iloc[0]
    sz_listwy = float(str(l['szer']).replace(',', '.'))
    c_l_netto = float(str(l['c_l']).replace(',', '.'))
    c_o_netto = float(str(l['c_o']).replace(',', '.'))

    obwod = ((2 * szer) + (2 * wys) + (8 * sz_listwy)) / 100
    pow_m2 = (szer * wys) / 10000
    VAT = 1.23

    # Obliczenia z użyciem BAZOWEJ KONFIGURACJI
    return {
        "kod": l['kod'],
        "results": {
            "listwa": round((c_l_netto * (1 + config.get('marza_listwa', 0.5))) * VAT * obwod, 2),
            "oprawa": round((c_o_netto * (1 + config.get('marza_oprawa', 0.3))) * VAT * obwod, 2),
            "float": round((config.get('float', 0) * VAT) * pow_m2, 2),
            "anty": round((config.get('anty', 0) * VAT) * pow_m2, 2),
            "hdf": round((config.get('hdf', 0) * VAT) * pow_m2, 2),
            "karton": round((config.get('karton', 0) * VAT) * pow_m2, 2),
            "pp": round((config.get('pp', 0) * VAT) * pow_m2, 2)
        }
    }