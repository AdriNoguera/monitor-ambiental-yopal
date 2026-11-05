# Monitor Ambiental Yopal – conexión ThingSpeak

Aplicación Streamlit conectada al canal público ThingSpeak `3561479`.

## Ejecutar localmente
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Publicar
1. Sube `app.py` y `requirements.txt` a un repositorio de GitHub.
2. Entra a https://share.streamlit.io/ y conecta GitHub.
3. Crea una aplicación seleccionando el repositorio y `app.py`.
4. Pulsa Deploy.

La aplicación consulta `https://api.thingspeak.com/channels/3561479/feeds.json?results=8000`.
Como el canal es público, no requiere Read API Key. El panel ejecuta una nueva consulta automáticamente cada 30 segundos y usa una caché de 30 segundos.

## Nota
La aplicación interpreta field1 como iluminancia, field2 como temperatura y field3 como humedad, conforme a las etiquetas del CSV suministrado. Contrasta estos nombres con la configuración real del canal ThingSpeak.
