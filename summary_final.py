import json
import requests
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import pydeck as pdk

st.set_page_config(layout="wide")

# =========================
# S3 URL CONFIG
# =========================
LOG_URL = "https://website-onecharge.s3.ap-southeast-1.amazonaws.com/analysis/pugev.status_logs_v2.json"
STATION_URL = "https://website-onecharge.s3.ap-southeast-1.amazonaws.com/analysis/station_202602182357.json"

# =========================
# CACHE LOAD FUNCTIONS
# =========================
@st.cache_data(show_spinner=True)
def load_log_data():
    response = requests.get(LOG_URL)
    return response.json()

@st.cache_data(show_spinner=True)
def load_station_data():
    response = requests.get(STATION_URL)
    return response.json()

# =========================
# HEADER
# =========================
st.markdown("# ⚡ EV Charging Dashboard")
st.caption("Analytics Report")

# =========================
# LOAD DATA FROM S3
# =========================
data = load_log_data()
df = pd.json_normalize(data)

station_data = load_station_data()
station_df = pd.json_normalize(station_data["station"])

# =========================
# PARSE STATION NAME
# =========================
station_df["name_parsed"] = station_df["name_obj"].apply(json.loads)
station_df["station_name"] = station_df["name_parsed"].apply(
    lambda x: x.get("th") if x.get("th") else x.get("en")
)

station_df = station_df[["id", "source", "station_name"]]
station_df = station_df.rename(columns={"id": "station_id"})

# =========================
# CLEAN LOG DATA
# =========================
df["start_time"] = pd.to_datetime(df["start_charging_time.$date"]).dt.tz_localize(None)
df["end_time"] = pd.to_datetime(df["end_charging_time.$date"]).dt.tz_localize(None)

df["duration_hour"] = (
    (df["end_time"] - df["start_time"])
    .dt.total_seconds() / 3600
)

df["longitude"] = df["location.coordinates"].apply(lambda x: x[0])
df["latitude"] = df["location.coordinates"].apply(lambda x: x[1])

df["estimate_power"] = df["estimate_power"].astype(float)
df["efficiency"] = df["efficiency"].astype(float)
df["effective_power"] = df["estimate_power"] * df["efficiency"]

df["start_hour"] = df["start_time"].dt.hour
df["date"] = df["start_time"].dt.date
df["weekday_name"] = df["start_time"].dt.day_name()

# merge station name
df = df.merge(
    station_df,
    on=["station_id", "source"],
    how="left"
)

df["station_name"] = df["station_name"].fillna(
    df["station_id"].astype(str)
)

def region(lat):
    if lat > 17:
        return "North"
    elif lat > 13:
        return "Central"
    else:
        return "South"

df["region"] = df["latitude"].apply(region)

# =========================
# SIDEBAR FILTER
# =========================
st.sidebar.header("🔍 Filter Panel")

providers = sorted(df["source"].unique())
selected_provider = st.sidebar.multiselect(
    "Provider",
    providers,
    default=providers
)

stations = sorted(df["station_name"].unique())
selected_station = st.sidebar.multiselect(
    "Station",
    stations,
    default=stations
)

date_range = st.sidebar.date_input(
    "Date Range",
    [df["start_time"].min(), df["start_time"].max()]
)

hour_range = st.sidebar.slider("Hour Range", 0, 23, (0, 23))

selected_region = st.sidebar.multiselect(
    "Region",
    df["region"].unique(),
    default=df["region"].unique()
)

# =========================
# APPLY FILTER
# =========================
filtered_df = df.copy()

filtered_df = filtered_df[
    filtered_df["source"].isin(selected_provider)
]

filtered_df = filtered_df[
    filtered_df["station_name"].isin(selected_station)
]

if len(date_range) == 2:
    filtered_df = filtered_df[
        (filtered_df["start_time"] >= pd.to_datetime(date_range[0])) &
        (filtered_df["start_time"] <= pd.to_datetime(date_range[1]))
    ]

filtered_df = filtered_df[
    (filtered_df["start_hour"] >= hour_range[0]) &
    (filtered_df["start_hour"] <= hour_range[1])
]

filtered_df = filtered_df[
    filtered_df["region"].isin(selected_region)
]

if filtered_df.empty:
    st.warning("No data available for selected filters")
    st.stop()

# =========================
# KPI SECTION
# =========================
st.markdown("## 📈 Performance Overview")

k1, k2, k3, k4 = st.columns(4)

k1.metric("Total Sessions", len(filtered_df))
k2.metric("Avg Duration (hrs)", round(filtered_df["duration_hour"].mean(), 2))
k3.metric("Avg Effective Power (kW)", round(filtered_df["effective_power"].mean(), 2))
k4.metric("Max Power (kW)", round(filtered_df["effective_power"].max(), 2))

st.divider()

# =========================
# WEEKDAY AVERAGE
# =========================
st.markdown("## 📅 Average Charging by Weekday (Mon–Sun)")

weekday_order = [
    "Monday","Tuesday","Wednesday",
    "Thursday","Friday","Saturday","Sunday"
]

daily_counts = (
    filtered_df
    .groupby(["weekday_name", "date"])
    .size()
    .reset_index(name="sessions")
)

weekday_avg_sessions = (
    daily_counts
    .groupby("weekday_name")["sessions"]
    .mean()
    .reindex(weekday_order)
)

weekday_avg_duration = (
    filtered_df
    .groupby("weekday_name")["duration_hour"]
    .mean()
    .reindex(weekday_order)
)

weekday_avg_power = (
    filtered_df
    .groupby("weekday_name")["effective_power"]
    .mean()
    .reindex(weekday_order)
)

weekday_summary_df = pd.DataFrame({
    "Avg Sessions / Day": weekday_avg_sessions,
    "Avg Duration (hrs)": weekday_avg_duration,
    "Avg Power (kW)": weekday_avg_power
}).round(2)

st.dataframe(weekday_summary_df)

st.divider()

# =========================
# SAFE HEATMAP VERSION
# =========================
st.markdown("## 🔥 Charging Activity Heat Map")

# เตรียมข้อมูล map แบบปลอดภัย
map_df = filtered_df[["latitude", "longitude"]].dropna().copy()

# แปลงเป็น python float จริง ๆ
map_df["latitude"] = map_df["latitude"].apply(lambda x: float(x))
map_df["longitude"] = map_df["longitude"].apply(lambda x: float(x))

# แปลงเป็น list dict (JSON safe)
map_data = map_df.to_dict(orient="records")

if len(map_data) > 0:

    heat_layer = pdk.Layer(
        "HeatmapLayer",
        data=map_data,
        get_position=["longitude", "latitude"],
        radiusPixels=60,
    )

    view_state = pdk.ViewState(
        latitude=float(map_df["latitude"].mean()),
        longitude=float(map_df["longitude"].mean()),
        zoom=6,
    )

    deck = pdk.Deck(
        layers=[heat_layer],
        initial_view_state=view_state,
    )

    st.pydeck_chart(deck)

else:
    st.warning("No map data available")



# =========================
# SESSION LIST
# =========================
st.markdown("## 📋 Charging Sessions Detail")

st.dataframe(
    filtered_df[
        ["station_name","source","start_time","duration_hour","effective_power","price"]
    ].sort_values("start_time", ascending=False)
)
