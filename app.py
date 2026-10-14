import streamlit as st
import pandas as pd
import requests
import folium
import plotly.express as px
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from datetime import date, timedelta

# ---------------- PAGE SETTINGS ----------------
st.set_page_config(
    page_title="GreenSite AI",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- DESIGN ----------------
st.markdown("""
<style>
.stApp { background-color: #F4F8F5; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
h1, h2, h3 { color: #174D38; }
[data-testid="stMetric"] {
    background: white; padding: 16px; border-radius: 12px;
    border: 1px solid #DCE9DF;
}
div[data-testid="stMetricValue"] { color: #176B45; }
section[data-testid="stSidebar"] { background-color: #EAF3EC; }
</style>
""", unsafe_allow_html=True)

st.title("🌱 GreenSite AI")
st.markdown("### Wind and Solar Site Suitability Engine")
st.caption("Location-based renewable-energy screening | Historical weather data | SDG 7")

st.info(
    "This is a preliminary screening prototype. Solar and wind values are retrieved "
    "from Open-Meteo historical weather data. Candidate points are generated around "
    "the searched location; they are not verified land parcels. Land, grid and road "
    "scores remain user-editable illustrative assumptions."
)

# ---------------- LOCATION SEARCH ----------------
if "base_location" not in st.session_state:
    st.session_state["base_location"] = {
        "name": "Coimbatore, Tamil Nadu",
        "lat": 11.0168,
        "lon": 76.9558,
    }

st.sidebar.subheader("🌍 Location")
place_name = st.sidebar.text_input(
    "Enter city, district or place in India",
    value=st.session_state["base_location"]["name"],
    key="place_input",
)

if st.sidebar.button("Search Location", key="search_location"):
    if not place_name.strip():
        st.sidebar.error("Please enter a location.")
    else:
        try:
            geolocator = Nominatim(user_agent="GreenSiteAI_Hackathon_Demo")
            location = geolocator.geocode(f"{place_name.strip()}, India", timeout=15)
            if location:
                st.session_state["base_location"] = {
                    "name": location.address,
                    "lat": float(location.latitude),
                    "lon": float(location.longitude),
                }
                st.rerun()
            else:
                st.sidebar.error("Location not found. Try a city or district name.")
        except Exception as exc:
            st.sidebar.error(f"Location search failed: {exc}")

base = st.session_state["base_location"]
st.sidebar.success(f"Selected: {base['name']}")
st.sidebar.caption(f"Latitude: {base['lat']:.5f} | Longitude: {base['lon']:.5f}")

# ---------------- ANALYSIS SETTINGS ----------------
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Analysis Settings")
energy = st.sidebar.selectbox("Choose Energy Type", ["Solar", "Wind"])

st.sidebar.caption("Adjust the relative importance of each factor.")
w1 = st.sidebar.slider("Solar / Wind Resource", 0, 100, 40)
w2 = st.sidebar.slider("Land Suitability", 0, 100, 25)
w3 = st.sidebar.slider("Grid Proximity", 0, 100, 20)
w4 = st.sidebar.slider("Road Connectivity", 0, 100, 15)
weights_raw = [w1, w2, w3, w4]
if sum(weights_raw) == 0:
    st.warning("At least one criterion weight must be greater than zero.")
    st.stop()
weights = [value / sum(weights_raw) for value in weights_raw]

# ---------------- HISTORICAL DATE RANGE ----------------
st.sidebar.markdown("---")
st.sidebar.subheader("📅 Historical Weather Period")
latest_date = date.today() - timedelta(days=5)
default_start = date(max(2017, latest_date.year - 2), 1, 1)
default_end = min(date(latest_date.year - 1, 12, 31), latest_date)
start_date = st.sidebar.date_input(
    "Start date",
    value=default_start,
    min_value=date(2017, 1, 1),
    max_value=latest_date,
)
end_date = st.sidebar.date_input(
    "End date",
    value=default_end,
    min_value=date(2017, 1, 1),
    max_value=latest_date,
)
if start_date > end_date:
    st.sidebar.error("Start date must be on or before end date.")
    st.stop()

# ---------------- COST ASSUMPTIONS ----------------
st.sidebar.markdown("---")
st.sidebar.subheader("💰 Cost Assumptions")
capacity_mw = st.sidebar.number_input(
    "Plant Capacity (MW)", min_value=0.1, max_value=10000.0, value=10.0, step=0.5
)
solar_cost_per_mw = st.sidebar.number_input(
    "Solar Plant Cost (₹ crore/MW)", min_value=0.0, value=4.0, step=0.25
)
wind_cost_per_mw = st.sidebar.number_input(
    "Wind Plant Cost (₹ crore/MW)", min_value=0.0, value=7.0, step=0.25
)
grid_distance_km = st.sidebar.number_input(
    "Estimated Grid Distance (km)", min_value=0.0, value=5.0, step=0.5
)
grid_cost_per_km = st.sidebar.number_input(
    "Grid Connection Cost (₹ crore/km)", min_value=0.0, value=0.15, step=0.05
)

# ---------------- WEATHER API ----------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_weather_data(latitude, longitude, start_iso, end_iso):
    """Retrieve hourly historical weather from Open-Meteo Archive API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_iso,
        "end_date": end_iso,
        "hourly": "shortwave_radiation,wind_speed_10m,wind_speed_100m",
        "timezone": "Asia/Kolkata",
        "wind_speed_unit": "ms",
    }
    response = requests.get(url, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()
    if "hourly" not in payload or not payload["hourly"].get("time"):
        raise ValueError("The API did not return hourly data for this date range.")

    hourly = pd.DataFrame(payload["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"])
    hourly = hourly.rename(columns={
        "time": "Time",
        "shortwave_radiation": "Solar radiation (W/m²)",
        "wind_speed_10m": "Wind at 10 m (m/s)",
        "wind_speed_100m": "Wind at 100 m (m/s)",
    })
    hourly["Date"] = hourly["Time"].dt.date

    # Open-Meteo shortwave radiation is an hourly mean in W/m².
    # Summing hourly mean values and dividing by 1000 estimates kWh/m²/day.
    daily_solar = (
        hourly.groupby("Date")["Solar radiation (W/m²)"]
        .sum(min_count=1) / 1000.0
    )
    daily_wind = hourly.groupby("Date")[
        ["Wind at 10 m (m/s)", "Wind at 100 m (m/s)"]
    ].mean()
    daily = pd.concat([
        daily_solar.rename("Solar energy (kWh/m²/day)"),
        daily_wind,
    ], axis=1).reset_index()
    return hourly, daily

def scale_score(value, low, high):
    """Map a measured resource value to a transparent 0–100 screening score."""
    if pd.isna(value):
        return 0.0
    return round(max(0.0, min(100.0, (float(value) - low) / (high - low) * 100)), 1)

# ---------------- CANDIDATE SITES ----------------
# Offsets create nearby screening points only; these are not real land boundaries.
site_offsets = [
    ("Site A", 0.000, 0.000, 85, 90, 80),
    ("Site B", 0.045, 0.000, 80, 70, 90),
    ("Site C", -0.045, 0.000, 50, 85, 70),
    ("Site D", 0.000, 0.045, 40, 60, 60),
]

st.subheader("📡 Real Historical Weather Data")
st.write(
    f"Selected location: **{base['name']}**  \n"
    f"Period: **{start_date.isoformat()} to {end_date.isoformat()}**"
)

# Fetch each candidate coordinate independently. Open-Meteo may use the same
# underlying weather grid cell for nearby points, so values can be identical.
candidate_records = []
daily_selected = None
hourly_selected = None
errors = []

with st.spinner("Fetching historical solar and wind data for candidate points..."):
    for site_name, lat_off, lon_off, land_score, grid_score, road_score in site_offsets:
        lat = base["lat"] + lat_off
        lon = base["lon"] + lon_off
        try:
            hourly_data, daily_data = get_weather_data(
                round(lat, 5), round(lon, 5),
                start_date.isoformat(), end_date.isoformat()
            )
            solar_avg = daily_data["Solar energy (kWh/m²/day)"].mean()
            wind10_avg = daily_data["Wind at 10 m (m/s)"].mean()
            wind100_avg = daily_data["Wind at 100 m (m/s)"].mean()
            solar_score = scale_score(solar_avg, 2.0, 7.0)
            # Screening threshold only; not a turbine-bankability standard.
            wind_score = scale_score(wind100_avg, 3.0, 10.0)
            candidate_records.append({
                "Site": site_name,
                "Latitude": lat,
                "Longitude": lon,
                "Solar average (kWh/m²/day)": solar_avg,
                "Wind at 10 m average (m/s)": wind10_avg,
                "Wind at 100 m average (m/s)": wind100_avg,
                "Solar resource score": solar_score,
                "Wind resource score": wind_score,
                "Land score (assumed)": land_score,
                "Grid score (assumed)": grid_score,
                "Road score (assumed)": road_score,
            })
            if site_name == "Site A":
                daily_selected = daily_data.copy()
                hourly_selected = hourly_data.copy()
        except Exception as exc:
            errors.append(f"{site_name}: {exc}")

if errors:
    st.warning(
        "Some candidate points could not be loaded. Check your internet connection "
        "or try a shorter date range.\n\n" + "\n".join(errors)
    )

if not candidate_records:
    st.error(
        "No historical weather data was retrieved. Check internet access, the selected "
        "dates, and the Open-Meteo API status, then rerun the app."
    )
    st.stop()

df = pd.DataFrame(candidate_records)
resource_col = "Solar resource score" if energy == "Solar" else "Wind resource score"
df["Score"] = (
    df[resource_col] * weights[0]
    + df["Land score (assumed)"] * weights[1]
    + df["Grid score (assumed)"] * weights[2]
    + df["Road score (assumed)"] * weights[3]
).round(1)
df = df.sort_values("Score", ascending=False).reset_index(drop=True)
df["Rank"] = range(1, len(df) + 1)
best = df.iloc[0]

# ---------------- DASHBOARD SUMMARY ----------------
st.markdown("---")
st.subheader("📊 Dashboard Overview")
solar_mean = df["Solar average (kWh/m²/day)"].mean()
wind10_mean = df["Wind at 10 m average (m/s)"].mean()
wind100_mean = df["Wind at 100 m average (m/s)"].mean()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Average Solar Energy", f"{solar_mean:.2f} kWh/m²/day")
m2.metric("Wind at 10 m", f"{wind10_mean:.2f} m/s")
m3.metric("Wind at 100 m", f"{wind100_mean:.2f} m/s")
m4.metric("Top Candidate", best["Site"], f"{best['Score']}/100")
st.caption("Weather figures are modelled historical data, not on-site measurements.")

# ---------------- WEATHER CHARTS ----------------
if daily_selected is not None:
    st.markdown("---")
    st.subheader("📈 Historical Trends at Selected Coordinates (Site A)")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown("**Daily solar energy**")
        st.line_chart(
            daily_selected.set_index("Date")["Solar energy (kWh/m²/day)"]
        )
    with chart_right:
        st.markdown("**Daily mean wind speed**")
        st.line_chart(
            daily_selected.set_index("Date")[
                ["Wind at 10 m (m/s)", "Wind at 100 m (m/s)"]
            ]
        )
    with st.expander("View daily weather table"):
        st.dataframe(daily_selected, use_container_width=True, hide_index=True)

# ---------------- RANKING AND COMPARISON ----------------
st.markdown("---")
left, right = st.columns([1.1, 1])
with left:
    st.subheader("🏆 Site Rankings")
    display_cols = [
        "Rank", "Site", "Score", "Solar average (kWh/m²/day)",
        "Wind at 100 m average (m/s)", "Land score (assumed)",
        "Grid score (assumed)", "Road score (assumed)",
    ]
    st.dataframe(
        df[display_cols].style.format({
            "Score": "{:.1f}",
            "Solar average (kWh/m²/day)": "{:.2f}",
            "Wind at 100 m average (m/s)": "{:.2f}",
        }),
        use_container_width=True,
        hide_index=True,
    )
with right:
    st.subheader("📊 Suitability Comparison")
    chart = px.bar(
        df.sort_values("Score"),
        x="Score", y="Site", orientation="h", text="Score",
        color="Score", color_continuous_scale=["#F2C14E", "#77BFA3", "#176B45"],
        range_color=[0, 100], labels={"Score": "Suitability Score"},
    )
    chart.update_layout(
        height=330, margin=dict(l=10, r=10, t=20, b=20),
        coloraxis_showscale=False, plot_bgcolor="white", paper_bgcolor="white",
        xaxis_range=[0, 100],
    )
    st.plotly_chart(chart, use_container_width=True)

# ---------------- INTERACTIVE MAP ----------------
st.markdown("---")
st.subheader("🗺️ Interactive Candidate Map")
st.caption("Green marker = searched location. Candidate points are generated nearby and are not verified land parcels.")
try:
    map_obj = folium.Map(
        location=[base["lat"], base["lon"]],
        zoom_start=10,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.Marker(
        [base["lat"], base["lon"]],
        tooltip="Searched location",
        popup=folium.Popup(
            f"<b>{base['name']}</b><br>Latitude: {base['lat']:.5f}<br>Longitude: {base['lon']:.5f}",
            max_width=300,
        ),
        icon=folium.Icon(color="green", icon="info-sign"),
    ).add_to(map_obj)

    for _, row in df.iterrows():
        marker_color = "green" if row["Rank"] == 1 else ("orange" if row["Score"] >= 60 else "red")
        popup_text = (
            f"<b>{row['Site']}</b><br>Rank: {int(row['Rank'])}"
            f"<br>Suitability score: {row['Score']}/100"
            f"<br>Solar: {row['Solar average (kWh/m²/day)']:.2f} kWh/m²/day"
            f"<br>Wind at 100 m: {row['Wind at 100 m average (m/s)']:.2f} m/s"
            f"<br>Lat/Lon: {row['Latitude']:.5f}, {row['Longitude']:.5f}"
        )
        folium.CircleMarker(
            [row["Latitude"], row["Longitude"]],
            radius=9 if row["Rank"] == 1 else 7,
            color=marker_color, fill=True, fill_color=marker_color,
            fill_opacity=0.85, tooltip=f"{row['Site']} — score {row['Score']}",
            popup=folium.Popup(popup_text, max_width=300),
        ).add_to(map_obj)

    bounds = [[base["lat"], base["lon"]]] + [
        [float(row["Latitude"]), float(row["Longitude"])] for _, row in df.iterrows()
    ]
    map_obj.fit_bounds(bounds, padding=(25, 25))
    st_folium(map_obj, height=460, use_container_width=True, key="greensite_map")
except Exception as exc:
    st.error(f"Map error: {exc}")

# ---------------- COST ESTIMATION ----------------
st.markdown("---")
st.subheader("💰 Project Cost Estimation")
st.caption("These are user-entered assumptions, not vendor quotations or a bankable project estimate.")
solar_plant_cost = capacity_mw * solar_cost_per_mw
wind_plant_cost = capacity_mw * wind_cost_per_mw
grid_connection_cost = grid_distance_km * grid_cost_per_km
solar_total = solar_plant_cost + grid_connection_cost
wind_total = wind_plant_cost + grid_connection_cost

cost1, cost2 = st.columns(2)
with cost1:
    st.markdown("#### ☀️ Solar Project")
    st.metric("Estimated Total Cost", f"₹{solar_total:,.2f} crore")
    st.write(f"Plant cost: ₹{solar_plant_cost:,.2f} crore")
    st.write(f"Grid connection: ₹{grid_connection_cost:,.2f} crore")
with cost2:
    st.markdown("#### 🌬️ Wind Project")
    st.metric("Estimated Total Cost", f"₹{wind_total:,.2f} crore")
    st.write(f"Plant cost: ₹{wind_plant_cost:,.2f} crore")
    st.write(f"Grid connection: ₹{grid_connection_cost:,.2f} crore")

cost_comparison = pd.DataFrame({
    "Energy Type": ["Solar", "Wind"],
    "Capacity (MW)": [capacity_mw, capacity_mw],
    "Plant Cost (₹ crore)": [solar_plant_cost, wind_plant_cost],
    "Grid Cost (₹ crore)": [grid_connection_cost, grid_connection_cost],
    "Estimated Total (₹ crore)": [solar_total, wind_total],
})
st.dataframe(cost_comparison, use_container_width=True, hide_index=True)

# ---------------- RECOMMENDATION ----------------
st.markdown("---")
st.subheader("💡 Preliminary Recommendation")
st.write(
    f"Under the selected **{energy.lower()}** weighting, **{best['Site']}** ranks first "
    f"with a score of **{best['Score']}/100**."
)
st.write(
    f"- Historical solar energy average: {best['Solar average (kWh/m²/day)']:.2f} kWh/m²/day\n"
    f"- Historical mean wind speed at 10 m: {best['Wind at 10 m average (m/s)']:.2f} m/s\n"
    f"- Historical mean wind speed at 100 m: {best['Wind at 100 m average (m/s)']:.2f} m/s\n"
    f"- Assumed land score: {best['Land score (assumed)']}/100\n"
    f"- Assumed grid score: {best['Grid score (assumed)']}/100\n"
    f"- Assumed road score: {best['Road score (assumed)']}/100"
)
st.warning(
    "This ranking is for early-stage comparison only. Confirm land ownership and zoning, "
    "protected-area restrictions, grid capacity and connection route, road access, terrain, "
    "environmental constraints, and on-site resource measurements before selecting a real site."
)

# ---------------- DOWNLOADS ----------------
st.markdown("---")
st.subheader("📥 Download Reports")
weather_csv = daily_selected.to_csv(index=False).encode("utf-8") if daily_selected is not None else b""
st.download_button(
    "Download Site Ranking CSV",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name="greensite_site_ranking.csv",
    mime="text/csv",
)
st.download_button(
    "Download Historical Weather CSV",
    data=weather_csv,
    file_name="greensite_historical_weather.csv",
    mime="text/csv",
    disabled=daily_selected is None,
)
st.download_button(
    "Download Cost Estimate CSV",
    data=cost_comparison.to_csv(index=False).encode("utf-8"),
    file_name="greensite_cost_estimate.csv",
    mime="text/csv",
)

st.markdown("---")
st.caption(
    "Weather source: Open-Meteo Historical Weather API (ERA5 / related reanalysis products). "
    "Geocoding: OpenStreetMap Nominatim. GreenSite AI | Hackathon prototype."
)
st.caption(
    "Resource score mapping used in this prototype: solar 2–7 kWh/m²/day and wind "
    "3–10 m/s at 100 m mapped to 0–100. These are transparent screening thresholds, "
    "not official project-approval criteria."
)
