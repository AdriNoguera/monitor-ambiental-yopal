import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from zoneinfo import ZoneInfo

CHANNEL_ID = "3561479"
API_URL = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
POLL_SECONDS = 30
MAX_RECORDS = 8000

st.set_page_config(page_title="Monitor Ambiental Yopal", page_icon="🌤️", layout="wide")

st.title("🌤️ Monitor Ambiental – Yopal, Casanare")
st.caption("Panel conectado al canal público de ThingSpeak · Actualización automática cada 30 segundos")

# Provoca una nueva consulta periódica sin que el usuario tenga que recargar manualmente.
st_autorefresh(interval=30_000, key="thingspeak_refresh")

@st.cache_data(ttl=POLL_SECONDS, show_spinner=False)
def get_channel_data():
    response = requests.get(API_URL, params={"results": MAX_RECORDS}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    channel = payload.get("channel", {})
    feeds = payload.get("feeds", [])
    if not feeds:
        return channel, pd.DataFrame()
    df = pd.DataFrame(feeds)
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    df["Fecha y hora"] = df["created_at"].dt.tz_convert("America/Bogota")
    mapping = {
        "field1": channel.get("field1") or "Iluminancia (Lux)",
        "field2": channel.get("field2") or "Temperatura (°C)",
        "field3": channel.get("field3") or "Humedad (%)",
    }
    # Mantener nombres de campo descriptivos esperados por el tablero
    df = df.rename(columns={
        "entry_id": "Registro",
        "field1": "Iluminancia (Lux)",
        "field2": "Temperatura (°C)",
        "field3": "Humedad (%)",
    })
    for col in ["Iluminancia (Lux)", "Temperatura (°C)", "Humedad (%)"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = pd.NA
    return channel, df.dropna(subset=["Fecha y hora"])

try:
    channel, df = get_channel_data()
except requests.RequestException as exc:
    st.error("No fue posible consultar ThingSpeak en este momento.")
    st.code(str(exc))
    st.info("Verifica que el canal sea público y que ThingSpeak esté disponible. La aplicación volverá a consultar al recargar.")
    st.stop()
except Exception as exc:
    st.error(f"No fue posible interpretar la respuesta del canal: {exc}")
    st.stop()

if df.empty:
    st.warning("El canal no contiene registros disponibles.")
    st.stop()

latest = df.sort_values("Fecha y hora").iloc[-1]
last_time = latest["Fecha y hora"]
now = datetime.now(ZoneInfo("America/Bogota"))
age_seconds = max(0, int((now - last_time.to_pydatetime()).total_seconds()))
if age_seconds <= 180:
    st.success(f"Conexión con ThingSpeak activa · Último dato hace {age_seconds} segundos")
else:
    st.warning(f"Canal accesible, pero el último registro tiene {age_seconds // 60} minutos de antigüedad. Comprueba los sensores o el envío de datos.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Iluminancia actual", f'{latest["Iluminancia (Lux)"]:.2f} Lux' if pd.notna(latest["Iluminancia (Lux)"]) else "Sin dato")
c2.metric("Temperatura actual", f'{latest["Temperatura (°C)"]:.2f} °C' if pd.notna(latest["Temperatura (°C)"]) else "Sin dato")
c3.metric("Humedad actual", f'{latest["Humedad (%)"]:.2f} %' if pd.notna(latest["Humedad (%)"]) else "Sin dato")
c4.metric("Registros cargados", f"{len(df):,}")

st.caption(f'Última medición: {last_time.strftime("%d/%m/%Y %H:%M:%S")} (hora de Colombia) · Canal: {CHANNEL_ID}')

st.sidebar.header("Configuración")
st.sidebar.write(f"**Canal:** {CHANNEL_ID}")
st.sidebar.write(f"**Actualización:** cada {POLL_SECONDS} segundos al consultar la página.")
start = df["Fecha y hora"].min().date()
end = df["Fecha y hora"].max().date()
selected = st.sidebar.date_input("Periodo de consulta", value=(start, end), min_value=start, max_value=end)
view = df.copy()
if isinstance(selected, (tuple, list)) and len(selected) == 2:
    d1, d2 = selected
    view = view[(view["Fecha y hora"].dt.date >= d1) & (view["Fecha y hora"].dt.date <= d2)]

st.subheader("Evolución de las variables")
t1, t2, t3, t4 = st.tabs(["Iluminancia", "Temperatura", "Humedad", "Comparación"])
with t1:
    fig = px.line(view, x="Fecha y hora", y="Iluminancia (Lux)", markers=True, title="Iluminancia")
    st.plotly_chart(fig, use_container_width=True)
with t2:
    fig = px.line(view, x="Fecha y hora", y="Temperatura (°C)", markers=True, title="Temperatura")
    st.plotly_chart(fig, use_container_width=True)
with t3:
    fig = px.line(view, x="Fecha y hora", y="Humedad (%)", markers=True, title="Humedad")
    st.plotly_chart(fig, use_container_width=True)
with t4:
    st.caption("Valores normalizados entre 0 y 1 para comparar tendencias, no magnitudes físicas.")
    norm = view[["Fecha y hora"]].copy()
    for col in ["Iluminancia (Lux)", "Temperatura (°C)", "Humedad (%)"]:
        lo, hi = view[col].min(), view[col].max()
        norm[col] = 0 if pd.isna(lo) or pd.isna(hi) or hi == lo else (view[col] - lo) / (hi - lo)
    long = norm.melt(id_vars="Fecha y hora", var_name="Variable", value_name="Valor normalizado")
    fig = px.line(long, x="Fecha y hora", y="Valor normalizado", color="Variable")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Historial de mediciones")
table = view[["Registro", "Fecha y hora", "Iluminancia (Lux)", "Temperatura (°C)", "Humedad (%)"]].sort_values("Fecha y hora", ascending=False)
st.dataframe(table, use_container_width=True, hide_index=True)
st.download_button("⬇️ Descargar histórico visible (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
                   "historico_yopal.csv", "text/csv")

with st.expander("Información del canal"):
    st.write("Nombre:", channel.get("name", "No informado"))
    st.write("Descripción:", channel.get("description", "No informada"))
    st.write("Campos publicados:", {f"field{i}": channel.get(f"field{i}") for i in range(1, 4)})
    st.write("Último ID de entrada:", channel.get("last_entry_id", "No informado"))

st.divider()
st.caption("Fuente: ThingSpeak, canal público 3561479. La aplicación consulta la API de lectura; no modifica el canal.")
st.button("🔄 Consultar ahora", on_click=st.cache_data.clear)
