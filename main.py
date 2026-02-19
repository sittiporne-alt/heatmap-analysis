import json
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import pydeck as pdk

st.set_page_config(layout="wide")

# =========================
# HEADER
# =========================
st.markdown("# ⚡ EV Charging Executive Dashboard")
st.caption("OneCharge Analytics Report")

# =========================
# LOAD DATA
# =========================
with open("pugev.status_logs_v2.json", "r", encoding="utf-8") as f:
    data = json.load(f)

df = pd.json_normalize(data)

# =========================
# CLEAN DATA
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
# DAILY AVERAGE (Mon–Sun)
# =========================
st.markdown("## 📅 Daily Average (Mon–Sun)")

daily_summary = filtered_df.groupby("date").agg(
    total_sessions=("station_id", "count"),
    avg_duration=("duration_hour", "mean")
)

avg_sessions_per_day = daily_summary["total_sessions"].mean()
avg_duration_per_day = daily_summary["avg_duration"].mean()

colA, colB = st.columns(2)
colA.metric("Average Sessions per Day", round(avg_sessions_per_day, 2))
colB.metric("Average Duration per Day (hrs)", round(avg_duration_per_day, 2))

st.divider()

# =========================
# WEEKDAY ANALYSIS
# =========================
st.markdown("## 📊 Sessions by Weekday")

weekday_summary = (
    filtered_df
    .groupby("weekday_name")
    .size()
    .reindex([
        "Monday","Tuesday","Wednesday",
        "Thursday","Friday","Saturday","Sunday"
    ])
)

fig_weekday = plt.figure(figsize=(10,4))
weekday_summary.plot(kind="bar")
plt.xticks(rotation=45)
plt.grid(axis="y", linestyle="--", alpha=0.3)
plt.title("Sessions by Weekday")
st.pyplot(fig_weekday)

st.divider()

# =========================
# CHART GRID
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

col3, col4 = st.columns(2)

with col3:
    fig3 = plt.figure(figsize=(8,4))
    filtered_df.groupby("type")["effective_power"].mean().plot(kind="bar")
    plt.title("Avg Effective Power by Type")
    plt.grid(axis="y", linestyle="--", alpha=0.3)
    st.pyplot(fig3)

with col4:
    fig4 = plt.figure(figsize=(8,4))
    filtered_df.groupby("price").size().plot(kind="bar")
    plt.title("Price Distribution")
    plt.grid(axis="y", linestyle="--", alpha=0.3)
    st.pyplot(fig4)

st.divider()

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
