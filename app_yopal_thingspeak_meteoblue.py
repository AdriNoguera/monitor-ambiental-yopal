import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

CHANNEL_ID = "3561479"
API_URL = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
MAX_RECORDS = 8000
REFRESH_SECONDS = 30


# meteoblue: pronóstico horario para Yopal, Casanare.
METEOBLUE_URL = "https://my.meteoblue.com/packages/basic-1h"
METEOBLUE_LAT = 5.33573
METEOBLUE_LON = -72.3939
METEOBLUE_ALTITUDE = 426
METEOBLUE_CACHE_SECONDS = 12 * 60 * 60  # Dos consultas al día como máximo por caché activa.


@st.cache_data(ttl=METEOBLUE_CACHE_SECONDS, show_spinner=False)
def get_meteoblue_forecast(api_key):
    """Consulta el paquete basic-1h y devuelve el pronóstico en hora de Colombia."""
    params = {
        "apikey": api_key,
        "lat": METEOBLUE_LAT,
        "lon": METEOBLUE_LON,
        "asl": METEOBLUE_ALTITUDE,
        "tz": "America/Bogota",
        "temperatureUnit": "C",
        "windSpeedUnit": "km/h",
        "precipitationUnit": "metric",
        "format": "json",
    }
    response = requests.get(METEOBLUE_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    # El paquete horario se entrega normalmente en el bloque data_1h.
    block = payload.get("data_1h", {})
    if not isinstance(block, dict):
        raise ValueError("La respuesta de meteoblue no contiene el bloque data_1h esperado.")

    times = block.get("time", [])
    if not times:
        raise ValueError("meteoblue no devolvió horas de pronóstico.")

    forecast = pd.DataFrame({"Fecha y hora": pd.to_datetime(times, errors="coerce")})
    if forecast["Fecha y hora"].dt.tz is None:
        forecast["Fecha y hora"] = forecast["Fecha y hora"].dt.tz_localize("America/Bogota")
    else:
        forecast["Fecha y hora"] = forecast["Fecha y hora"].dt.tz_convert("America/Bogota")

    variable_map = {
        "temperature": "Temperatura pronosticada (°C)",
        "relativehumidity": "Humedad pronosticada (%)",
        "precipitation": "Precipitación pronosticada (mm)",
        "precipitation_probability": "Probabilidad de precipitación (%)",
        "windspeed": "Velocidad del viento (km/h)",
        "winddirection": "Dirección del viento (°)",
        "felttemperature": "Sensación térmica (°C)",
        "sealevelpressure": "Presión a nivel del mar (hPa)",
    }
    for api_field, display_name in variable_map.items():
        values = block.get(api_field)
        if values is not None and len(values) == len(forecast):
            forecast[display_name] = pd.to_numeric(pd.Series(values), errors="coerce")

    forecast = forecast.dropna(subset=["Fecha y hora"]).sort_values("Fecha y hora")
    if forecast.empty:
        raise ValueError("No se encontraron horas válidas en el pronóstico.")
    return forecast, payload.get("metadata", payload.get("meta", {}))

st.set_page_config(page_title="Monitor Ambiental Yopal", page_icon="🌤️", layout="wide")
st.title("🌤️ Monitor Ambiental – Yopal, Casanare")
st.caption("Panel conectado al canal público de ThingSpeak · Actualización automática cada 30 segundos")

@st.cache_data(ttl=20, show_spinner=False)
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
    df = df.rename(columns={
        "entry_id": "Registro",
        "field1": "Iluminancia (Lux)",
        "field2": "Temperatura (°C)",
        "field3": "Humedad (%)",
    })
    for col in ["Iluminancia (Lux)", "Temperatura (°C)", "Humedad (%)"]:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return channel, df.dropna(subset=["Fecha y hora"])

# st.fragment actualiza el contenido sin insertar un componente externo en el navegador.
# Esto evita el componente de auto-refresh que puede provocar conflictos del DOM.
@st.fragment(run_every=f"{REFRESH_SECONDS}s")
def live_dashboard():
    try:
        channel, df = get_channel_data()
    except requests.RequestException:
        st.error("No fue posible consultar ThingSpeak. Comprueba tu conexión a Internet y que el canal siga siendo público.")
        st.caption(f"Dirección consultada: {API_URL}?results={MAX_RECORDS}")
        if st.button("Reintentar ahora"):
            get_channel_data.clear()
            st.rerun()
        return
    except Exception as exc:
        st.error(f"No fue posible interpretar la respuesta del canal: {exc}")
        return

    if df.empty:
        st.warning("El canal no contiene registros disponibles.")
        return

    latest = df.sort_values("Fecha y hora").iloc[-1]
    last_time = latest["Fecha y hora"]
    now = datetime.now(ZoneInfo("America/Bogota"))
    age_seconds = max(0, int((now - last_time.to_pydatetime()).total_seconds()))

    if age_seconds <= 180:
        st.success(f"Canal accesible · Último dato hace {age_seconds} segundos")
    else:
        st.warning(f"Canal accesible, pero el último registro tiene {age_seconds // 60} minutos de antigüedad. Comprueba el envío de datos de los sensores.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Iluminancia actual", f'{latest["Iluminancia (Lux)"]:.2f} Lux' if pd.notna(latest["Iluminancia (Lux)"]) else "Sin dato")
    c2.metric("Temperatura actual", f'{latest["Temperatura (°C)"]:.2f} °C' if pd.notna(latest["Temperatura (°C)"]) else "Sin dato")
    c3.metric("Humedad actual", f'{latest["Humedad (%)"]:.2f} %' if pd.notna(latest["Humedad (%)"]) else "Sin dato")
    c4.metric("Registros cargados", f"{len(df):,}")

    st.caption(f'Última medición: {last_time.strftime("%d/%m/%Y %H:%M:%S")} (hora de Colombia) · Canal: {CHANNEL_ID}')

    # Fuente meteorológica externa: pronóstico, separado de las mediciones del ESP32.
    st.divider()
    st.subheader("Pronóstico meteorológico para Yopal · meteoblue")
    st.caption(
        "Pronóstico estimado por meteoblue para las coordenadas configuradas de Yopal. "
        "Estos valores no son mediciones del sensor ESP32 ni reemplazan los datos de ThingSpeak."
    )

    try:
        meteoblue_key = st.secrets.get("METEOBLUE_API_KEY", "")
    except Exception:
        meteoblue_key = ""

    if not meteoblue_key:
        st.info(
            "Para activar el pronóstico, agrega METEOBLUE_API_KEY en "
            "Manage app → Settings → Secrets de Streamlit Community Cloud."
        )
    else:
        try:
            with st.spinner("Consultando el pronóstico de meteoblue..."):
                forecast, forecast_meta = get_meteoblue_forecast(meteoblue_key)

            forecast_now = forecast.iloc[0]
            f1, f2, f3, f4 = st.columns(4)
            temp_col = "Temperatura pronosticada (°C)"
            humidity_col = "Humedad pronosticada (%)"
            rain_col = "Precipitación pronosticada (mm)"
            wind_col = "Velocidad del viento (km/h)"

            f1.metric(
                "Temperatura próxima hora",
                f'{forecast_now[temp_col]:.1f} °C' if temp_col in forecast and pd.notna(forecast_now.get(temp_col)) else "Sin dato",
            )
            f2.metric(
                "Humedad próxima hora",
                f'{forecast_now[humidity_col]:.0f} %' if humidity_col in forecast and pd.notna(forecast_now.get(humidity_col)) else "Sin dato",
            )
            f3.metric(
                "Precipitación próxima hora",
                f'{forecast_now[rain_col]:.1f} mm' if rain_col in forecast and pd.notna(forecast_now.get(rain_col)) else "Sin dato",
            )
            f4.metric(
                "Viento próximo horario",
                f'{forecast_now[wind_col]:.1f} km/h' if wind_col in forecast and pd.notna(forecast_now.get(wind_col)) else "Sin dato",
            )

            forecast_view = forecast.head(48).copy()
            st.markdown("**Evolución pronosticada para las próximas 48 horas**")
            forecast_tabs = st.tabs(["Temperatura", "Humedad", "Precipitación", "Viento"])
            forecast_charts = [
                (temp_col, "Temperatura pronosticada (°C)"),
                (humidity_col, "Humedad pronosticada (%)"),
                (rain_col, "Precipitación pronosticada (mm)"),
                (wind_col, "Velocidad del viento (km/h)"),
            ]
            for tab, (column, chart_title) in zip(forecast_tabs, forecast_charts):
                with tab:
                    if column in forecast_view.columns:
                        fig_forecast = px.line(
                            forecast_view,
                            x="Fecha y hora",
                            y=column,
                            markers=True,
                            title=chart_title,
                        )
                        st.plotly_chart(fig_forecast, use_container_width=True)
                    else:
                        st.caption("Esta variable no está disponible en la respuesta del paquete contratado.")

            with st.expander("Tabla del pronóstico horario"):
                st.dataframe(forecast_view, use_container_width=True, hide_index=True)
                st.download_button(
                    "⬇️ Descargar pronóstico (CSV)",
                    forecast_view.to_csv(index=False).encode("utf-8-sig"),
                    "pronostico_meteoblue_yopal.csv",
                    "text/csv",
                )

            st.caption(
                "Fuente: meteoblue Forecast API · paquete basic-1h · "
                "pronóstico almacenado en caché durante 12 horas para controlar el consumo de créditos."
            )
        except requests.RequestException as exc:
            st.warning(f"No fue posible consultar meteoblue en este momento: {exc}")
        except (ValueError, KeyError, TypeError) as exc:
            st.warning(f"La respuesta de meteoblue no pudo interpretarse: {exc}")

    st.divider()
    st.sidebar.header("Configuración")
    st.sidebar.write(f"**Canal:** {CHANNEL_ID}")
    st.sidebar.write(f"**Actualización automática:** cada {REFRESH_SECONDS} segundos")
    start, end = df["Fecha y hora"].min().date(), df["Fecha y hora"].max().date()
    selected = st.sidebar.date_input("Periodo de consulta", value=(start, end), min_value=start, max_value=end)

    view = df.copy()
    if isinstance(selected, (tuple, list)) and len(selected) == 2:
        d1, d2 = selected
        view = view[(view["Fecha y hora"].dt.date >= d1) & (view["Fecha y hora"].dt.date <= d2)]

    if view.empty:
        st.warning("No hay registros para el periodo seleccionado.")
        return

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
        st.caption("Valores normalizados entre 0 y 1 para comparar tendencias; no representan magnitudes físicas.")
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
    st.download_button(
        "⬇️ Descargar histórico visible (CSV)",
        table.to_csv(index=False).encode("utf-8-sig"),
        "historico_yopal.csv",
        "text/csv",
    )

    with st.expander("Información del canal"):
        st.write("Nombre:", channel.get("name", "No informado"))
        st.write("Descripción:", channel.get("description", "No informada"))
        st.write("Campos publicados:", {f"field{i}": channel.get(f"field{i}") for i in range(1, 4)})
        st.write("Último ID de entrada:", channel.get("last_entry_id", "No informado"))

    st.caption("Fuente: ThingSpeak, canal público 3561479. La aplicación consulta la API de lectura y no modifica el canal.")

live_dashboard()
