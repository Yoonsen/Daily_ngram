# -*- coding: utf-8 -*-

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output, State
import pandas as pd
from PIL import Image, ImageEnhance
import json
import datetime
import plotly.graph_objs as go
from io import BytesIO, StringIO
import base64
import dhlab.api.dhlab_api as api
from urllib.parse import urlencode

# Constants
max_days = 7400
min_days = 3

# Utility functions (unchanged)
def make_nb_query(name, start_date, end_date):
    return "https://www.nb.no/search?mediatype=aviser&" + urlencode({
        'q': f"{name}",
        'fromDate': f"{start_date.strftime('%Y%m%d')}",
        'toDate': f"{end_date.strftime('%Y%m%d')}"
    })

def to_excel(df):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    df.to_excel(writer, index=True, sheet_name='Sheet1')
    writer.close()
    processed_data = output.getvalue()
    return processed_data

def titles():
    try:
        b = pd.read_csv('titles.csv')
        return list(b['title'])
    except FileNotFoundError:
        return ["No titles available"]

def sumword(words, period, title=None):
    wordlist = [x.strip() for x in words.split(',')]
    if '' in wordlist:
        wordlist = [','] + [y for y in wordlist if y != '']
    try:
        ref = api.ngram_news(wordlist, period=period, title=title).sum(axis=1)
        ref = pd.Series(ref, name='tot')
        ref.index = ref.index.map(pd.Timestamp)
    except AttributeError:
        ref = pd.DataFrame()
    return ref

def ngram(word, mid_date, sammenlign, title=None):
    period = (
        (mid_date - datetime.timedelta(days=max_days)).strftime("%Y%m%d"),
        (mid_date + datetime.timedelta(days=max_days)).strftime("%Y%m%d")
    )
    try:
        res = api.ngram_news(word, period=period, title=title).fillna(0).sort_index()
        res.index = res.index.map(pd.Timestamp)
        if sammenlign != "":
            tot = sumword(sammenlign, period=period, title=title)
            for x in res:
                res[x] = res[x] / tot
    except AttributeError:
        res = pd.DataFrame()
    return res

def adjust(df, date, days, smooth):
    res = df.copy()
    try:
        ts = pd.Timestamp(date)
        td = pd.Timedelta(days=days - 1)
        s = pd.Timestamp(min(pd.Timestamp("20210701"), ts - pd.Timedelta(days=days + min_days)))
        e = pd.Timestamp(min(pd.Timestamp.today(), ts + td))
        mask = (df.index >= s) & (df.index <= e)
        res = res.loc[mask]
        res.loc[res.index.dayofweek == 6] = pd.NA
        res = res.rolling(window=smooth, min_periods=1).mean()
    except AttributeError:
        res = pd.DataFrame()
    return res.fillna(0).apply(lambda x: x.astype(int))

# Initialize Dash app
app = dash.Dash(__name__, title="Dagsplott", external_stylesheets=[dbc.themes.FLATLY])

# Generate year options for quick selection
year_options = [{'label': str(year), 'value': year} for year in range(1763, datetime.date.today().year + 1)]

# Layout
app.layout = html.Div([
    dbc.Row([
        dbc.Col([
            dbc.Button(
                "☰", 
                id="toggle_sidebar", 
                n_clicks=0, 
                color="link", 
                style={
                    'fontSize': '24px', 
                    'padding': '0', 
                    'backgroundColor': 'transparent', 
                    'border': 'none',
                    'position': 'relative',
                    'zIndex': '1001'
                }
            ),
            html.Div("Menu", style={'fontSize': '12px', 'textAlign': 'center', 'marginTop': '5px'})
        ], width=1),
        dbc.Col([
            dcc.Input(
                id='words', 
                type='text', 
                value='frihet', 
                placeholder='Søk ord (f.eks. frihet, likhet)', 
                debounce=True, 
                className="form-control mb-3 mt-3"
            ),
        ], width=3),
        dbc.Col([
            dcc.Dropdown(
                id='avisnavn', 
                options=[{'label': t, 'value': t} for t in titles()], 
                value=None, 
                placeholder="Select publication",
                className="form-control mb-3 mt-3"
            ),
        ], width=3),
        dbc.Col([
            html.Div([
                dcc.Dropdown(
                    id='year_picker',
                    options=year_options,
                    value=2020,  # Default year
                    placeholder="Select year",
                    className="form-control mb-2",
                    style={'width': '100px', 'display': 'inline-block'}
                ),
                dcc.DatePickerSingle(
                    id='mid_date',
                    date=datetime.datetime.strptime("20200701", '%Y%m%d') - datetime.timedelta(days=int(max_days/2)),
                    min_date_allowed=datetime.date(1763, 5, 1),
                    max_date_allowed=datetime.date.today(),
                    display_format="YYYY-MM-DD",
                    className="mb-3 mt-2",
                    style={'display': 'inline-block', 'marginLeft': '10px'}
                ),
            ])
        ], width=3),
        dbc.Col([
            dcc.Dropdown(
                id='plot_type',
                options=[
                    {'label': 'Line', 'value': 'lines'},
                    {'label': 'Scatter', 'value': 'markers'},
                    {'label': 'Line + Markers', 'value': 'lines+markers'}
                ],
                value='lines',
                placeholder="Select plot type",
                className="form-control mb-3 mt-3"
            ),
        ], width=2)
    ], className="mb-4", style={'position': 'relative', 'zIndex': '1000'}),
    
    html.Div([
        dcc.Graph(id='ngram_chart', style={'height': '70vh'})
    ], style={
        'maxHeight': '70vh', 
        'overflowY': 'auto', 
        'margin': '20px 0'
    }),
    
    html.Div(id='content_summary', className="text-muted small mb-4 mt-2", style={'marginLeft': '20px', 'marginRight': '20px'}),
    
    dbc.Collapse(
        dbc.Card([
            dbc.CardBody([
                html.H4("Settings", className="card-title"),
                dbc.Label("Period (days)"),
                dcc.Input(
                    id='period_size', 
                    type='number', 
                    value=3000, 
                    min=min_days, 
                    max=max_days, 
                    step=100, 
                    className="form-control mb-3"
                ),
                dbc.Label("Smoothing"),
                dcc.Slider(
                    id='smooth_slider', 
                    min=1, 
                    max=21, 
                    step=1, 
                    value=7, 
                    marks={1: '1', 21: '21'}, 
                    className="mb-3"
                ),
                dbc.Label("Color Theme"),
                dcc.Dropdown(
                    id='theme', 
                    options=[{'label': t, 'value': t} for t in ['plotly', 'plotly_white', 'plotly_dark']], 
                    value='plotly', 
                    className="form-control mb-3"
                ),
                dbc.Label("Opacity"),
                dcc.Input(
                    id='alpha', 
                    type='number', 
                    value=0.8, 
                    min=0.1, 
                    max=1.0, 
                    step=0.1, 
                    className="form-control mb-3"
                ),
                dbc.Label("Line Width"),
                dcc.Input(
                    id='width', 
                    type='number', 
                    value=2.5, 
                    min=0.5, 
                    max=20.0, 
                    step=0.5, 
                    className="form-control mb-3"
                ),
                dbc.Label("Download Filename"),
                dcc.Input(
                    id='filnavn', 
                    type='text', 
                    value=f"dagsplott_{datetime.date.today().strftime('%Y-%m-%d')}_{datetime.date.today().strftime('%Y-%m-%d')}.xlsx",
                    className="form-control mb-3"
                ),
                dbc.Button("Download", id="btn_download", n_clicks=0, color="primary", className="w-100"),
                dcc.Download(id="download_excel")
            ])
        ], style={'width': '300px'}),
        id="sidebar",
        is_open=False,
        className="position-fixed",
        style={'top': '50px', 'left': '10px', 'zIndex': '998'}
    ),
    dcc.Store(id='data_store')
], className="container-fluid", style={'padding': '20px'})

# Callbacks
@app.callback(
    Output('sidebar', 'is_open'),
    [Input('toggle_sidebar', 'n_clicks')],
    [State('sidebar', 'is_open')]
)
def toggle_sidebar(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

@app.callback(
    Output('data_store', 'data'),
    [Input('words', 'value'),
     Input('avisnavn', 'value'),
     Input('mid_date', 'date'),
     Input('period_size', 'value')]
)
def update_data(words, avisnavn, mid_date, period_size):
    mid_date = datetime.datetime.strptime(mid_date.split('T')[0], '%Y-%m-%d').date()
    allword = list(set([w.strip() for w in words.split(',')]))[:30]
    if avisnavn == "--ingen--":
        avisnavn = None
    period_size = period_size if period_size is not None else max_days

    df = ngram(allword, mid_date, "", title=avisnavn)
    return df.to_json(date_format='iso')

# Sync year picker with date picker
@app.callback(
    Output('mid_date', 'date'),
    [Input('year_picker', 'value')],
    [State('mid_date', 'date')]
)
def update_date_from_year(year, current_date):
    if year is None:
        return current_date
    current = datetime.datetime.strptime(current_date.split('T')[0], '%Y-%m-%d')
    new_date = current.replace(year=year)
    return new_date

@app.callback(
    [Output('ngram_chart', 'figure'),
     Output('content_summary', 'children'),
     Output('download_excel', 'data')],
    [Input('data_store', 'data'),
     Input('mid_date', 'date'),
     Input('period_size', 'value'),
     Input('smooth_slider', 'value'),
     Input('theme', 'value'),
     Input('alpha', 'value'),
     Input('width', 'value'),
     Input('plot_type', 'value'),
     Input('btn_download', 'n_clicks')],
    [State('words', 'value'),
     State('avisnavn', 'value'),
     State('filnavn', 'value')]
)
def update_chart(data_json, mid_date, period_size, smooth_slider, theme, alpha, width, plot_type, n_clicks, words, avisnavn, filnavn):
    if data_json is None:
        return go.Figure(), "Ingen data", None
    
    df = pd.read_json(StringIO(data_json))
    
    mid_date = datetime.datetime.strptime(mid_date.split('T')[0], '%Y-%m-%d').date()
    period_size = period_size if period_size is not None else max_days
    smooth_slider = smooth_slider if smooth_slider is not None else 3

    df_for_print = adjust(df, mid_date, period_size, smooth_slider)

    traces = []
    for col in df_for_print.columns:
        traces.append(go.Scatter(
            x=df_for_print.index,
            y=df_for_print[col],
            mode=plot_type,
            name=col,
            opacity=alpha if alpha is not None else 0.9,
            line=dict(width=width if width is not None else 3.0),
            hovertemplate=f"{col}<br>Date: %{{x}}<br>Freq: %{{y}}"
        ))

    layout = go.Layout(
        template=theme if theme is not None else 'plotly',
        height=500,
        xaxis_title="Dato",
        yaxis_title="Frekvens",
        hovermode="x unified"
    )
    fig = go.Figure(data=traces, layout=layout)

    start_date = mid_date - datetime.timedelta(days=period_size)
    end_date = mid_date + datetime.timedelta(days=period_size)
    summary = f"Søk: {words} | Publikasjon: {avisnavn or 'Alle'} | Periode: {start_date.strftime('%Y-%m-%d')} til {end_date.strftime('%Y-%m-%d')}"
    
    if n_clicks > 0:
        excel_data = to_excel(df_for_print)
        return fig, summary, dcc.send_bytes(excel_data, filnavn)
    return fig, summary, None

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)