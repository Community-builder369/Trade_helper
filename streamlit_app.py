import streamlit as st
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='Nifty 50 MACD Prediction',
    page_icon=':chart_with_upwards_trend:',
)

# -----------------------------------------------------------------------------
# Declare some useful functions.

@st.cache_data
def get_nifty_data():
    """Fetch Nifty 50 data from Yahoo Finance."""
    ticker = "^NSEI"  # Nifty 50 Index
    end_date = datetime.today()
    start_date = end_date - timedelta(days=365)
    df = yf.download(ticker, start=start_date, end=end_date)
    return df

@st.cache_data
def calculate_macd(df):
    """Calculate MACD for the given DataFrame."""
    df['MACD'], df['Signal'], df['Hist'] = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    return df

nifty_df = get_nifty_data()
nifty_df = calculate_macd(nifty_df)

# -----------------------------------------------------------------------------
# Draw the actual page

# Set the title that appears at the top of the page.
st.title(':chart_with_upwards_trend: Nifty 50 MACD Prediction')

# Add some spacing
st.write("### Nifty 50 Historical Data")
st.line_chart(nifty_df[['Close', 'MACD', 'Signal']])

# Predicting the direction based on the latest MACD
latest_data = nifty_df.iloc[-1]

if latest_data['MACD'] > latest_data['Signal']:
    prediction = "The Nifty 50 is likely to go **up** based on MACD."
else:
    prediction = "The Nifty 50 is likely to go **down** based on MACD."

st.write("### Prediction")
st.write(prediction)

# Display the MACD and Signal values
st.write(f"**Latest MACD Value:** {latest_data['MACD']:.2f}")
st.write(f"**Latest Signal Line Value:** {latest_data['Signal']:.2f}")

