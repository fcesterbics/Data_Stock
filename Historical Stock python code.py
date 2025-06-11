# 📦 Instalar dependencias necesarias (solo en Colab)
!pip install yfinance
!pip install pandas
!pip install datetime  # No es estrictamente necesario, 'datetime' es parte de la librería estándar de Python

# 📚 Importar módulos requeridos
import yfinance as yf              # Para descargar datos financieros históricos
import pandas as pd               # Para manipulación de datos
from datetime import datetime     # Para manejar fechas
import os                         # Para verificar si existe el archivo CSV

# 🟢 1. Montar Google Drive para guardar y leer archivos desde allí
from google.colab import drive
drive.mount('/content/drive')

# 🟢 2. Definir la ruta donde se guardará o actualizará el archivo CSV de resultados
FILE_NAME = '/content/drive/MyDrive/AQUI CONTINUA EL RESTO DE LA RUTA'  # ← Cambiar por tu ruta real

# 🟢 3. Leer lista de activos financieros desde un CSV en Drive
# El archivo debe tener una columna llamada 'ticker'
tickers_df = pd.read_csv("/content/drive/MyDrive/AQUI CONTINUA EL RESTO DE LA RUTA")  # ← Ruta del archivo con tickers
tickers = tickers_df["ticker"].dropna().tolist()  # Convertimos la columna en lista, sin valores nulos

# 🟢 4. Obtener la fecha actual en formato 'YYYY-MM-DD'
hoy = datetime.today().strftime('%Y-%m-%d')

# 🟢 5. Descargar precios de cierre diario desde Yahoo Finance
# Desde 2015 hasta la fecha de hoy, con ajuste automático de precios (por dividendos, splits, etc.)
df = yf.download(tickers, start="2015-01-02", end=hoy, interval="1d", auto_adjust=True)['Close']

# ⚠️ Verificar si se obtuvieron datos (puede fallar en fines de semana o feriados)
if df.empty:
    print("⚠️ No hay datos disponibles para hoy.")
else:
    # Reordenar columnas para que coincidan con el orden de los tickers
    df = df[tickers]  

    # 🗃️ Verificamos si ya existe el archivo CSV
    if os.path.exists(FILE_NAME):
        # Leer archivo existente
        df_existente = pd.read_csv(FILE_NAME, index_col=0)

        # Si la fecha de hoy aún no está guardada, se agrega
        if hoy not in df_existente.index:
            df_final = pd.concat([df_existente, df])
            df_final.to_csv(FILE_NAME)
            print("✅ Se agregó la fila de hoy al archivo.")
        else:
            print("⚠️ Ya existe una fila para hoy. No se duplicó.")
    else:
        # Si el archivo no existe, se crea con los datos de hoy
        df.to_csv(FILE_NAME)
        print("✅ Archivo creado y datos de hoy guardados.")
