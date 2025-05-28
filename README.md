# Data_Stock
## 📈 About This Project

This repository contains a Python-based automation system for collecting, processing, and organizing financial data on US-listed stocks, particularly those included in the S&P 500 index (SPY).

### 📁 Repository Contents

1. **Ticker.csv**  
   A base file containing a list of ticker symbols used as input for data extraction.

2. **Actual_Stock.py**  
   A Python script that:
   - Reads the tickers from `Ticker.csv`.
   - Downloads the latest **Close Price** for each ticker.
   - Retrieves key financial indicators including:
     - Market Capitalization (`marketCap`)
     - Price-to-Earnings Ratios (`trailingPE`, `forwardPE`)
     - Volatility (`beta`)
     - Earnings per Share (`trailingEps`)
   - Saves this data into two separate files:
     - `Actual_Stock.csv` → latest closing prices.
     - `Stock_Info.csv` → financial fundamentals.

3. **Tickers Info.xlsx**  
   An Excel file created from the official Wikipedia table of S&P 500 components, including:
   - Ticker symbol
   - Company name
   - Sector

4. **Historical_Stock.csv**  
   Contains the **last 10 years of daily Close Price data** for all tickers in `Ticker.csv`, updated via a similar Python script.

---

### ⚙️ Automation with GitHub Actions

This project uses **GitHub Actions** to run the data update automatically every day at 16:00 UTC.  
The scheduled workflow performs the following steps:

- Checks out the repository
- Sets up the Python environment
- Installs necessary dependencies (`yfinance`, `pandas`)
- Executes the `Actual_Stock.py` script
- Commits and pushes the updated data to the repository
