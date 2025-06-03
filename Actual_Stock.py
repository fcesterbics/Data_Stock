import pandas as pd
import yfinance as yf
from datetime import datetime
import os

# Leer tickers desde CSV
tickers_df = pd.read_csv("Tickers.csv")
tickers = tickers_df["ticker"].dropna().tolist()
tickers_dict = {str(ticker): True for ticker in tickers_df["ticker"].dropna()}

# Descargar datos últimos 5 días
df = yf.download(tickers, period="5d", interval="1d", auto_adjust=True)['Close']

# Tomar solo la última fila disponible (último cierre)
df = df.tail(1)
dow_stats = {}

for ticker_look in tickers_dict:
    ticker_yf = yf.Ticker(ticker_look)
    temp = ticker_yf.info
    
    # Lista de atributos que te interesan
    attributes_of_interest = [
        "marketCap", "trailingPE", 
        "forwardPE", "beta", "trailingEps","industry",
        "sector","fullTimeEmployees","country","ebitda","totalDebt",
        "totalRevenue","grossProfits","freeCashflow","shortName","trailingPegRatio"
    ]
    
    # Crear un diccionario con solo los atributos deseados
    filtered_data = {attr: temp.get(attr) for attr in attributes_of_interest}
    
    ticker_info = pd.DataFrame([filtered_data]) # Crear un DataFrame directamente
    dow_stats[ticker_look] = ticker_info

all_stats_info = pd.concat(dow_stats, keys=dow_stats.keys(), names=['ticker', 'Index'])

# Archivo destino
file_info_name = "Stock_Info.csv"
file_name = "Actual_Stock.csv"
all_stats_info.to_csv(file_info_name)

if not os.path.exists(file_name) or os.stat(file_name).st_size == 0:
    # Si el archivo no existe o está vacío, guarda df directamente (con índice de fechas)
    df.to_csv(file_name, index=True)  # El índice de df (fechas) se guardará como la primera columna "Date"
    print("📊 Archivo creado con datos iniciales.")
else:  # Si el archivo existe y NO está vacío
    df_existente = pd.read_csv(file_name, index_col="Date")
    df_existente.index = pd.to_datetime(df_existente.index)  # Convertir a DateTimeIndex

    fecha_nueva = df.index[0]  # Fecha del nuevo dato
    if fecha_nueva not in df_existente.index:
        df_final = pd.concat([df_existente, df])
        df_final.to_csv(file_name)
        print("📈 Datos actualizados.")
    else:
        pass
