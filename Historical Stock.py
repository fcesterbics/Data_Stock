# 📚 Importar librerías necesarias
import pandas as pd
import yfinance as yf
from datetime import datetime
import os

# 🟢 1. Leer lista de tickers desde CSV local
tickers_df = pd.read_csv("Tickers.csv")
tickers = tickers_df["ticker"].dropna().tolist()

# 🟢 2. Definir archivo histórico
FILE_NAME = "Historical_Stock.csv"

# 🟢 3. Definir rango de fechas
start_date = "2015-01-02"
end_date = datetime.today().strftime('%Y-%m-%d')

# 🟢 4. Descargar precios históricos
df = yf.download(
    tickers,
    start=start_date,
    end=end_date,
    interval="1d",
    auto_adjust=True
)['Close']

# ⚠️ Validar datos
if df.empty:
    print("⚠️ No se descargaron datos.")
else:
    # Asegurar orden de columnas
    df = df[tickers]

    # 🟢 5. Guardar / actualizar CSV histórico
    if not os.path.exists(FILE_NAME):
        # Si no existe → crear archivo completo
        df.to_csv(FILE_NAME, index=True)
        print("📁 Archivo histórico creado.")
    else:
        # Leer histórico existente
        df_existente = pd.read_csv(FILE_NAME, index_col=0)
        df_existente.index = pd.to_datetime(df_existente.index)
        df.index = pd.to_datetime(df.index)

        # Filtrar solo fechas nuevas
        fechas_nuevas = df.index.difference(df_existente.index)
        df_nuevo = df.loc[fechas_nuevas]

        if not df_nuevo.empty:
            df_final = pd.concat([df_existente, df_nuevo])
            df_final.to_csv(FILE_NAME)
            print(f"📈 Se agregaron {len(df_nuevo)} nuevas filas.")
        else:
            print("⚠️ No hay nuevas fechas para agregar.")
