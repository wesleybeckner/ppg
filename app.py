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
production_df = pd.read_excel('data/work_cell_data.xlsx')
margin_column = 'Actual vs Planned'
groupby_primary = 'Batch Close Month'
groupby_secondary = 'Inventory Org Name'
descriptors = list(production_df.select_dtypes(exclude=np.number).columns)
##########

production_df[descriptors] = production_df[descriptors].astype(str)
production_json = production_df.to_json()

def calculate_margin_opportunity(production_df,
                                 groupby_primary,
                                 margin_column,
                                 category_filter,
                                 descriptors=None,
                                 families=None,
                                 results_df=None,
                                 selecteddata=None):
    old_products = production_df['Product'].unique().shape[0]
    if selecteddata is not None:
        if families != None:
            production_df = production_df.loc[production_df[category_filter]\
                .isin(families)]
        dff = pd.DataFrame(selecteddata['points'])
        subdf = production_df.loc[(production_df[margin_column].isin(dff['y'])) &
                          (production_df[groupby_primary].isin(dff['marker.size']))]
    elif results_df is not None:
        new_df = production_df
        for index in results_df.index:
            new_df = new_df.loc[~((new_df[category_filter] == \
                results_df.iloc[index]['Family']) &
                        (new_df[results_df.iloc[index]['Descriptor']] \
                            == results_df.iloc[index]['Group']))]

    new_EBITDA = new_df[margin_column].sum()
    EBITDA_percent = new_EBITDA / production_df[margin_column].sum() * 100

    new_products = new_df['Product'].unique().shape[0]

    product_percent_reduction = (new_products) / \
        old_products * 100

    new_kg = new_df[groupby_primary].sum()
    old_kg = production_df[groupby_primary].sum()
    kg_percent = new_kg / old_kg * 100

    return "€{:.2f} M of €{:.2f} M ({:.1f}%)".format(new_EBITDA/1e6,
                production_df[margin_column].sum()/1e6, EBITDA_percent), \
            "{} of {} Products ({:.1f}%)".format(new_products,old_products,
                product_percent_reduction),\
            "{:.2f} M of {:.2f} M kg ({:.1f}%)".format(new_kg/1e6, old_kg/1e6,
                kg_percent)

def make_secondary_plot(production_df,
                   margin_column,
                   groupby_primary,
                   groupby_secondary,
                   filter_selected=None,
                   filter_category=None,
                   results_df=None):

    fig = px.violin(production_df,
                    y=margin_column,
                    x=groupby_primary,
                    color=groupby_secondary)#, violinmode='overlay')
    fig.update_layout({
                "plot_bgcolor": "#FFFFFF",
                "paper_bgcolor": "#FFFFFF",
                "title": '{} by {}, {}'.format( margin_column,
                 groupby_primary,
                 groupby_secondary),
                "yaxis.title": "{}".format(margin_column),
                # "height": 400,
                "margin": dict(
                       l=0,
                       r=0,
                       b=0,
                       t=30,
                       pad=4),
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
            col = descriptors[0]
            val = production_df[descriptors[0]][0]
        if col in desc:
            desc.remove(col)
        test = production_df.loc[production_df[col] == val]
        title = '{}: {}'.format(col,val)
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

def make_primary_plot(production_df,
                   margin_column,
                   groupby_primary,
                   groupby_secondary,
                   filter_selected=None,
                   filter_category=None,
                   results_df=None):
    if "vs" in margin_column:
        margin_column = '{} (% by {}, {})'\
                       .format(margin_column, groupby_primary, groupby_secondary)
        dff = pd.DataFrame(((production_df.groupby([groupby_primary, groupby_secondary])\
                             ['Actual Qty In (KLG)'].sum() -
                         production_df.groupby([groupby_primary, groupby_secondary])\
                             ['Planned Qty In (KLG)'].sum()) /
                         production_df.groupby([groupby_primary, groupby_secondary])\
                            ['Planned Qty In (KLG)'].sum()) * 100).reset_index()
        dff.columns = [groupby_primary, groupby_secondary, margin_column]
    elif "KLG" in margin_column:
        dff = pd.DataFrame(production_df.groupby([groupby_primary,
                                       groupby_secondary])\
                           [margin_column].sum()).reset_index()
    else:
        dff = pd.DataFrame(production_df.groupby([groupby_primary,
                                       groupby_secondary])\
                           [margin_column].mean()).reset_index()
    fig = px.bar(dff, dff[groupby_primary],
                 margin_column,
                 color=groupby_secondary,
                 barmode='group')

    if results_df is not None:
        new_df = pd.DataFrame()
        for index in results_df.index:
            x = production_df.loc[(production_df[category_filter] == results_df.iloc[index]['Family']) &
                        (production_df[results_df.iloc[index]['Descriptor']] == results_df.iloc[index]['Group'])]
            x['color'] = next(colors_cycle) # for line shapes
            new_df = pd.concat([new_df, x])
            new_df = new_df.reset_index(drop=True)
        shapes=[]
        for index, i in enumerate(new_df['Product']):
            shapes.append({'type': 'line',
                           'xref': 'x',
                           'yref': 'y',
                           'x0': i,
                           'y0': new_df[margin_column][index],
                           'x1': i,
                           'y1': max(production_df[margin_column]),
                           'line':dict(
                               dash="dot",
                               color=new_df['color'][index],)})
        fig.update_layout(shapes=shapes)
    fig.layout.clickmode = 'event+select'
    fig.update_layout({
            "plot_bgcolor": "#FFFFFF",
            "paper_bgcolor": "#FFFFFF",
            # "title": '{} by {}'.format(margin_column, color),
            # "yaxis.title": "{}".format(margin_column),
            "height": 600,
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
        dbc.Col(html.Img(src='assets/mfg_logo.png', height="40px")),
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
                    dbc.Col(html.Img(src='assets/caravel_logo.png', height="40px")),
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
                 value=descriptors[1],
                 multi=False,
                 className="dcc_control"),
    dcc.Dropdown(id='filter_dropdown_2',
                 options=[{'label': i, 'value': i} for i in
                            production_df[groupby_primary].unique()],
                 value=production_df[groupby_primary].unique(),
                 multi=True,
                 className="dcc_control"),
    html.P('Groupby Primary'),
    dcc.Dropdown(id='primary_dropdown',
                 options=[{'label': i, 'value': i} for i in
                           descriptors],
                 value=descriptors[0],
                 multi=False,
                 className="dcc_control"),
    html.P('Groupby Secondary'),
    dcc.Dropdown(id='secondary_dropdown',
                 options=[{'label': i, 'value': i} for i in
                           descriptors],
                 value=descriptors[1],
                 multi=False,
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
                        margin_column, groupby_primary,
                        groupby_secondary)),
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
                                           groupby_secondary)
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
        html.Div([
            dcc.Dropdown(id='length_width_dropdown',
                        options=[{'label': i, 'value': i} for i in
                                   descriptors],
                        value=descriptors[:-3],
                        multi=True,
                        placeholder="Include in sunburst chart...",
                        className="dcc_control"),
            dcc.Graph(
                        id='tertiary_plot',
                        figure=make_tertiary_plot(production_df, margin_column,
                                         descriptors, toAdd=descriptors)
                        ),
                ], className='mini_container',
                   id='sunburst',
                ),
            ], className='row container-display',
               style={'margin-bottom': '10px'},
            ),
    ],
    ), HIDDEN,
    html.Div([], id='clickdump'),
],
)
app.config.suppress_callback_exceptions = True

# @app.callback(
#     [Output('opportunity-table', 'data'),
#     Output('opportunity-table', 'columns'),],
#     [Input('production-df-upload', 'children'),
#      Input('stat-df-upload', 'children'),
#      Input('descriptor_dropdown_analytics', 'value'),
#      Input('family_dropdown_analytics', 'value'),
#      Input('opportunity-button', 'n_clicks'),
#      Input('primary-upload', 'children'),
#      Input('margin-upload', 'children'),
#      Input('filter_dropdown_1', 'value'),]
# )
# def display_opportunity_results(production_df, stat_df, descriptors, families,
#     button, groupby_primary, margin_column, category_filter):
#     ctx = dash.callback_context
#     if ctx.triggered[0]['prop_id'] == 'opportunity-button.n_clicks':
#         production_df = pd.read_json(production_df)
#         stat_df = pd.read_json(stat_df)
#         results = maximize_ebitda(production_df, stat_df, families, descriptors,
#             groupby_primary, margin_column, category_filter)
#         results[results.columns[3:]] = np.round(results[results.columns[3:]].astype(float))
#         columns=[{"name": i, "id": i} for i in results.columns]
#         return results.to_dict('rows'), columns
#
# @app.callback(
#     [Output('violin_plot', 'style'),
#      Output('opportunity-table-block', 'style'),],
#     [Input('tabs-control', 'value'),]
# )
# def display_violin_plot(tab):
#     if (tab == 'tab-1') | (tab == 'tab-3') | (tab == 'tab-4'):
#             return {'display': 'block',
#              'margin': '10px',
#              'padding': '15px',
#              'position': 'relative',
#              'border-radius': '5px',
#              'width': '95%'}, {'display': 'none'}
#     elif tab == 'tab-2':
#             return {'display': 'none'}, \
#             {'max-height': '500px',
#                'overflow': 'scroll',
#                'display': 'block',
#                'padding': '0px 20px 20px 20px'}

# @app.callback(
#     [Output('clickdump', 'children')],
#     [Input('primary_plot', 'selectedData')]
# )
# def clickdump(data):
#     return json.dumps(data)


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
    ]
)
def display_opportunity(filter_category, filter_selected, rows, data, tab,
                        production_df, margin_column, groupby_primary,
                        groupby_secondary, clickData, selectedData):
    production_df = pd.read_json(production_df)
    production_df = production_df.loc[production_df[filter_category].isin(
        filter_selected)]
    if (tab == 'tab-1') or (tab == 'tab-3') or (tab == 'tab-4'):
        if selectedData is not None:
            return calculate_margin_opportunity(production_df, stat_df,
                groupby_primary, margin_column, category_filter,
                descriptors, families, results_df=None, selecteddata=selecteddata)
        else:
            old_kpi_2 = production_df.shape[0]
            old_kpi_1 = (production_df['Actual Qty In (KLG)'].sum() -
                         production_df['Planned Qty In (KLG)'].sum()) /\
                         production_df['Planned Qty In (KLG)'].sum()
            old_kpi_3 = production_df['Actual Qty In (KLG)'].sum()
            return "{:.2f}%".format(old_kpi_1), \
            "{}".format(old_kpi_2),\
            "{:.2f} M kg".format(old_kpi_3/1e6)
    elif (tab == 'tab-2'):
        results_df = pd.DataFrame(data)
        results_df = results_df.iloc[rows].reset_index(drop=True)
        return calculate_margin_opportunity(production_df, stat_df,
            groupby_primary, margin_column, category_filter, results_df=results_df)

# @app.callback(
#     [Output('filter_dropdown_1', 'options'),
#      Output('filter_dropdown_1', 'value'),
#      Output('descriptor_dropdown_analytics', 'options'),
#      Output('descriptor_dropdown_analytics', 'value'),
#      Output('family_dropdown_analytics', 'options'),
#       Output('family_dropdown_analytics', 'value'),
#       Output('length_width_dropdown', 'options'),
#       Output('length_width_dropdown', 'value'),],
#     [Input('descriptors-upload', 'children'),
#      Input('production-df-upload', 'children')]
# )
# def update_dropdowns(descriptors, production_df):
#     production_df = pd.read_json(production_df)
#     families = list(production_df[category_filter].unique())
#     descriptor_options = [{'label': i, 'value': i} for i in descriptors]
#     family_options = columns = [{'label': i, 'value': i} for i in families]
#     return descriptor_options, descriptors[1], \
#         descriptor_options, \
#         descriptors, family_options, families, descriptor_options, descriptors[:-5]

# @app.callback(
#     Output('pvalue-number', 'children'),
#     [Input('p-value-slider', 'value')]
# )
# def display_descriptor_number(select):
#     return "p-Value Limit for Median Test: {}".format(select)
#
# @app.callback(
#     Output('margin-label', 'children'),
#     [Input('margin-upload', 'children')]
# )
# def display_descriptor_number(select):
#     return select

@app.callback(
    [Output('filter_dropdown_2', 'options'),
     Output('filter_dropdown_2', 'value')],
    [Input('filter_dropdown_1', 'value')]
)
def update_filter(category):
    return [{'label': i, 'value': i} for i in production_df[category].unique()],\
        list(production_df[category].unique())

### FIGURES ###
@app.callback(
    [Output('primary_plot', 'figure'),
    Output('secondary_plot', 'figure'),],
    [Input('filter_dropdown_1', 'value'),
    Input('filter_dropdown_2', 'value'),
    Input('opportunity-table', 'derived_viewport_selected_rows'),
    Input('opportunity-table', 'data'),
    Input('tabs-control', 'value'),
    Input('production-df-upload', 'children'),
    Input('margin-upload', 'children'),
    Input('primary_dropdown', 'value'),
    Input('secondary_dropdown', 'value'),
    ]
)
def display_primary_plot(filter_category, filter_selected, rows, data, tab,
                        production_df, margin_column, groupby_primary,
                        groupby_secondary):

    production_df = pd.read_json(production_df)
    production_df = production_df.loc[production_df[filter_category].isin(
        filter_selected)]

    return [make_primary_plot(production_df,
      margin_column, groupby_primary,
      groupby_secondary),
      make_secondary_plot(production_df,
        margin_column, groupby_primary,
        groupby_secondary)]

@app.callback(
    Output('tertiary_plot', 'figure'),
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
    Input('length_width_dropdown', 'value'),
    Input('descriptors-upload', 'children'),
    ]
)
def display_tertiary_plot(filter_category, filter_selected, rows, data, tab,
                        production_df, margin_column, groupby_primary,
                        groupby_secondary, clickData, selectedData,
                         toAdd, descriptors):

    production_df = pd.read_json(production_df)
    production_df = production_df.loc[production_df[filter_category].isin(
        filter_selected)]
    ctx = dash.callback_context
    if ctx.triggered[0]['prop_id'] == 'primary_plot.selectedData':
        dff = pd.DataFrame(selectedData['points'])
        dfff = pd.DataFrame(production_df[groupby_secondary].unique())
        subdf = production_df.loc[(production_df[groupby_primary].isin(dff['label'])) &
                (production_df[groupby_secondary].isin(dfff.iloc
                [dfff.index.isin(dff['curveNumber'])][0].values))]
        return make_tertiary_plot(production_df, margin_column, descriptors,
            toAdd=toAdd,
            subdf=subdf)

    col = groupby_primary
    val = production_df[col].unique()[0]

    return make_tertiary_plot(production_df, margin_column, descriptors,
        clickData=clickData, toAdd=toAdd, col=col, val=val)

### UPLOAD TOOL ###
# @app.callback(
#     [Output('upload-margin', 'options'),
#    Output('upload-descriptors', 'options'),
#    Output('production-df-holding', 'children'),
#    Output('upload-volume', 'options')],
#   [Input('upload-data', 'contents'),
#    Input('preset-files', 'value')],
#   [State('upload-data', 'filename'),
#    State('upload-data', 'last_modified')])
# def update_production_df_and_table(list_of_contents, preset_file, list_of_names, list_of_dates):
#     if list_of_contents is not None:
#         df = [parse_contents(c, n, d) for c, n, d in
#             zip(list_of_contents, list_of_names, list_of_dates)]
#         df = df[0]
#         columns = [{'label': i, 'value': i} for i in df.columns]
#         columns_table = [{"name": i, "id": i} for i in df.columns]
#         return columns, columns, df.to_json(), columns
#     elif preset_file is not None:
#         df = pd.read_csv('data/{}.csv'.format(preset_file))
#         columns = [{'label': i, 'value': i} for i in df.columns]
#         columns_table = [{"name": i, "id": i} for i in df.columns]
#         return columns, columns, df.to_json(), columns
#
# @app.callback(
#     [Output('production-df-upload', 'children'),
#     Output('stat-df-upload', 'children'),
#     Output('descriptors-upload', 'children'),
#     Output('margin-upload', 'children'),
#     Output('primary-upload', 'children'),
#     Output('secondary-upload', 'children'),],
#    [Input('production-df-holding', 'children'),
#     Input('upload-margin', 'value'),
#     Input('upload-descriptors', 'value'),
#     Input('datafile-button', 'n_clicks'),
#     Input('upload-volume', 'value'),
#     Input('p-value-slider', 'value')]
# )
# def update_main_dataframe(holding_df, margin, descriptors, button, volume, pvalue):
#     ctx = dash.callback_context
#     if ctx.triggered[0]['prop_id'] == 'datafile-button.n_clicks':
#         production_df = pd.read_json(holding_df)
#         for desc in descriptors: #9 is arbitrary should be a fraction of total datapoints or something
#             if (len(production_df[desc].unique()) > 9) and (production_df[desc].dtype == float):
#                 production_df[desc] = np.round(production_df[desc].astype(float),1)
#         stat_df = my_median_test(production_df,
#                    metric=margin,
#                    descriptors=descriptors,
#                    stat_cut_off=pvalue,
#                    continuous=False)
#         production_df[descriptors] = production_df[descriptors].astype(str)
#         production_df = production_df.sort_values([category_filter, margin],
#                                                   ascending=False)
#         return production_df.to_json(), stat_df.to_json(), descriptors, margin,\
#             volume
# @app.callback(
#     [Output('opportunity-table', 'data'),
#     Output('opportunity-table', 'columns'),],
#     [Input('descriptor_dropdown_analytics', 'value'),
#      Input('family_dropdown_analytics', 'value'),
#      Input('opportunity-button', 'n_clicks'),
#      Input('production-df-upload', 'children'),
#      Input('stat-df-upload', 'children')]
# )
# def display_opportunity_results(descriptors, families,
#                                 button, production_df, stat_df):
#     ctx = dash.callback_context
#     if ctx.triggered[0]['prop_id'] == 'opportunity-button.n_clicks':
#         production_df = pd.read_json(production_df)
#         production_df = production_df.sort_values([category_filter, margin_column],
#             ascending=False).reset_index(drop=True)
#         stat_df = pd.read_json(stat_df)
#         results = maximize_ebitda(production_df, stat_df, families, descriptors)
#         results[results.columns[3:]] = np.round(results[results.columns[3:]].astype(float))
#         columns=[{"name": i, "id": i} for i in results.columns]
#         return results.to_dict('rows'), columns
# @app.callback(
#     [Output('upload-table', 'data'),
#     Output('upload-table', 'columns'),],
#     [Input('production-df-holding', 'children'),
#      Input('production-df-upload', 'children'),]
# )
# def store_upload_results(df_holding, df_upload):
#     if df_holding is not None:
#
#         production_df = pd.read_json(df_holding)
#     else:
#         production_df = pd.read_json(df_upload)
#     # production_df = production_df.sort_values([category_filter, margin_column], ascending=False).reset_index(drop=True)
#     columns=[{"name": i, "id": i} for i in production_df.columns]
#     return production_df.to_dict('rows'), columns
if __name__ == "__main__":
    app.run_server(debug=True)
