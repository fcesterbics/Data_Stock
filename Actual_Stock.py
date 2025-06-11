# 📚 Importar librerías necesarias
import pandas as pd               # Para manipulación de datos
import yfinance as yf             # Para obtener datos financieros desde Yahoo Finance
from datetime import datetime     # Para manejar fechas
import os                         # Para operaciones con archivos

# 🟢 1. Leer lista de tickers desde archivo CSV
tickers_df = pd.read_csv("Tickers.csv")                         # Leer archivo con columna 'ticker'
tickers = tickers_df["ticker"].dropna().tolist()                # Crear lista sin valores nulos
tickers_dict = {str(ticker): True for ticker in tickers}        # Crear diccionario con tickers como claves

# 🟢 2. Descargar datos de precios de cierre de los últimos 5 días
# Se obtiene un DataFrame con las fechas como índice y los tickers como columnas
df = yf.download(tickers, period="5d", interval="1d", auto_adjust=True)['Close']

# 🟢 3. Filtrar solo el último día disponible (última fila)
df = df.tail(1)

# 🟢 4. Inicializar diccionario para guardar estadísticas financieras
dow_stats = {}

# 🟢 5. Recorrer cada ticker y obtener información financiera
for ticker_look in tickers_dict:
    ticker_yf = yf.Ticker(ticker_look)       # Crear objeto de ticker
    temp = ticker_yf.info                    # Obtener todos los datos disponibles

    # Lista de atributos financieros de interés
    attributes_of_interest = [
        "marketCap", "trailingPE", "forwardPE", "beta", "trailingEps",
        "industry", "sector", "fullTimeEmployees", "country", "ebitda",
        "totalDebt", "totalRevenue", "grossProfits", "freeCashflow",
        "shortName", "trailingPegRatio"
    ]

    # Crear diccionario filtrado con solo los atributos deseados
    filtered_data = {attr: temp.get(attr) for attr in attributes_of_interest}

    # Convertir a DataFrame con una sola fila
    ticker_info = pd.DataFrame([filtered_data])

    # Agregar al diccionario general con el ticker como clave
    dow_stats[ticker_look] = ticker_info

# 🟢 6. Unir todos los DataFrames de cada ticker en uno solo
# Se crea una jerarquía de índices: ticker > fila
all_stats_info = pd.concat(dow_stats, keys=dow_stats.keys(), names=['ticker', 'Index'])

# 🟢 7. Guardar la información financiera general
file_info_name = "Stock_Info.csv"
all_stats_info.to_csv(file_info_name)

# 🟢 8. Guardar los precios de cierre en otro archivo
file_name = "Actual_Stock.csv"

if not os.path.exists(file_name) or os.stat(file_name).st_size == 0:
    # Si el archivo no existe o está vacío, se guarda df completo
    df.to_csv(file_name, index=True)  # El índice de fechas se guarda como columna "Date"
    print("📊 Archivo creado con datos iniciales.")
else:
    # Si el archivo ya existe, verificar si ya se guardó la fecha
    df_existente = pd.read_csv(file_name, index_col="Date")
    df_existente.index = pd.to_datetime(df_existente.index)

    fecha_nueva = df.index[0]  # Fecha del nuevo dato

    if fecha_nueva not in df_existente.index:
        # Si la fecha nueva no está en el archivo, agregarla
        df_final = pd.concat([df_existente, df])
        df_final.to_csv(file_name)
        print("📈 Datos actualizados.")
    else:
        # Si ya existe la fila, no se hace nada
        pass
