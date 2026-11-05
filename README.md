# Monitor Ambiental Yopal – corrección de actualización automática

Aplicación Streamlit conectada al canal público ThingSpeak `3561479`.

## Ejecutar localmente
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Publicar en Streamlit Community Cloud
Repositorio: `AdriNoguera/monitor-ambiental-yopal`
Rama: `main`
Archivo principal: `app.py`

La aplicación consulta la API pública:
`https://api.thingspeak.com/channels/3561479/feeds.json?results=8000`

El tablero se actualiza cada 30 segundos mediante `st.fragment`, sin usar componentes externos de auto-refresh.
