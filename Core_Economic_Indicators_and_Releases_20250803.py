import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import base64
from io import BytesIO
import pandas_datareader.data as web
import datetime
from dateutil.relativedelta import relativedelta
import requests
import io
from bs4 import BeautifulSoup
import re
from dateutil.parser import parse
import dash_bootstrap_components as dbc
import dash_table

# Fetch functions (unchanged)
def fetch_fred_data(code, label, lookback=120, is_mom=False, is_yoy=False):
    try:
        extra = 12 if is_yoy else 1 if is_mom else 0
        start = datetime.datetime.now() - relativedelta(months=lookback + extra)
        data = web.DataReader(code, 'fred', start, datetime.datetime.now())
        data = data.reset_index()
        data.columns = ['Date', 'Value']
        if is_yoy:
            data[label] = data['Value'].pct_change(periods=12) * 100
        elif is_mom:
            data[label] = data['Value'].pct_change() * 100
        else:
            data[label] = data['Value']
        data = data.dropna()[['Date', label]]
        start_date = datetime.datetime.now() - relativedelta(months=lookback)
        data = data[data['Date'] >= start_date]
        return data
    except Exception as e:
        print(f'Fetch failed for {label}: {e}')
        return pd.DataFrame()

def fetch_bls_csv(series_id, label, lookback=120):
    url = 'https://download.bls.gov/pub/time.series/ce/ce.data.0.Current'
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text), delimiter='\t', on_bad_lines='skip')
        df = df.apply(lambda col: col.str.strip() if col.dtype == 'object' else col)
        df = df[df['series_id'] == series_id]
        if df.empty:
            return pd.DataFrame()
        df['month'] = df['period'].str.replace('M', '').astype(int)
        df['Date'] = pd.to_datetime(df['year'].astype(str) + '-' + df['month'].astype(str) + '-01')
        df = df.sort_values('Date').tail(lookback)
        df = df[['Date', 'value']]
        df.columns = ['Date', label]
        return df
    except Exception as e:
        print(f'Fetch failed for {label}: {e}')
        return pd.DataFrame()

def fetch_ism_pmi(lookback=6):
    url = 'https://www.investing.com/economic-calendar/ism-manufacturing-pmi-173'
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        table = None
        for t in soup.find_all('table'):
            if 'Actual' in t.text:
                table = t
                break
        if table:
            rows = table.find_all('tr')[1:]
            data = []
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 5:
                    date_text = cols[0].text.strip()
                    value = cols[2].text.strip()
                    if value and value != '-':
                        date_text = re.sub(r'\s+', ' ', date_text)
                        match = re.search(r'\w{3} \d{2}, (\d{4}) \((\w{3})\)', date_text)
                        if match:
                            year, month = match.groups()
                            full_date = f"{month} 1, {year}"
                            data.append({'Date': pd.to_datetime(full_date), 'ISM Manufacturing PMI': value})
            if data:
                df = pd.DataFrame(data)
                df['ISM Manufacturing PMI'] = pd.to_numeric(df['ISM Manufacturing PMI'], errors='coerce')
                df = df.dropna().sort_values('Date').tail(lookback)
                return df
        return pd.DataFrame()
    except Exception as e:
        print(f'Fetch failed for ISM Manufacturing PMI: {e}')
        return pd.DataFrame()

def fetch_fomc_rates(lookback=120):
    url = 'https://en.wikipedia.org/wiki/History_of_Federal_Open_Market_Committee_actions'
    try:
        dfs = pd.read_html(url)
        if not dfs:
            raise ValueError("No tables found on page")
        table = None
        for df in dfs:
            if 'Date' in df.columns and 'Fed. Funds Rate' in df.columns:
                table = df
                break
        if table is None:
            raise ValueError("Expected columns not found in any table")
        data = table[['Date', 'Fed. Funds Rate']]
        data = data.rename(columns={'Fed. Funds Rate': 'Rate Range %'})
        data['Rate Range %'] = data['Rate Range %'].str.replace('%', '', regex=False).str.replace('–', '-', regex=False).str.strip()
        data = data.dropna(subset=['Date', 'Rate Range %'])
        data['Date'] = pd.to_datetime(data['Date'], errors='coerce')
        data = data.dropna(subset=['Date'])
        data = data.sort_values('Date')
        start_date = pd.Timestamp.now() - relativedelta(months=lookback)
        data = data[data['Date'] >= start_date]
        return data
    except Exception as e:
        print(f'Fetch failed for FOMC Decisions: {e}')
        return pd.DataFrame()

def fetch_retail_sales(label, lookback=120):
    url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=RSAFS'
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        df['Date'] = pd.to_datetime(df['observation_date'], errors='coerce')
        df['Sales'] = pd.to_numeric(df['RSAFS'], errors='coerce')
        df = df.dropna(subset=['Date', 'Sales'])
        start_date = pd.Timestamp.now() - relativedelta(months=lookback + 1)
        df = df[df['Date'] >= start_date].sort_values('Date')
        df[label] = df['Sales'].pct_change() * 100
        df = df.dropna()[['Date', label]]
        return df
    except Exception as e:
        print(f'Fetch failed for {label}: {e}')
        return pd.DataFrame()

def fetch_housing_starts(label, lookback=120):
    url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=HOUST'
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        df['Date'] = pd.to_datetime(df['observation_date'], errors='coerce')
        df['Value'] = pd.to_numeric(df['HOUST'], errors='coerce') / 1000
        df = df.dropna(subset=['Date', 'Value'])
        start_date = pd.Timestamp.now() - relativedelta(months=lookback)
        df = df[df['Date'] >= start_date].sort_values('Date').tail(lookback)
        df[label] = df['Value']
        return df[['Date', label]]
    except Exception as e:
        print(f'Fetch failed for {label}: {e}')
        return pd.DataFrame()

def fetch_durable_goods(label, lookback=120):
    url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGORDER'
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        df['Date'] = pd.to_datetime(df['observation_date'], errors='coerce')
        df['Sales'] = pd.to_numeric(df['DGORDER'], errors='coerce')
        df = df.dropna(subset=['Date', 'Sales'])
        start_date = pd.Timestamp.now() - relativedelta(months=lookback + 1)
        df = df[df['Date'] >= start_date].sort_values('Date')
        df[label] = df['Sales'].pct_change() * 100
        df = df.dropna()[['Date', label]]
        return df
    except Exception as e:
        print(f'Fetch failed for {label}: {e}')
        return pd.DataFrame()

# Descriptions
descriptions = {
    'nfp': 'Nonfarm Payrolls (NFP): Measures monthly job gains/losses in US nonfarm sectors (excludes farms, self-employed). High adds indicate strong labor market and economic growth.',
    'cpi': 'CPI (YoY %): Tracks annual change in prices for urban consumers\' goods/services. High values signal inflation; Fed may raise rates to cool.',
    'gdp': 'GDP (QoQ Annualized %): Quarterly annualized growth in US output of goods/services. Positive rates show expansion; negative indicate recession.',
    'fomc': 'FOMC Decisions: Sets federal funds rate range, influencing borrowing. Hikes fight inflation; cuts boost growth.',
    'unemp': 'Unemployment Rate (%): Share of labor force jobless but seeking work. Low rates (e.g., <5%) suggest full employment; high rates signal weakness.',
    'pce': 'PCE (YoY %): Fed\'s preferred inflation measure of household spending prices. Rising YoY indicates eroding purchasing power.',
    'retail': 'Retail Sales (MoM %): Monthly change in retail spending. Increases reflect consumer confidence; key for GDP (70% from consumption).',
    'ppi': 'PPI (YoY %): Annual change in producers\' selling prices. Leads CPI; high values may pass costs to consumers, signaling inflation.',
    'ism': 'ISM Manufacturing PMI: Survey-based index of manufacturing health. >50 = expansion, <50 = contraction; leading economic indicator. Note: Limited to last 6 months due to data fetch effort; historical data available but not justified for now.',
    'conf': 'Consumer Confidence Index: Gauges optimism on economy/finances. High scores predict more spending; low suggest caution.',
    'housing': 'Housing Starts (Millions annualized): Annualized new home constructions started. High numbers show housing demand and economic confidence.',
    'trade': 'Trade Balance ($ Millions): Exports minus imports. Surplus positive; US often in deficit, impacting currency and growth.',
    'claims': 'Jobless Claims: Weekly new unemployment filings. Low/falling claims indicate healthy job market; spikes warn of slowdowns.',
    'durable': 'Durable Goods Orders (MoM %): Monthly change in orders for long-lasting goods. Rises signal business investment and expansion.',
    'prod': 'Productivity (QoQ Annualized %): Output per hour (nonfarm). Higher growth rates support growth without inflation; key for wages/profits.',
    'fomc_3d': '3D FOMC Upper Rates: Visualizes upper fed funds rate (y-axis) over meeting dates (x-axis) with depth (z-axis) representing time sequence (higher z = more recent). Color gradient from blue (older) to red (recent) highlights trend evolution. Rotate to see rate changes in 3D perspective for better trend analysis.'
}

# Metrics list in ranked order
metrics_list = [
    'Nonfarm Payrolls (NFP)',
    'Consumer Price Index (CPI)',
    'Gross Domestic Product (GDP)',
    'FOMC Decisions',
    'Unemployment Rate',
    'Personal Consumption Expenditures (PCE)',
    'Retail Sales',
    'Producer Price Index (PPI)',
    'ISM Manufacturing PMI',
    'Consumer Confidence Index',
    'Housing Starts',
    'Trade Balance',
    'Jobless Claims',
    'Durable Goods Orders',
    'Productivity'
]

# Release dates dict
release_dates = {
    'Nonfarm Payrolls (NFP)': ['2025-08-01', '2025-09-05', '2025-10-03', '2025-11-07', '2025-12-05', '2026-01-02', '2026-02-06', '2026-03-06', '2026-04-03', '2026-05-01', '2026-06-05', '2026-07-03', '2026-08-07', '2026-09-04', '2026-10-02', '2026-11-06', '2026-12-04'],
    'Consumer Price Index (CPI)': ['2025-08-12', '2025-09-11', '2025-10-15', '2025-11-13', '2025-12-10', '2026-01-12', '2026-02-12', '2026-03-12', '2026-04-13', '2026-05-12', '2026-06-12', '2026-07-13', '2026-08-12', '2026-09-14', '2026-10-12', '2026-11-12', '2026-12-14'],
    'Gross Domestic Product (GDP)': ['2025-08-28', '2025-09-25', '2025-10-30', '2025-11-26', '2025-12-19', '2026-01-30', '2026-02-27', '2026-03-27', '2026-04-30', '2026-05-29', '2026-06-26', '2026-07-30', '2026-08-28', '2026-09-25', '2026-10-30', '2026-11-25', '2026-12-18'],
    'FOMC Decisions': ['2025-09-17', '2025-10-29', '2025-12-10', '2026-01-31', '2026-03-19', '2026-05-07', '2026-06-18', '2026-09-17', '2026-10-29', '2026-12-10'],
    'Unemployment Rate': ['2025-08-01', '2025-09-05', '2025-10-03', '2025-11-07', '2025-12-05', '2026-01-02', '2026-02-06', '2026-03-06', '2026-04-03', '2026-05-01', '2026-06-05', '2026-07-03', '2026-08-07', '2026-09-04', '2026-10-02', '2026-11-06', '2026-12-04'],
    'Personal Consumption Expenditures (PCE)': ['2025-08-29', '2025-09-26', '2025-10-31', '2025-11-26', '2025-12-19', '2026-01-28', '2026-03-02', '2026-03-30', '2026-04-28', '2026-05-28', '2026-06-29', '2026-07-28', '2026-08-28', '2026-09-28', '2026-10-28', '2026-11-30', '2026-12-28'],
    'Retail Sales': ['2025-08-15', '2025-09-16', '2025-10-16', '2025-11-14', '2025-12-17', '2026-01-15', '2026-02-16', '2026-03-16', '2026-04-15', '2026-05-15', '2026-06-15', '2026-07-15', '2026-08-17', '2026-09-15', '2026-10-15', '2026-11-16', '2026-12-15'],
    'Producer Price Index (PPI)': ['2025-08-14', '2025-09-10', '2025-10-16', '2025-11-14', '2025-12-11', '2026-01-13', '2026-02-13', '2026-03-13', '2026-04-13', '2026-05-13', '2026-06-15', '2026-07-13', '2026-08-13', '2026-09-14', '2026-10-13', '2026-11-13', '2026-12-14'],
    'ISM Manufacturing PMI': ['2025-08-01', '2025-09-02', '2025-10-01', '2025-11-03', '2025-12-01', '2026-01-02', '2026-02-02', '2026-03-02', '2026-04-01', '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-03', '2026-09-01', '2026-10-01', '2026-11-02', '2026-12-01'],
    'Consumer Confidence Index': ['2025-08-26', '2025-09-30', '2025-10-28', '2025-11-25', '2025-12-30', '2026-01-27', '2026-02-24', '2026-03-31', '2026-04-28', '2026-05-26', '2026-06-30', '2026-07-28', '2026-08-25', '2026-09-29', '2026-10-27', '2026-11-24', '2026-12-29'],
    'Housing Starts': ['2025-08-19', '2025-09-17', '2025-10-17', '2025-11-19', '2025-12-16', '2026-01-19', '2026-02-18', '2026-03-18', '2026-04-20', '2026-05-18', '2026-06-18', '2026-07-20', '2026-08-18', '2026-09-18', '2026-10-19', '2026-11-18', '2026-12-18'],
    'Trade Balance': ['2025-08-05', '2025-09-04', '2025-10-07', '2025-11-04', '2025-12-04', '2026-01-05', '2026-02-05', '2026-03-05', '2026-04-06', '2026-05-05', '2026-06-05', '2026-07-06', '2026-08-05', '2026-09-07', '2026-10-05', '2026-11-05', '2026-12-07'],
    'Jobless Claims': ['2025-08-07', '2025-08-14', '2025-08-21', '2025-08-28', '2025-09-04', '2025-09-11', '2025-09-18', '2025-09-25', '2025-10-02', '2025-10-09', '2025-10-16', '2025-10-23', '2025-10-30', '2025-11-06', '2025-11-13', '2025-11-20', '2025-11-27', '2025-12-04', '2025-12-11', '2025-12-18', '2025-12-25', '2026-01-01', '2026-01-08', '2026-01-15', '2026-01-22', '2026-01-29', '2026-02-05', '2026-02-12', '2026-02-19', '2026-02-26', '2026-03-05', '2026-03-12', '2026-03-19', '2026-03-26', '2026-04-02', '2026-04-09', '2026-04-16', '2026-04-23', '2026-04-30', '2026-05-07', '2026-05-14', '2026-05-21', '2026-05-28', '2026-06-04', '2026-06-11', '2026-06-18', '2026-06-25', '2026-07-02', '2026-07-09', '2026-07-16', '2026-07-23', '2026-07-30', '2026-08-06', '2026-08-13', '2026-08-20', '2026-08-27', '2026-09-03', '2026-09-10', '2026-09-17', '2026-09-24', '2026-10-01', '2026-10-08', '2026-10-15', '2026-10-22', '2026-10-29', '2026-11-05', '2026-11-12', '2026-11-19', '2026-11-26', '2026-12-03', '2026-12-10', '2026-12-17', '2026-12-24', '2026-12-31'],
    'Durable Goods Orders': ['2025-08-26', '2025-09-25', '2025-10-27', '2025-11-26', '2025-12-24', '2026-01-26', '2026-02-25', '2026-03-25', '2026-04-27', '2026-05-25', '2026-06-25', '2026-07-27', '2026-08-25', '2026-09-25', '2026-10-26', '2026-11-25', '2026-12-25'],
    'Productivity': ['2025-08-07', '2025-09-04', '2025-11-06', '2025-12-09', '2026-02-06', '2026-03-06', '2026-05-07', '2026-06-05', '2026-08-06', '2026-09-04', '2026-11-05', '2026-12-09']
}

# Function to fetch data
def get_data(lookback=120):
    data_dict = {}
    data_dict['nfp'] = fetch_fred_data('PAYEMS', 'NFP (thousands added)', lookback=lookback)
    if not data_dict['nfp'].empty:
        data_dict['nfp']['NFP (thousands added)'] = data_dict['nfp']['NFP (thousands added)'].diff().dropna()
    data_dict['cpi'] = fetch_fred_data('CPIAUCSL', 'CPI (YoY %)', lookback=lookback, is_yoy=True)
    data_dict['gdp'] = fetch_fred_data('A191RL1Q225SBEA', 'GDP (QoQ Annualized %)', lookback=lookback)
    data_dict['fomc'] = fetch_fomc_rates(lookback=lookback)
    if not data_dict['fomc'].empty:
        def get_plot_value(rate):
            try:
                rate = rate.strip()
                if '-' in rate:
                    return float(rate.split('-')[1])
                return float(rate)
            except:
                return 0.0
        data_dict['fomc']['Upper Rate (%)'] = data_dict['fomc']['Rate Range %'].apply(get_plot_value)
    data_dict['unemp'] = fetch_fred_data('UNRATE', 'Unemployment Rate (%)', lookback=lookback)
    data_dict['pce'] = fetch_fred_data('PCEPI', 'PCE (YoY %)', lookback=lookback, is_yoy=True)
    data_dict['retail'] = fetch_retail_sales('Retail Sales (MoM %)', lookback=lookback)
    data_dict['ppi'] = fetch_fred_data('PPIACO', 'PPI (YoY %)', lookback=lookback, is_yoy=True)
    data_dict['ism'] = fetch_ism_pmi(lookback=6)
    data_dict['conf'] = fetch_fred_data('UMCSENT', 'Consumer Confidence Index', lookback=lookback)
    data_dict['housing'] = fetch_housing_starts('Housing Starts (Millions annualized)', lookback=lookback)
    data_dict['trade'] = fetch_fred_data('BOPGSTB', 'Trade Balance ($ Millions)', lookback=lookback)
    data_dict['claims'] = fetch_fred_data('ICSA', 'Jobless Claims', lookback=lookback)
    data_dict['durable'] = fetch_durable_goods('Durable Goods Orders (MoM %)', lookback=lookback)
    data_dict['prod'] = fetch_fred_data('PRS85006092', 'Productivity (QoQ Annualized %)', lookback=lookback)
    return {k: v.to_dict('records') for k, v in data_dict.items() if not v.empty}

# Initial serialized data
initial_serialized_data = get_data(120)

# Function to create compact figure
def create_figure(serialized_df, x, y, title, is_bar=False, is_3d=False, is_trade=False, theme='dark'):
    template = 'plotly_dark' if theme == 'dark' else 'plotly'
    df = pd.DataFrame(serialized_df)
    if df.empty:
        fig = px.line(title=title + ' (No Data)')
    elif is_3d:
        df = df.sort_values('Date')
        z = list(range(len(df)))
        fig = go.Figure(data=[go.Scatter3d(
            x=df[x], y=df[y], z=z,
            mode='lines+markers', marker=dict(color=z, colorscale='Viridis', size=5, colorbar=dict(title='Depth (0=oldest)'))
        )])
        fig.update_layout(title=title, scene=dict(xaxis_title='', yaxis_title=y, zaxis_title='Sequential Depth (0 = oldest, max = recent)'), template=template, height=500)
    else:
        if is_bar:
            fig = px.bar(df, x=x, y=y, title=title)
        else:
            fig = px.line(df, x=x, y=y, title=title, markers=True)
        fig.update_layout(template=template, height=300, margin={'l':20, 'r':20, 't':50, 'b':20})
        fig.update_xaxes(title_text='', tickformat='%b %Y', nticks=12, tickangle=0)
        if is_trade:
            ymin = min(df[y].min() * 1.1, 0)
            ymax = max(df[y].max() * 1.1, 0)
            fig.update_yaxes(range=[ymin, ymax])
    return fig

# Function to create release dates figure (updated with vertical line for today's date)
def create_release_figure(theme='dark'):
    template = 'plotly_dark' if theme == 'dark' else 'plotly'
    fig = go.Figure()
    colors = px.colors.sequential.RdBu  # Red to blue gradient
    for i, metric in enumerate(metrics_list):
        dates = release_dates.get(metric, [])
        y_val = 16 - (i + 1)
        normalize = (y_val - 1) / 15
        color_index = int(normalize * (len(colors) - 1))
        color = colors[color_index]
        fig.add_trace(go.Scatter(
            x=dates,
            y=[y_val] * len(dates),
            mode='markers',
            name=metric,
            marker=dict(color=color, size=10, symbol='circle')
        ))
    # Add vertical line for today's date (August 03, 2025)
    fig.add_shape(
        type="line",
        x0="2025-08-03", y0=0, x1="2025-08-03", y1=16,
        line=dict(color="Yellow", width=2, dash="dash"),
    )
    fig.add_annotation(
        x="2025-08-03", y=16,
        text="Today (Aug 03, 2025)",
        showarrow=True,
        arrowhead=1,
        yshift=10
    )
    fig.update_layout(
        title='Upcoming Economic Release Dates (Aug 2025 - Dec 2026)',
        xaxis=dict(title='Date', type='date'),
        yaxis=dict(
            title='Metrics (Ranked by Importance)',
            tickvals=list(range(1, 16)),
            ticktext=metrics_list[::-1],  # Reverse so top is important
            range=[0, 16]
        ),
        template=template,
        height=600,
        showlegend=True
    )
    return fig

# Function to create release DF for download
def create_release_df():
    all_dates = sorted(set(date for dates in release_dates.values() for date in dates))
    df = pd.DataFrame(index=pd.to_datetime(all_dates), columns=metrics_list)
    for i, metric in enumerate(metrics_list):
        y_val = 16 - (i + 1)
        for date in release_dates.get(metric, []):
            df.loc[pd.to_datetime(date), metric] = y_val
    return df

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)

app.layout = html.Div(id='main-div', children=[
    html.Div(id='fixed-header', style={'position': 'fixed', 'top': 0, 'width': '100%', 'backgroundColor': '#111', 'color': '#fff', 'zIndex': 1000, 'padding': '10px'}, children=[
        html.H1('Core Economic Indicators and Releases', style={'textAlign': 'center'}),
        dcc.Tabs(id='tabs', style={'marginTop': '10px'}, value='Employment', children=[
            dcc.Tab(label='Employment', value='Employment', style={'backgroundColor': '#222', 'color': '#fff'}),
            dcc.Tab(label='Inflation & Prices', value='Inflation & Prices', style={'backgroundColor': '#222', 'color': '#fff'}),
            dcc.Tab(label='Growth & Sales', value='Growth & Sales', style={'backgroundColor': '#222', 'color': '#fff'}),
            dcc.Tab(label='Other Indicators', value='Other Indicators', style={'backgroundColor': '#222', 'color': '#fff'}),
            dcc.Tab(label='Rates & 3D View', value='Rates & 3D View', style={'backgroundColor': '#222', 'color': '#fff'}),
            dcc.Tab(label='Release Calendar', value='Release Calendar', style={'backgroundColor': '#222', 'color': '#fff'})
        ]),
        html.Div(style={'position': 'absolute', 'top': '10px', 'right': '10px'}, children=[
            html.Button('Toggle Controls', id='toggle-controls', n_clicks=0, style={'marginBottom': '5px'}),
            dbc.Collapse(
                id='controls-collapse',
                is_open=False,
                children=[
                    html.Div(id='controls-div', style={'backgroundColor': '#222', 'padding': '10px', 'borderRadius': '5px'}, children=[
                        dbc.Switch(id='theme-toggle', label='Dark Mode', value=True, style={'margin': '5px'}),
                        html.Div(children=[
                            html.Button('3M', id='btn-3m', n_clicks=0, style={'margin': '5px'}),
                            html.Button('6M', id='btn-6m', n_clicks=0, style={'margin': '5px'}),
                            html.Button('1Y', id='btn-1y', n_clicks=0, style={'margin': '5px'}),
                            html.Button('5Y', id='btn-5y', n_clicks=0, style={'margin': '5px'}),
                            html.Button('10Y', id='btn-10y', n_clicks=0, style={'margin': '5px'}),
                        ]),
                        dcc.Input(id='lookback-input', type='number', placeholder='Custom months', style={'width': '100px', 'margin': '5px'}),
                        html.Button('Update', id='update-btn', n_clicks=0, style={'margin': '5px'}),
                        html.Button('Download Data', id='download-btn', n_clicks=0, style={'margin': '5px'}),
                        dcc.Download(id='download-data')
                    ])
                ]
            ),
            dcc.Store(id='data-store', data=initial_serialized_data),
            dcc.Store(id='current-lookback', data=120),
            dcc.Store(id='theme-store', data='dark')
        ])
    ]),
    html.Div(id='tab-content', style={'paddingTop': '150px', 'backgroundColor': '#111', 'color': '#fff'})
])

@app.callback(
    Output('controls-collapse', 'is_open'),
    Input('toggle-controls', 'n_clicks'),
    State('controls-collapse', 'is_open')
)
def toggle_collapse(n, is_open):
    if n:
        return not is_open
    return is_open

@app.callback(
    Output('theme-store', 'data'),
    Input('theme-toggle', 'value')
)
def update_theme(value):
    return 'dark' if value else 'light'

@app.callback(
    [Output('fixed-header', 'style'),
     Output('tab-content', 'style'),
     Output('controls-div', 'style'),
     Output('main-div', 'style')],
    Input('theme-store', 'data')
)
def update_styles(theme):
    if theme == 'dark':
        header_style = {'position': 'fixed', 'top': 0, 'width': '100%', 'backgroundColor': '#111', 'color': '#fff', 'zIndex': 1000, 'padding': '10px'}
        content_style = {'paddingTop': '150px', 'backgroundColor': '#111', 'color': '#fff'}
        controls_style = {'backgroundColor': '#222', 'padding': '10px', 'borderRadius': '5px'}
        main_style = {'backgroundColor': '#111', 'color': '#fff'}
    else:
        header_style = {'position': 'fixed', 'top': 0, 'width': '100%', 'backgroundColor': '#fff', 'color': '#000', 'zIndex': 1000, 'padding': '10px', 'borderBottom': '1px solid #ddd'}
        content_style = {'paddingTop': '150px', 'backgroundColor': '#fff', 'color': '#000'}
        controls_style = {'backgroundColor': '#f8f9fa', 'padding': '10px', 'borderRadius': '5px', 'border': '1px solid #ddd'}
        main_style = {'backgroundColor': '#fff', 'color': '#000'}
    return header_style, content_style, controls_style, main_style

@app.callback(
    Output('data-store', 'data'),
    Output('current-lookback', 'data'),
    [Input('update-btn', 'n_clicks'), Input('btn-3m', 'n_clicks'), Input('btn-6m', 'n_clicks'), Input('btn-1y', 'n_clicks'),
     Input('btn-5y', 'n_clicks'), Input('btn-10y', 'n_clicks')],
    State('lookback-input', 'value')
)
def update_data_store(update_n, btn3m, btn6m, btn1y, btn5y, btn10y, custom):
    ctx = dash.callback_context
    if not ctx.triggered:
        return initial_serialized_data, 120
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if button_id == 'btn-3m':
        lookback = 3
    elif button_id == 'btn-6m':
        lookback = 6
    elif button_id == 'btn-1y':
        lookback = 12
    elif button_id == 'btn-5y':
        lookback = 60
    elif button_id == 'btn-10y':
        lookback = 120
    else:
        lookback = custom or 120
    serialized_data = get_data(lookback)
    return serialized_data, lookback

@app.callback(
    Output('tab-content', 'children'),
    Input('tabs', 'value'),
    Input('data-store', 'data'),
    Input('theme-store', 'data')
)
def render_tab_content(tab, stored_data, theme):
    text_color = '#fff' if theme == 'dark' else '#000'
    if tab == 'Employment':
        return html.Div([
            html.Div([html.H6('Nonfarm Payrolls (thousands added)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['nfp'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('nfp', []), 'Date', 'NFP (thousands added)', '', is_bar=True, theme=theme))]),
            html.Div([html.H6('Unemployment Rate (%)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['unemp'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('unemp', []), 'Date', 'Unemployment Rate (%)', '', theme=theme))]),
            html.Div([html.H6('Jobless Claims', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['claims'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('claims', []), 'Date', 'Jobless Claims', '', theme=theme))])
        ], style={'padding': '20px 0px'})
    elif tab == 'Inflation & Prices':
        return html.Div([
            html.Div([html.H6('CPI (YoY %)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['cpi'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('cpi', []), 'Date', 'CPI (YoY %)', '', theme=theme))]),
            html.Div([html.H6('PCE (YoY %)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['pce'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('pce', []), 'Date', 'PCE (YoY %)', '', theme=theme))]),
            html.Div([html.H6('PPI (YoY %)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['ppi'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('ppi', []), 'Date', 'PPI (YoY %)', '', theme=theme))])
        ], style={'padding': '20px 0px'})
    elif tab == 'Growth & Sales':
        return html.Div([
            html.Div([html.H6('GDP (QoQ Annualized %)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['gdp'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('gdp', []), 'Date', 'GDP (QoQ Annualized %)', '', is_bar=True, theme=theme))]),
            html.Div([html.H6('Retail Sales (MoM %)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['retail'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('retail', []), 'Date', 'Retail Sales (MoM %)', '', theme=theme))]),
            html.Div([html.H6('Durable Goods Orders (MoM %)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['durable'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('durable', []), 'Date', 'Durable Goods Orders (MoM %)', '', theme=theme))]),
            html.Div([html.H6('Productivity (QoQ Annualized %)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['prod'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('prod', []), 'Date', 'Productivity (QoQ Annualized %)', '', theme=theme))])
        ], style={'padding': '20px 0px'})
    elif tab == 'Other Indicators':
        return html.Div([
            html.Div([html.H6('ISM Manufacturing PMI', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['ism'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('ism', []), 'Date', 'ISM Manufacturing PMI', '', theme=theme))]),
            html.Div([html.H6('Consumer Confidence Index', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['conf'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('conf', []), 'Date', 'Consumer Confidence Index', '', theme=theme))]),
            html.Div([html.H6('Housing Starts (Millions annualized)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['housing'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('housing', []), 'Date', 'Housing Starts (Millions annualized)', '', theme=theme))]),
            html.Div([html.H6('Trade Balance ($ Millions)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['trade'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('trade', []), 'Date', 'Trade Balance ($ Millions)', '', is_trade=True, theme=theme))])
        ], style={'padding': '20px 0px'})
    elif tab == 'Rates & 3D View':
        return html.Div([
            html.Div([html.H6('FOMC Rates (Upper Bound (%))', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['fomc'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(figure=create_figure(stored_data.get('fomc', []), 'Date', 'Upper Rate (%)', '', theme=theme))]),
            html.Div([html.H6('3D FOMC Upper Rates (%)', style={'color': text_color, 'marginBottom': '0px'}),
            html.P(descriptions['fomc_3d'], style={'fontSize': '12px', 'margin': '0px 0px 10px 0px'}),
            dcc.Graph(style={'height': '500px'}, figure=create_figure(stored_data.get('fomc', []), 'Date', 'Upper Rate (%)', '', is_3d=True, theme=theme))])
        ], style={'padding': '20px 0px'})
    elif tab == 'Release Calendar':
        # Define the table data based on verification
        table_data = [
            {'Series': 'Nonfarm Payrolls (NFP)', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Consumer Price Index (CPI)', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Gross Domestic Product (GDP)', 'Frequency': 'Quarterly', 'Notes': '3 revisions per quarter (advance, second, third estimate).'},
            {'Series': 'FOMC Decisions', 'Frequency': 'Irregular (~8/year)', 'Notes': 'Decision days only; no revisions.'},
            {'Series': 'Unemployment Rate', 'Frequency': 'Monthly', 'Notes': 'No revisions; released with NFP.'},
            {'Series': 'Personal Consumption Expenditures (PCE)', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Retail Sales', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Producer Price Index (PPI)', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'ISM Manufacturing PMI', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Consumer Confidence Index', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Housing Starts', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Trade Balance', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Jobless Claims', 'Frequency': 'Weekly', 'Notes': 'No revisions; released weekly.'},
            {'Series': 'Durable Goods Orders', 'Frequency': 'Monthly', 'Notes': 'No revisions; released once per month.'},
            {'Series': 'Productivity', 'Frequency': 'Quarterly', 'Notes': '2 main releases per quarter (preliminary and revised).'}
        ]
        return html.Div([
            dcc.Graph(figure=create_release_figure(theme=theme)),
            html.H6('Release Series Details', style={'color': text_color, 'marginTop': '20px'}),
            dash_table.DataTable(
                data=table_data,
                columns=[{'name': 'Series', 'id': 'Series'},
                         {'name': 'Frequency', 'id': 'Frequency'},
                         {'name': 'Notes', 'id': 'Notes'}],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'minWidth': '100px', 'whiteSpace': 'normal'},
                style_header={'backgroundColor': '#222' if theme == 'dark' else '#f8f9fa', 'fontWeight': 'bold'},
                style_data={'backgroundColor': '#111' if theme == 'dark' else '#fff', 'color': '#fff' if theme == 'dark' else '#000'}
            )
        ], style={'padding': '20px 0px'})
    return html.Div('Select a tab')

@app.callback(
    Output('download-data', 'data'),
    Input('download-btn', 'n_clicks'),
    State('data-store', 'data'),
    prevent_initial_call=True
)
def download_data_func(n_clicks, stored_data):
    data = {k: pd.DataFrame(v) for k, v in stored_data.items()}
    release_df = create_release_df()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for key, df in data.items():
            if not df.empty:
                df.to_excel(writer, sheet_name=key, index=False)
        release_df.to_excel(writer, sheet_name='Release_Dates', index=True)
    output.seek(0)
    return dcc.send_bytes(output.getvalue(), 'dashboard_data.xlsx')

if __name__ == '__main__':
    app.run(debug=True)