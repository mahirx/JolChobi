import streamlit as st
import folium

st.set_page_config(page_title="JolChobi Step 2", layout="wide")
st.title("JolChobi • Step 2: Base Map")

# Sunamganj approx center
center_lat, center_lon = 25.0, 91.4

m = folium.Map(location=[center_lat, center_lon], zoom_start=9, control_scale=True, tiles="OpenStreetMap")
st.components.v1.html(m._repr_html_(), height=600)
st.write("You should see a base map centered on Sunamganj.")
