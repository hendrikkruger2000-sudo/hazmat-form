import dash
from dash import dcc, html, Input, Output, State
import pandas as pd
import plotly.graph_objects as go

# 🔗 Sample data
df = pd.DataFrame([{
    "id": 1,
    "reference": "JP045236",
    "date": "2025-10-14",
    "shipment_type": "export",  # or "local"
    "collection_time": "10:30",
    "collection_address": "46 Champion Street",
    "collection_contact": "Hendrik 0647573692",
    "delivery_address": "52 Malcolm Moodie Crescent",
    "delivery_contact": "Lyndon 0647573694",
    "delivery_type": "NORMAL",
    "quoted": "NO",
    "document_file": "C:\\HAZMATCOLLECTIONSYSTEMTEST\\UPLOADS\\DOCS\\1706249287_CONFIRMATION_OF_EMPLOYMENT.PDF",
    "collection_lat": -26.2,
    "collection_lon": 28.3,
    "delivery_lat": -26.25,
    "delivery_lon": 28.35,
    "collection_driver_name": "",
    "collection_driver_contact": "",
    "collection_vehicle_id": "",
    "collection_status": "collection_pending",
    "delivery_driver_name": "",
    "delivery_driver_contact": "",
    "delivery_vehicle_id": "",
    "delivery_status": "delivery_pending"
}])

# ⚙️ Dash app
app = dash.Dash(__name__)
app.title = "Hazmat Global Support Services"

app.layout = html.Div([
    html.H2("Filter by Delivery Type"),
    dcc.Dropdown(
        options=[{"label": i, "value": i} for i in df["delivery_type"].unique()],
        value=None,
        id="delivery-filter",
        placeholder="Select delivery type"
    ),

    html.Div(id="collection-card"),

    html.H2("Map of Collection"),
    dcc.Graph(id="map"),

    html.H2("Assign Collection Driver"),
    html.Div([
        dcc.Input(id="collection-driver-name", type="text", placeholder="Name"),
        dcc.Input(id="collection-driver-contact", type="text", placeholder="Contact"),
        dcc.Input(id="collection-vehicle-id", type="text", placeholder="Vehicle ID"),
        html.Button("Assign Collection Driver", id="assign-collection", n_clicks=0)
    ], style={"marginBottom": "40px"})

])

@app.callback(
    Output("collection-card", "children"),
    Output("map", "figure"),
    Output("delivery-driver-section", "children"),
    Input("delivery-filter", "value")
)
def update_dashboard(delivery_type):
    filtered = df.copy()
    if delivery_type:
        filtered = filtered[filtered["delivery_type"] == delivery_type]

    if filtered.empty:
        return html.Div("No records found"), go.Figure(), html.Div()

    row = filtered.iloc[0]

    delivery_info = html.Div("Export shipment – no delivery driver assigned.") if row["shipment_type"] == "export" else html.Div([
        html.H2("Assign Delivery Driver"),
        dcc.Input(id="delivery-driver-name", type="text", placeholder="Name"),
        dcc.Input(id="delivery-driver-contact", type="text", placeholder="Contact"),
        dcc.Input(id="delivery-vehicle-id", type="text", placeholder="Vehicle ID"),
        dcc.Dropdown(
            options=[
                {"label": "Pending", "value": "delivery_pending"},
                {"label": "En Route", "value": "delivery_en_route"},
                {"label": "Delivered", "value": "delivered"}
            ],
            id="delivery-status",
            placeholder="Delivery Status"
        ),
        html.Button("Assign Delivery Driver", id="assign-delivery", n_clicks=0)
    ])

    card = html.Div([
        html.H4(f"Reference: {row['reference']}"),
        html.P(f"Shipment Type: {row['shipment_type']}"),
        html.P(f"Collection: {row['collection_address']} ({row['collection_contact']})"),
        html.P(f"Collection Driver: {row['collection_driver_name']} ({row['collection_driver_contact']})"),
        html.P(f"Collection Vehicle: {row['collection_vehicle_id']}"),
        html.P(f"Collection Status: {row['collection_status']}"),
        html.P(f"Quoted: {row['quoted']}"),
        html.P(f"Document: {row['document_file']}"),
        html.P(f"Delivery: {row['delivery_address']} ({row['delivery_contact']})") if row["shipment_type"] == "local" else html.P("Delivery: N/A (Export)"),
        html.P(f"Delivery Driver: {row['delivery_driver_name']} ({row['delivery_driver_contact']})") if row["shipment_type"] == "local" else None,
        html.P(f"Delivery Vehicle: {row['delivery_vehicle_id']}") if row["shipment_type"] == "local" else None,
        html.P(f"Delivery Status: {row['delivery_status']}") if row["shipment_type"] == "local" else None
    ])

    fig = go.Figure()
    fig.add_trace(go.Scattermapbox(
        lat=[row["collection_lat"]],
        lon=[row["collection_lon"]],
        mode="markers",
        marker=dict(size=12, color="green"),
        text=["Collection"]
    ))
    if row["shipment_type"] == "local":
        fig.add_trace(go.Scattermapbox(
            lat=[row["delivery_lat"]],
            lon=[row["delivery_lon"]],
            mode="markers+lines",
            marker=dict(size=12, color="blue"),
            text=["Delivery"]
        ))
    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox=dict(center={"lat": -26.23, "lon": 28.33}, zoom=10),
        margin={"r":0,"t":0,"l":0,"b":0}
    )

    return card, fig, delivery_info

@app.callback(
    Output("collection-card", "children", allow_duplicate=True),
    Input("assign-collection", "n_clicks"),
    State("collection-driver-name", "value"),
    State("collection-driver-contact", "value"),
    State("collection-vehicle-id", "value"),
    prevent_initial_call=True
)
def assign_collection_driver(n_clicks, name, contact, vehicle):
    df.loc[0, "collection_driver_name"] = name or ""
    df.loc[0, "collection_driver_contact"] = contact or ""
    df.loc[0, "collection_vehicle_id"] = vehicle or ""

    row = df.iloc[0]
    return html.Div([
        html.H4(f"Reference: {row['reference']}"),
        html.P(f"Shipment Type: {row['shipment_type']}"),
        html.P(f"Collection: {row['collection_address']} ({row['collection_contact']})"),
        html.P(f"Collection Driver: {row['collection_driver_name']} ({row['collection_driver_contact']})"),
        html.P(f"Collection Vehicle: {row['collection_vehicle_id']}"),
        html.Div([
            html.Span("Collection Status: "),
            html.Span(
                row["collection_status"].replace("_", " ").title(),
                style={
                    "backgroundColor": {
                        "collection_pending": "#999",
                        "collection_en_route": "#f90",
                        "collected": "#0f0"
                    }.get(row["collection_status"], "#333"),
                    "color": "#000",
                    "padding": "4px 8px",
                    "marginLeft": "10px",
                    "borderRadius": "4px",
                    "fontWeight": "bold"
                }
            )
        ]),
        html.P(f"Quoted: {row['quoted']}"),
        html.P(f"Document: {row['document_file']}")
        # Add delivery fields if shipment_type == "local"
    ])

@app.callback(
    Output("collection-card", "children", allow_duplicate=True),
    Input("assign-delivery", "n_clicks"),
    State("delivery-driver-name", "value"),
    State("delivery-driver-contact", "value"),
    State("delivery-vehicle-id", "value"),
    State("delivery-status", "value"),
    prevent_initial_call=True
)
def assign_delivery_driver(n_clicks, name, contact, vehicle, status):
    df.loc[0, "delivery_driver_name"] = name or ""
    df.loc[0, "delivery_driver_contact"] = contact or ""
    df.loc[0, "delivery_vehicle_id"] = vehicle or ""
    df.loc[0, "delivery_status"] = status or "delivery_pending"

    row = df.iloc[0]
    return html.Div([
        html.H4(f"Reference: {row['reference']}"),
        html.P(f"Shipment Type: {row['shipment_type']}"),
        html.P(f"Collection: {row['collection_address']} ({row['collection_contact']})"),
        html.P(f"Collection Driver: {row['collection_driver_name']} ({row['collection_driver_contact']})"),
        html.P(f"Collection Vehicle: {row['collection_vehicle_id']}"),
        html.Div([
            html.Span("Collection Status: "),
            html.Span(
                row["collection_status"].replace("_", " ").title(),
                style={
                    "backgroundColor": {
                        "collection_pending": "#999",
                        "collection_en_route": "#f90",
                        "collected": "#0f0"
                    }.get(row["collection_status"], "#333"),
                    "color": "#000",
                    "padding": "4px 8px",
                    "marginLeft": "10px",
                    "borderRadius": "4px",
                    "fontWeight": "bold"
                }
            )
        ]),
        html.P(f"Quoted: {row['quoted']}"),
        html.P(f"Document: {row['document_file']}"),
        html.P(f"Delivery: {row['delivery_address']} ({row['delivery_contact']})") if row["shipment_type"] == "local" else html.P("Delivery: N/A (Export)"),
        html.P(f"Delivery Driver: {row['delivery_driver_name']} ({row['delivery_driver_contact']})") if row["shipment_type"] == "local" else None,
        html.P(f"Delivery Vehicle: {row['delivery_vehicle_id']}") if row["shipment_type"] == "local" else None,
        html.P(f"Delivery Status: {row['delivery_status']}") if row["shipment_type"] == "local" else None
    ])