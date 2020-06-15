# -*- coding: utf-8 -*-
import base64
import io

import dash
import dash_auth
import dash_table
import json
import dash_core_components as dcc
import dash_daq as daq
import dash_bootstrap_components as dbc
import dash_html_components as html
from dash.dependencies import Input, Output, State
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import plotly.express as px
from itertools import cycle
import time

import pandas as pd
import numpy as np
import datetime
from utils import *

VALID_USERNAME_PASSWORD_PAIRS = {
    'caravel': 'assessment'
}

app = dash.Dash(
    __name__, meta_tags=[{"name": "viewport", "content": "width=device-width"}],
    external_stylesheets=[dbc.themes.BOOTSTRAP]
)

auth = dash_auth.BasicAuth(
    app,
    VALID_USERNAME_PASSWORD_PAIRS
)

server = app.server

########## PPG
# production_df = pd.read_csv('data/work_cell_data.csv')
# margin_column = 'Actual vs Planned'
# groupby_primary = 'Batch Close Month'
# groupby_secondary = 'Inventory Org Name'
# descriptors = list(production_df.select_dtypes(exclude=np.number).columns)
##########

########## PPG2
dates = ['Batch Completion Date']
production_df = pd.read_csv('data/cleveland_filtered.csv', parse_dates=dates)
descriptors = ['Batch Completion Date', 'Batch Number', 'Tank Number',
       'Cost Center', 'Technology', 'Product', 'Inventory Category',
       'Equalization Lot Number', 'Parent Batch Planned Qty',
       'Parent Batch Actual Qty']
time_components = ['PA Time',
 'Formulated CM Time',
 'QC Adj CM Time',
 'Tot. CM Time',
 '80 appv.',
 'Filling Time',
 '90 appv.',
 'Tot. Time']
for col in time_components:
    production_df[col] = pd.to_timedelta(production_df[col])
time_column = time_components[-1]
volume_column = 'Parent Batch Actual Qty'
margin_column = "{} By {}".format(volume_column, time_column)
production_df[margin_column] = production_df[volume_column] /\
    (production_df[time_components[-1]].dt.total_seconds()/60/60)
groupby_primary = 'Technology'
groupby_secondary = descriptors[2]
production_df = production_df.loc[production_df[margin_column] < 1e2]
print(production_df[groupby_primary].unique())
##########


production_df[descriptors] = production_df[descriptors].astype(str)
production_json = production_df.to_json()

def make_primary_plot(production_df,
                   margin_column,
                   volume_column,
                   groupby_primary,
                   groupby_secondary,
                   time_column,
                   filter_selected=None,
                   filter_category=None,
                   results_df=None,
                   chart_type='Parallel Coordinates (Time)',
                   all_lines=True,
                   sort_by='mean',
                   rate=True,
                   quant=[0.02, 0.98]):
    ### Preprocessing
    if (rate) and (chart_type != 'Parallel Coordinates (Time)'):
        margin_column = "{} By {}".format(volume_column, time_column)
        production_df[margin_column] = production_df[volume_column] / (production_df[time_column].dt.total_seconds()/60/60)
    elif chart_type != 'Parallel Coordinates (Time)':
        margin_column = "{}".format(time_column)
        production_df[margin_column] = production_df[time_column].dt.total_seconds()/60/60
    production_df = production_df.loc[production_df[margin_column] < np.inf]
    production_df = production_df.loc[(production_df[margin_column] <
               production_df[margin_column].quantile(quant[1])) &
              (production_df[margin_column] >
               production_df[margin_column].quantile(quant[0]))]

    ### Charts
    if chart_type == 'Parallel Coordinates (Time)':
        df = production_df.groupby(groupby_primary)[time_components].agg(lambda x: x.median())
        df = df.reset_index()
        for col in time_components:
            df[col] = df[col].dt.total_seconds()/60/60
        df[time_components] = np.round(df[time_components]) #px does not round automatically
        df = df.sort_values(by='Tot. Time').reset_index(drop=True)
        dimensions = list([
                    dict(tickvals = list(df['Tot. Time']),
                         ticktext = list(df[groupby_primary]),
                         label = groupby_primary, values = df['Tot. Time']),
                ])
        for col in time_components:
            dimensions.append(dict(label = col, values = df[col]))

        fig = go.Figure(data=
            go.Parcoords(
                line = dict(color = df['Tot. Time'],
                           colorscale = 'Electric',
                           showscale = True,
                           cmin = min(df['Tot. Time']),
                           cmax = max(df['Tot. Time'])),
                dimensions = dimensions,

            )
        )
    elif chart_type == 'Scatter (Rate)':

        dff = pd.DataFrame(production_df.groupby([groupby_primary, groupby_secondary])[[margin_column, volume_column]]\
             .median().sort_values(by=margin_column, ascending=False)).reset_index()
        dff['median'] = dff.groupby(groupby_secondary)[margin_column].\
                transform('median')

        dff = dff.sort_values(['median', margin_column],
            ascending=False).reset_index(drop=True)
        dff = dff[dff.columns[:-1]]
        if groupby_primary == 'Cost Center':
            dff[groupby_primary] = '_' + dff[groupby_primary] + ' '

        fig = go.Figure()

        for data in px.scatter(
                dff,
                x=groupby_primary,
                y=margin_column,
                size=volume_column,
                color=groupby_secondary,
                hover_data=[groupby_primary],
                opacity=0.6).data:
            fig.add_trace(
                data
            ),
    elif chart_type == 'Distribution (Rate)':
        fig = go.Figure()
        if all_lines:
            data = production_df
        else:
            data = production_df.loc[production_df['Cost Center'] == line]
        temp = pd.DataFrame(data.groupby([groupby_primary])[[margin_column, volume_column]]\
         .median().sort_values(by=margin_column, ascending=False)).reset_index()
        temp2 = pd.DataFrame(data.groupby([groupby_primary])[[margin_column, volume_column]]\
             .mean().sort_values(by=margin_column, ascending=False)).reset_index()
        data['median'] = temp.groupby(groupby_primary)[margin_column].\
                transform('median')
        data['mean']  = temp2.groupby(groupby_primary)[margin_column].\
                transform('mean')
        if sort_by == 'median':
            data = data.sort_values(['median', margin_column],
                ascending=False).reset_index(drop=True)
        else:
            data = data.sort_values(['mean', margin_column],
                ascending=False).reset_index(drop=True)
        data['Site'] = ''
        if sort_by == 'mean':
            products = list(data.groupby(groupby_primary)[margin_column].mean().sort_values().index)
        elif sort_by == 'median':
            products = list(data.groupby(groupby_primary)[margin_column].median().sort_values().index)
        elif sort_by == 'std':
            products = list(data.groupby(groupby_primary)[margin_column].std().sort_values().index)
        for index, product in enumerate(products):

            if sort_by == 'median':
                name = 'Avg: {:.2f}, {}'.format(temp.loc[temp[groupby_primary] == product][margin_column].values[0], product)
            elif sort_by =='mean':
                name = 'Avg: {:.2f}, {}'.format(temp2.loc[temp2[groupby_primary] == product][margin_column].values[0], product)
            elif sort_by =='std':
                name = 'Std: {:.2f}, {}'.format(data.loc[data[groupby_primary] == product][margin_column].std(), product)
            fig.add_trace(go.Violin(y=data.loc[data[groupby_primary] == product]['Site'],
                                    x=data.loc[data[groupby_primary] == product][margin_column],
                                    name=name,
                                    side='positive')
                         )
        fig.update_traces(meanline_visible=True, orientation='h')
        fig.update_xaxes(rangemode="nonnegative")


    elif "vs" in margin_column:
        margin_column = '{} (% by {}, {})'\
                       .format(margin_column, groupby_primary, groupby_secondary)
        dff = pd.DataFrame(((production_df.groupby([groupby_primary, groupby_secondary])\
                             ['Actual Qty In (KLG)'].sum() -
                         production_df.groupby([groupby_primary, groupby_secondary])\
                             ['Planned Qty In (KLG)'].sum()) /
                         production_df.groupby([groupby_primary, groupby_secondary])\
                            ['Planned Qty In (KLG)'].sum()) * 100).reset_index()
        dff.columns = [groupby_primary, groupby_secondary, margin_column]
        fig = px.bar(dff, dff[groupby_primary],
                 margin_column,
                 color=groupby_secondary,
                 barmode='group')

    fig.layout.clickmode = 'event+select'
    fig.update_layout({
            "height": 600,
            "plot_bgcolor": "#FFFFFF",
            "paper_bgcolor": "#FFFFFF",
    }
    )
    if chart_type != 'Parallel Coordinates (Time)':
        if chart_type != 'Distribution (Rate)':
            fig.update_layout({
                "title": '{}'.format(margin_column),
                "yaxis.title": "{}".format(margin_column),
                "xaxis.title": "{}".format(groupby_primary),
                "margin": dict(
                       l=0,
                       r=0,
                       b=0,
                       t=30,
                       pad=4
    ),
                "xaxis.tickfont.size": 8,
                })
        else:
            fig.update_layout({
                    "title": '{}'.format(margin_column),
                    "xaxis.title": "{}".format(margin_column),
                    "yaxis.title": "{}".format(groupby_primary),
                    "margin": dict(
                           l=0,
                           r=0,
                           b=0,
                           t=30,
                           pad=4
        ),
                    "xaxis.tickfont.size": 8,
                    })
    return fig

def make_secondary_plot(production_df,
                   margin_column,
                   groupby_primary,
                   groupby_secondary,
                   filter_selected=None,
                   filter_category=None,
                   results_df=None,
                   chart_type='time'):
    if chart_type == 'time':

        production_df = production_df.sort_values(dates[-1]).reset_index()
        fig = px.line(production_df.loc[production_df[groupby_primary].dropna().index],
              x=dates[-1], y=volume_column, color=groupby_primary)
    else: fig = px.violin(production_df,
                    y=margin_column,
                    x=groupby_primary,
                    color=groupby_secondary)#, violinmode='overlay')
    fig.update_layout({
                "plot_bgcolor": "#FFFFFF",
                "paper_bgcolor": "#FFFFFF",
                # "title": '{} by {}'.format(volume_column,
                #  dates[-1]),
                "yaxis.title": "{}".format(volume_column),
                "height": 300,
                "margin": dict(
                       l=0,
                       r=0,
                       b=0,
                       t=30,
                       pad=4),
                "xaxis":{'rangeselector': {'buttons': list([{'count': 1, 'label': '1M', 'step': 'month', 'stepmode': 'backward'},
                                                          {'count': 3, 'label': '3M', 'step': 'month', 'stepmode': 'backward'},
                                                          {'count': 6, 'label': '6M', 'step': 'month', 'stepmode': 'backward'},
                                                          {'count': 1, 'label': '1Y', 'step': 'year', 'stepmode': 'backward'},
                                                          {'step': 'all'}])}},
                })
    return fig

def make_tertiary_plot(production_df,
                       margin_column,
                       descriptors,
                       clickData=None,
                       toAdd=None,
                       col=None,
                       val=None,
                       subdf=None,
                       family=None,
                       category_filter=None):
    desc = []
    if toAdd is not None:
        for item in toAdd:
            if item not in desc:
                desc.append(item)
    if subdf is not None:
        test = subdf
        title = 'Main Plot Selection'
    else:
        if clickData != None:
            val = clickData["points"][0]['x']
            production_df[descriptors] = production_df[descriptors].astype(str)
        elif col == None:
            col = 'Product'
            val = production_df[col].unique()[0]
        if col in desc:
            desc.remove(col)
        test = production_df.loc[production_df[col] == val]
        title = '{}: {}'.format(col,val)

    test = test.replace(np.nan, 'N/A', regex=True)
    test[descriptors] = test[descriptors].astype(str)

    fig = px.sunburst(test, path=desc, color=margin_column, title='{}: {}'.format(
        col, val), hover_data=desc,
        color_continuous_scale=px.colors.sequential.Viridis,
         )
    fig.update_layout({
                "plot_bgcolor": "#FFFFFF",
                "title": title,
                "paper_bgcolor": "#FFFFFF",
                "margin": dict(
                       l=0,
                       r=0,
                       b=0,
                       t=30,
                       pad=4
    ),
                })
    return fig

UPLOAD = html.Div([
    html.Div([
    html.Div([
        dcc.Upload(
            id='upload-data',
            children=html.Div([
                'Drag and Drop or ',
                html.A('Select Files')
            ]),
            style={
                'width': '95%',
                'height': '60px',
                # 'lineHeight': '60px',
                'borderWidth': '1px',
                'borderStyle': 'dashed',
                'borderRadius': '5px',
                'textAlign': 'center',
                'vertical-align': 'middle',
                'margin': '10px',

                'padding': '5px',
            },
            multiple=False
        ),],className='four columns',
            style={
            'margin-left': '40px',
            },
        id='up-option-1',),
        html.Div([
        html.P(' - or - ',
        style={
               'textAlign': 'center',
               'margin-top': '30px'}
               ),],className='four columns',
                   id='up-option-2',
                             ),
        html.Div([
        dcc.Dropdown(id='preset-files',
                     multi=False,
                     options=[{'label': i, 'value': i} for i in ['polyamides', 'films']],
                     # placeholder="Select Cloud Dataset",
                     className='dcc_control',
                     style={
                            'textAlign': 'center',
                            'width': '95%',
                            'margin': '10px',
                            }
                            ),],className='four columns',
                            id='up-option-3',
                                                        style={
                                                        'margin-right': '40px',
                                                               }
                                                               ),
        ], className='row flex-display',
        ),
    html.P('Margin Column'),
    dcc.Dropdown(id='upload-margin',
                 multi=False,
                 options=[],
                 className="dcc_control",
                 style={'textAlign': 'center',
                        'margin-bottom': '10px'}),
    html.P('Volume Column'),
    dcc.Dropdown(id='upload-volume',
                 multi=False,
                 options=[],
                 className="dcc_control",
                 style={'textAlign': 'center',
                        'margin-bottom': '10px'}),
    html.P('Descriptor-Attribute Columns'),
    dcc.Dropdown(id='upload-descriptors',
                 multi=True,
                 options=[],
                 className="dcc_control",
                 style={'textAlign': 'left',
                        'margin-bottom': '10px'}),
    html.P('p-Value Limit for Median Test', id='pvalue-number'),
    dcc.Slider(id='p-value-slider',
               min=0.01,
               max=1,
               step=0.01,
               value=0.5),
    html.Button('Process data file',
                id='datafile-button',
                style={'textAlign': 'center',
                       'margin-bottom': '10px'}),
],)

HIDDEN = html.Div([
    html.Div(id='production-df-upload',
             style={'display': 'none'},
             children=production_json),
    # html.Div(id='stat-df-upload',
    #          style={'display': 'none'},
    #          children=stat_json),
    html.Div(id='descriptors-upload',
             style={'display': 'none'},
             children=descriptors),
    html.Div(id='margin-upload',
             style={'display': 'none'},
             children=margin_column),
    html.Div(id='primary-upload',
             style={'display': 'none'},
             children=groupby_primary),
    html.Div(id='secondary-upload',
             style={'display': 'none'},
             children=groupby_secondary),
    html.Div(id='production-df-holding',
             style={'display': 'none'},
             children=None),
])

ABOUT = html.Div([dcc.Markdown('''

###### This dashboard evaluates Work Cell correlation with Planned vs Actual production ######

**KPIs:**

--KPI Description--

**Charts:**

--Primary, Secondary, Tertiary Chart Description--

**Controls:**

--Controls Tab Description--

Visualization Tab:

--Analytics Tab Description--

''')],style={'margin-top': '20px',
             'max-height': '500px',
             'overflow': 'scroll'})

search_bar = html.A(
    dbc.Row(
    [
        # dbc.Col(html.Img(src='assets/mfg_logo.png', height="40px")),
    ],
    no_gutters=True,
    className="ml-auto flex-nowrap mt-3 mt-md-0",
    align="center",
),
href='https://mfganalytic.com/',
className="ml-auto flex-nowrap mt-3 mt-md-0",
)

NAVBAR = dbc.Navbar(
    [ html.A(
            dbc.Row(
                [
                    dbc.Col(html.Img(src='assets/dashboard_logo.png', height="50px")),
                ],
                align="center",
                no_gutters=True,
            ),
            href='http://caravelsolutions.com/',
            ),
        dbc.Collapse(search_bar, id="navbar-collapse", navbar=True),
    ],
    color="light",
    dark=False,
    sticky='top',
)

VISUALIZATION = html.Div([
    html.P('Filter'),
    dcc.Dropdown(id='filter_dropdown_1',
                 options=[{'label': i, 'value': i} for i in
                            descriptors],
                 value='Cost Center',
                 multi=False,
                 className="dcc_control"),
    dcc.Dropdown(id='filter_dropdown_2',
                 options=[{'label': i, 'value': i} for i in
                            production_df['Cost Center'].unique()],
                 value=production_df['Cost Center'].unique(),
                 multi=True,
                 className="dcc_control"),
    html.P('Groupby Primary'),
    dcc.Dropdown(id='primary_dropdown',
                 options=[{'label': i, 'value': i} for i in
                           descriptors],
                 value='Technology',
                 multi=False,
                 className="dcc_control"),
    html.P('Groupby Secondary'),
    dcc.Dropdown(id='secondary_dropdown',
                 options=[{'label': i, 'value': i} for i in
                           descriptors],
                 value='Cost Center',
                 multi=False,
                 className="dcc_control"),
    html.P('Process Times'),
    dcc.Dropdown(id='time_dropdown',
                 options=[{'label': i, 'value': i} for i in
                           time_components],
                 value=time_components[-1],
                 multi=False,
                 className="dcc_control"),
    # html.P('Quantile Range'),
    # dcc.RangeSlider(
    #     id='quantile-slider',
    #     min=0,
    #     max=1,
    #     step=0.05,
    #     value=[.1, .9]
    # ),
    html.P('Graph Type'),
    dcc.RadioItems(id='distribution',
                 options=[{'label': i, 'value': i} for i in
                           ['Scatter (Rate)', 'Distribution (Rate)', 'Parallel Coordinates (Time)']],
                 value='Parallel Coordinates (Time)',
                 className="dcc_control"),
      ],style={'max-height': '500px',
               'margin-top': '20px'}
)

KPIS = html.Div([
    html.Div([
        html.Div([
            html.Div([
                html.H5(id='kpi-1'), html.H6(margin_column, id='margin-label')
            ], id='kpi1', className='six columns', style={'margin': '10px'}
            ),
            html.Div([
                html.Img(src='assets/money_icon_1.png', width='80px'),
            ], id='icon1', className='five columns',
                style={
                    'textAlign': 'right',
                    'margin-top': '20px',
                    'margin-right': '20px',
                    'vertical-align': 'text-bottom',
                }),
            ], className='row flex-display',
            ),
        ], className='mini_container',
           id='margin-rev',),
    html.Div([
        html.Div([
            html.Div([
                html.H5(id='kpi-2'), html.H6('Batches', id='margin-label2')
            ], className='six columns', style={'margin': '10px'}, id='kpi2',
            ),
            html.Div([
                html.Img(src='assets/product_icon_3.png', width='80px'),
            ], className='five columns',
                style={
                    'textAlign': 'right',
                    'margin-top': '20px',
                    'margin-right': '20px',
                    'vertical-align': 'text-bottom',
                }),
            ], className='row flex-display',
            ),
        ], className='mini_container',
           id='margin-rev-percent',),
    html.Div([
        html.Div([
            html.Div([
                html.H5(id='kpi-3'), html.H6('Volume', id='margin-label3')
            ], className='six columns', style={'margin': '10px'}, id='kpi3',
            ),
            html.Div([
                html.Img(src='assets/volume_icon_3.png', width='80px'),
            ], className='five columns',
                style={
                    'textAlign': 'right',
                    'margin-top': '20px',
                    'margin-right': '20px',
                    'vertical-align': 'text-bottom',
                }),
            ], className='row flex-display',
            ),
        ], className='mini_container',
           id='margin-products',),
    ], className='row container-display',
)

# ANALYTICS = html.Div([
# html.P('Families',
# style={"margin-top": "20px"}),
# dcc.Dropdown(id='family_dropdown_analytics',
#              options=[{'label': i, 'value': i} for i in
#                         production_df[category_filter].unique()],
#              value=production_df[category_filter].unique(),
#              multi=True,
#              className="dcc_control"),
# html.P('Descriptors'),
# dcc.Dropdown(id='descriptor_dropdown_analytics',
#              options=[{'label': i, 'value': i} for i in
#                        descriptors],
#              value=descriptors[:2],
#              multi=True,
#              className="dcc_control",
#              style={'margin-bottom': '10px'}),
# html.Button('Find opportunity',
#             id='opportunity-button',
#             style={'textAlign': 'center',
#                    'margin-bottom': '10px'}),
#
#     ], style={'max-height': '500px',
#              'overflow': 'scroll',
#              'margin-top': '20px'}
#
#     )

app.layout = html.Div([NAVBAR,
html.Div(className='pretty_container', children=[KPIS,
    html.Div([
        html.Div([
        dcc.Tabs(id='tabs-control', value='tab-1', children=[
            dcc.Tab(label='About', value='tab-3',
                    children=[ABOUT]),
            # dcc.Tab(label='Upload', value='tab-4',
                    # children=[UPLOAD]),
            dcc.Tab(label='Visualization', value='tab-1',
                    children=[VISUALIZATION]),
            # dcc.Tab(label='Analytics', value='tab-2',
            #         children=[ANALYTICS]),
                    ]),
            ], className='mini_container',
               id='descriptorBlock',
            ),
        html.Div([
            dcc.Graph(id='primary_plot',
                      figure=make_primary_plot(production_df,
                        margin_column, volume_column, groupby_primary,
                        groupby_secondary, time_column)),
            ], className='mini_container',
               id='ebit-family-block',
               style={'display': 'block'},
            ),
    ], className='row container-display',
    ),
    html.Div([
        html.Div([
            dcc.Graph(className='inside_container',
                        id='secondary_plot',
                        figure=make_secondary_plot(production_df,
                                           margin_column,
                                           groupby_primary,
                                           groupby_secondary,
                                           chart_type='time')
                        ),
            html.Div([
            dcc.Loading(
                id="loading-1",
                type="default",
                children=dash_table.DataTable(id='opportunity-table',
                                 row_selectable='multi',),),
                    ],
                    id='opportunity-table-block',
                    style={'overflow': 'scroll',
                           'display': 'none'}),
            ], className='mini_container',
               id='violin',
               style={'display': 'block'},
                ),
        # html.Div([
        #     dcc.Dropdown(id='length_width_dropdown',
        #                 options=[{'label': i, 'value': i} for i in
        #                            descriptors],
        #                 value=descriptors[:-3],
        #                 multi=True,
        #                 placeholder="Include in sunburst chart...",
        #                 className="dcc_control"),
        #     dcc.Graph(
        #                 id='tertiary_plot',
        #                 figure=make_tertiary_plot(production_df, margin_column,
        #                                  descriptors, toAdd=descriptors[:-3])
        #                 ),
        #         ], className='mini_container',
        #            id='sunburst',
        #         ),
            ], className='row container-display',
               style={'margin-bottom': '10px'},
            ),
    ],
    ), HIDDEN,
    html.Div([], id='clickdump'),
],
)
app.config.suppress_callback_exceptions = True

@app.callback(
    [Output('kpi-1', 'children'),
     Output('kpi-2', 'children'),
     Output('kpi-3', 'children')],
    [Input('filter_dropdown_1', 'value'),
    Input('filter_dropdown_2', 'value'),
    Input('opportunity-table', 'derived_viewport_selected_rows'),
    Input('opportunity-table', 'data'),
    Input('tabs-control', 'value'),
    Input('production-df-upload', 'children'),
    Input('margin-upload', 'children'),
    Input('primary_dropdown', 'value'),
    Input('secondary_dropdown', 'value'),
    Input('secondary_plot', 'clickData'),
    Input('primary_plot', 'selectedData'),
    Input('secondary_plot', 'relayoutData'),
    Input('time_dropdown', 'value')
    ]
)
def display_opportunity(filter_category, filter_selected, rows, data, tab,
                        production_df, margin_column, groupby_primary,
                        groupby_secondary, clickData, selectedData,
                        relayoutData, time_column):
    production_df = pd.read_json(production_df, convert_dates=dates)
    production_df = production_df.loc[production_df[filter_category].isin(
        filter_selected)]
    for col in time_components:
        production_df[col] = pd.to_timedelta(production_df[col], unit='ms')
    production_df[margin_column] = production_df[volume_column] /\
        (production_df[time_column].dt.total_seconds()/60/60)
    production_df = production_df.loc[production_df[margin_column] < np.inf]
    production_df = production_df.loc[(production_df[margin_column] <
        production_df[margin_column].quantile(0.995))]
    if relayoutData is not None:
        if 'xaxis.range[0]' in relayoutData.keys():
            start = pd.to_datetime(relayoutData['xaxis.range[0]'])
            end = pd.to_datetime(relayoutData['xaxis.range[1]'])
            production_df = production_df.loc[(production_df[dates[-1]] < end) &
                                              (production_df[dates[-1]] > start)]
    old_kpi_2 = production_df.shape[0]
    old_kpi_1 = production_df[margin_column].mean()
    old_kpi_3 = production_df[volume_column].sum()
    # old_kpi_1 = (production_df['Actual Qty In (KLG)'].sum() -
    #              production_df['Planned Qty In (KLG)'].sum()) * 5
    # old_kpi_3 = production_df['Actual Qty In (KLG)'].sum()
    return "{:.2f} Avg. Gal/Hr".format(old_kpi_1), \
    "{}".format(old_kpi_2),\
    "{:.2f} M Gal".format(old_kpi_3/1e6)

@app.callback(
    [Output('filter_dropdown_2', 'options'),
     Output('filter_dropdown_2', 'value')],
    [Input('filter_dropdown_1', 'value')]
)
def update_filter(category):
    return [{'label': i, 'value': i} for i in production_df[category].unique()],\
        list(production_df[category].unique())

@app.callback(
    Output('margin-upload', 'children'),
    [Input('time_dropdown', 'value')]
)
def margin_column(time_column):
    return "{} By {}".format(volume_column, time_column)

@app.callback(
    Output('margin-label', 'children'),
    [Input('time_dropdown', 'value')]
)
def margin_column(time_column):
    return "{} By {}".format(volume_column, time_column)

### FIGURES ###
@app.callback(
    Output('primary_plot', 'figure'),
    [Input('filter_dropdown_1', 'value'),
    Input('filter_dropdown_2', 'value'),
    Input('opportunity-table', 'derived_viewport_selected_rows'),
    Input('opportunity-table', 'data'),
    Input('tabs-control', 'value'),
    Input('production-df-upload', 'children'),
    Input('margin-upload', 'children'),
    Input('primary_dropdown', 'value'),
    Input('secondary_dropdown', 'value'),
    Input('secondary_plot', 'relayoutData'),
    Input('time_dropdown', 'value'),
    Input('distribution', 'value')
    ]
)
def display_primary_plot(filter_category, filter_selected, rows, data, tab,
                        production_df, margin_column, groupby_primary,
                        groupby_secondary, relayoutData, time_column,
                        chart_type):

    production_df = pd.read_json(production_df, convert_dates=dates)
    production_df = production_df.loc[production_df[filter_category].isin(
        filter_selected)]
    for col in time_components:
        production_df[col] = pd.to_timedelta(production_df[col], unit='ms')
    production_df[margin_column] = production_df[volume_column] /\
        (production_df[time_column].dt.total_seconds()/60/60)
    production_df = production_df.loc[production_df[margin_column] < np.inf]
    production_df = production_df.loc[(production_df[margin_column] <
        production_df[margin_column].quantile(0.995))]
    if relayoutData is not None:
        if 'xaxis.range[0]' in relayoutData.keys():
            start = pd.to_datetime(relayoutData['xaxis.range[0]'])
            end = pd.to_datetime(relayoutData['xaxis.range[1]'])
            production_df = production_df.loc[(production_df[dates[-1]] < end) &
                                              (production_df[dates[-1]] > start)]
        return make_primary_plot(production_df,
          margin_column, volume_column, groupby_primary,
          groupby_secondary, time_column, chart_type=chart_type)

    return make_primary_plot(production_df,
      margin_column, volume_column, groupby_primary,
      groupby_secondary, time_column, chart_type=chart_type)

@app.callback(
    Output('secondary_plot', 'figure'),
    [Input('filter_dropdown_1', 'value'),
    Input('filter_dropdown_2', 'value'),
    Input('opportunity-table', 'derived_viewport_selected_rows'),
    Input('opportunity-table', 'data'),
    Input('tabs-control', 'value'),
    Input('production-df-upload', 'children'),
    Input('margin-upload', 'children'),
    Input('primary_dropdown', 'value'),
    Input('secondary_dropdown', 'value'),
    Input('time_dropdown', 'value')
    ]
)
def display_secondary_plot(filter_category, filter_selected, rows, data, tab,
                        production_df, margin_column, groupby_primary,
                        groupby_secondary, time_column):

    production_df = pd.read_json(production_df, convert_dates=dates)
    production_df = production_df.loc[production_df[filter_category].isin(
        filter_selected)]
    for col in time_components:
        production_df[col] = pd.to_timedelta(production_df[col], unit='ms')
    production_df[margin_column] = production_df[volume_column] /\
        (production_df[time_column].dt.total_seconds()/60/60)
    production_df = production_df.loc[production_df[margin_column] < np.inf]
    production_df = production_df.loc[(production_df[margin_column] <
        production_df[margin_column].quantile(0.995))]
    return make_secondary_plot(production_df,
        margin_column, groupby_primary,
        groupby_secondary, chart_type='time')

# @app.callback(
#     Output('tertiary_plot', 'figure'),
#     [Input('filter_dropdown_1', 'value'),
#     Input('filter_dropdown_2', 'value'),
#     Input('opportunity-table', 'derived_viewport_selected_rows'),
#     Input('opportunity-table', 'data'),
#     Input('tabs-control', 'value'),
#     Input('production-df-upload', 'children'),
#     Input('margin-upload', 'children'),
#     Input('primary_dropdown', 'value'),
#     Input('secondary_dropdown', 'value'),
#     Input('secondary_plot', 'clickData'),
#     Input('primary_plot', 'selectedData'),
#     Input('length_width_dropdown', 'value'),
#     Input('descriptors-upload', 'children'),
#     Input('secondary_plot', 'relayoutData'),
#     Input('time_dropdown', 'value')
#     ]
# )
# def display_tertiary_plot(filter_category, filter_selected, rows, data, tab,
#                         production_df, margin_column, groupby_primary,
#                         groupby_secondary, clickData, selectedData,
#                          toAdd, descriptors, relayoutData, time_column):
#
#     production_df = pd.read_json(production_df, convert_dates=dates)
#     production_df = production_df.loc[production_df[filter_category].isin(
#         filter_selected)]
#     for col in time_components:
#         production_df[col] = pd.to_timedelta(production_df[col], unit='ms')
#     production_df[margin_column] = production_df[volume_column] /\
#         (production_df[time_column].dt.total_seconds()/60/60)
#     production_df = production_df.loc[production_df[margin_column] < np.inf]
#     production_df = production_df.loc[(production_df[margin_column] <
#         production_df[margin_column].quantile(0.995))]
#     ctx = dash.callback_context
#     if ctx.triggered[0]['prop_id'] == 'primary_plot.selectedData':
#         dff = pd.DataFrame(selectedData['points'])
#         # dfff = pd.DataFrame(production_df[groupby_secondary].unique())
#         subdf = production_df.loc[(production_df[groupby_primary].isin(dff['x']))]# &
#                 # (production_df[groupby_secondary].isin(dfff.iloc
#                 # [dfff.index.isin(dff['curveNumber'])][0].values))]
#
#         return make_tertiary_plot(production_df, margin_column, descriptors,
#             toAdd=toAdd,
#             subdf=subdf)
#
#     col = groupby_primary
#     val = production_df[col].unique()[0]
#
#     return make_tertiary_plot(production_df, margin_column, descriptors,
#         clickData=clickData, toAdd=toAdd, col=col, val=val)

if __name__ == "__main__":
    app.run_server(debug=True)
