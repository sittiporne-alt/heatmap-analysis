import json
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import pydeck as pdk

st.set_page_config(layout="wide")

# =========================
# HEADER
# =========================
st.markdown("# ⚡ EV Charging  Dashboard")
st.caption("Analytics Report")

# =========================
# LOAD LOG DATA
# =========================
with open("pugev.status_logs_v2.json", "r", encoding="utf-8") as f:
    data = json.load(f)

df = pd.json_normalize(data)

# =========================
# LOAD STATION MASTER
# =========================
with open("station_202602182357.json", "r", encoding="utf-8") as f:
    station_data = json.load(f)

station_df = pd.json_normalize(station_data["station"])

# parse name_obj
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
# DAILY AVERAGE BY WEEKDAY
# =========================
st.markdown("## 📅 Average Charging by Weekday (Mon–Sun)")

# เรียงลำดับวัน
weekday_order = [
    "Monday","Tuesday","Wednesday",
    "Thursday","Friday","Saturday","Sunday"
]

# คำนวณจำนวน session ต่อวันจริงก่อน
daily_counts = (
    filtered_df
    .groupby(["weekday_name", "date"])
    .size()
    .reset_index(name="sessions")
)

# ค่าเฉลี่ย session ต่อวันของแต่ละ weekday
weekday_avg_sessions = (
    daily_counts
    .groupby("weekday_name")["sessions"]
    .mean()
    .reindex(weekday_order)
)

# ค่าเฉลี่ย duration ต่อ weekday
weekday_avg_duration = (
    filtered_df
    .groupby("weekday_name")["duration_hour"]
    .mean()
    .reindex(weekday_order)
)

# ค่าเฉลี่ย power ต่อ weekday
weekday_avg_power = (
    filtered_df
    .groupby("weekday_name")["effective_power"]
    .mean()
    .reindex(weekday_order)
)

# รวมเป็น DataFrame
weekday_summary_df = pd.DataFrame({
    "Avg Sessions / Day": weekday_avg_sessions,
    "Avg Duration (hrs)": weekday_avg_duration,
    "Avg Power (kW)": weekday_avg_power
}).round(2)

# แสดงตาราง
st.dataframe(weekday_summary_df)

st.divider()

# =========================
# WEEKDAY CHART
# =========================
st.markdown("### 📊 Average Sessions per Day by Weekday")

fig_weekday = plt.figure(figsize=(10,4))
weekday_avg_sessions.plot(kind="bar")
plt.title("Average Sessions per Day")
plt.xticks(rotation=45)
plt.grid(axis="y", linestyle="--", alpha=0.3)
st.pyplot(fig_weekday)


# =========================
# STATION SUMMARY
# =========================
st.markdown("## 🏢 Station Summary")

station_summary = (
    filtered_df
    .groupby("station_name")
    .agg(
        sessions=("station_id", "count"),
        avg_duration=("duration_hour", "mean"),
        avg_power=("effective_power", "mean")
    )
    .sort_values("sessions", ascending=False)
)

st.dataframe(station_summary)

st.divider()

# =========================
# CHART GRID (เหมือน UI เดิม)
# =========================
st.markdown("## 📊 Charging Analysis")

col1, col2 = st.columns(2)

with col1:
    fig1 = plt.figure(figsize=(8,4))
    filtered_df.groupby("start_hour").size().plot(kind="bar")
    plt.title("Sessions by Hour")
    plt.grid(axis="y", linestyle="--", alpha=0.3)
    st.pyplot(fig1)

with col2:
    fig2 = plt.figure(figsize=(8,4))
    filtered_df.groupby("region").size().plot(kind="bar")
    plt.title("Sessions by Region")
    plt.grid(axis="y", linestyle="--", alpha=0.3)
    st.pyplot(fig2)

st.divider()

# =========================
# ADVANCED HEATMAP (DENSITY + STATION)
# =========================

# รวมจำนวน session ต่อพิกัด
map_df = (
    filtered_df
    .groupby(["station_name", "latitude", "longitude"])
    .size()
    .reset_index(name="sessions")
)

# =========================
# HEATMAP
# =========================
st.markdown("## 🔥 Charging Activity Heat Map")

heatmap_data = filtered_df[["latitude", "longitude"]]

layer = pdk.Layer(
    "HeatmapLayer",
    data=heatmap_data,
    get_position=["longitude", "latitude"],
    radiusPixels=60,
)

view_state = pdk.ViewState(
    latitude=filtered_df["latitude"].mean(),
    longitude=filtered_df["longitude"].mean(),
    zoom=5,
)

deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
)

st.pydeck_chart(deck)



# =========================
# SESSION LIST PER STATION
# =========================
st.markdown("## 📋 Charging Sessions Detail")

st.dataframe(
    filtered_df[
        ["station_name","source","start_time","duration_hour","effective_power","price"]
    ].sort_values("start_time", ascending=False)
)