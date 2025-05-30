# yfinance_script_Python_Historical_Stock

!pip install yfinance
!pip install pandas
!pip install datetime
# Importar módulos
import yfinance as yf
import pandas as pd
from datetime import datetime
import os

# 🟢 1. Montar Google Drive
from google.colab import drive
drive.mount('/content/drive')

# 🟢 2. Definir la ruta al archivo CSV
FILE_NAME = '/content/drive/MyDrive/AQUI CONTINUA EL RESTO DE LA RUTA'

# 🟢 3. Lista de activos financieros
tickers_df = pd.read_csv("/content/drive/MyDrive/AQUI CONTINUA EL RESTO DE LA RUTA")
tickers = tickers_df["ticker"].dropna().tolist()

# 🟢 4. Obtener la fecha actual
hoy = datetime.today().strftime('%Y-%m-%d')

# 🟢 5. Descargar los datos de cierre de hoy
df = yf.download(tickers, start="2015-01-02", end=hoy,interval="1d", auto_adjust=True)['Close']

# Verificamos si hay datos (puede estar vacío en fines de semana o feriados)
if df.empty:
    print("⚠️ No hay datos disponibles para hoy.")
else:
    df = df[tickers]  # Asegurar el orden de las columnas

    # Verificar si ya existe el archivo
    if os.path.exists(FILE_NAME):
        df_existente = pd.read_csv(FILE_NAME, index_col=0)

        # Si la fecha de hoy ya está, no agregamos
        if hoy not in df_existente.index:
            df_final = pd.concat([df_existente, df])
            df_final.to_csv(FILE_NAME)
            print("✅ Se agregó la fila de hoy al archivo.")
        else:
            print("⚠️ Ya existe una fila para hoy. No se duplicó.")
    else:
        # Si es la primera vez, se crea el archivo
        df.to_csv(FILE_NAME)
        print("✅ Archivo creado y datos de hoy guardados.")
