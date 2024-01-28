import datetime

import dash
import pandas as pd
from dash import Dash, dcc, html, Input, Output, callback
import plotly
import plotly.subplots

import numpy as np

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = Dash(__name__, external_stylesheets=external_stylesheets)
app.layout = html.Div(
    html.Div([
        html.H4('TERRA Satellite Live Feed'),
        html.Div(id='live-update-text'),
        dcc.Graph(id='live-update-graph'),
        dcc.Interval(
            id='interval-component',
            interval=1*50,  # in milliseconds
            n_intervals=0,
        )
    ])
)


@callback(Output('live-update-text', 'children'),
              Input('interval-component', 'n_intervals'))
def update_metrics(n):
    lon, lat, alt = (np.random.random() , np.random.random() ,np.random.random())
    style = {'padding': '5px', 'fontSize': '16px'}
    return [
        html.Span('Longitude: {0:.2f}'.format(lon), style=style),
        html.Span('Latitude: {0:.2f}'.format(lat), style=style),
        html.Span('Altitude: {0:0.2f}'.format(alt), style=style)
    ]


data = {
        'time': [],
        'Latitude': [],
        'Longitude': [],
        'Altitude': []
    }

WINDOW_SIZE = 50


# Multiple components can update everytime interval gets fired.
@callback(Output('live-update-graph', 'figure'),
              Input('interval-component', 'n_intervals'))
def update_graph_live(n):
    global data
    now = datetime.datetime.now()
    # Collect some data
    for i in range(180):
        time = datetime.datetime.now() - datetime.timedelta(seconds=i*20)

    data['Longitude'].append(600 * np.random.random())
    data['Latitude'].append(600 * np.random.random())
    data['Altitude'].append(600 * np.random.random())
    data['time'].append(now)

    data['Longitude'] = data['Longitude'][-WINDOW_SIZE:]
    data['Latitude'] = data['Latitude'][-WINDOW_SIZE:]
    data['Altitude'] = data['Altitude'][-WINDOW_SIZE:]
    data['time'] = data['time'][-WINDOW_SIZE:]

    # take df with window size for all columns
    df = pd.DataFrame(data)
    df = df.tail(WINDOW_SIZE)
    df = df.reset_index(drop=True)


    # Create the graph with subplots
    fig = plotly.subplots.make_subplots(rows=2, cols=1, vertical_spacing=0.2)
    fig['layout']['margin'] = {
        'l': 30, 'r': 10, 'b': 30, 't': 10
    }
    fig['layout']['legend'] = {'x': 0, 'y': 1, 'xanchor': 'left'}

    fig.add_trace({
        'x': df['time'],
        'y': df['Altitude'],
        'name': 'Altitude',
        'mode': 'lines+markers',
        'type': 'scatter'
    }, 1, 1)
    fig.add_trace({
        'x': df['time'],
        'y': df['Latitude'],
        'text': df['time'],
        'name': 'Longitude vs Latitude',
        'mode': 'lines+markers',
        'type': 'scatter'
    }, 2, 1)

    return fig

if __name__ == '__main__':
    app.run(debug=True)