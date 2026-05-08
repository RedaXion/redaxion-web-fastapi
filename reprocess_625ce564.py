"""
Script de reproceso para la orden 625ce564 de Martina Javiera Henríquez Puebla.
El resultado se envía SOLO a chris.rodval@gmail.com para revisión.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

PROD_URL = "https://redaxion-web-fastapi-production.up.railway.app"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")

if not ADMIN_SECRET:
    ADMIN_SECRET = input("Ingresa el ADMIN_SECRET de producción: ").strip()

ORDEN_ID    = "625ce564-f834-4ddf-a13b-b34e2aae8f4c"
BLOB_NAME   = "625ce564-f834-4ddf-a13b-b34e2aae8f4c_Fisiopato_260402.mp4"
EMAIL_ADMIN = "chris.rodval@gmail.com"  # Solo al admin para revisión

payload = {
    "admin_key":    ADMIN_SECRET,
    "orden_id":     ORDEN_ID,
    "gcs_blob_name": BLOB_NAME,
    "email_to":     EMAIL_ADMIN,
    "email_bcc":    "",              # Sin BCC, solo va al admin
    "nombre":       "Martina",       # Nombre en el saludo del correo
    "color":        "azul pastel",
    "columnas":     "una",
}

endpoint = f"{PROD_URL}/api/admin/reprocess-from-gcs"
print(f"\n🔧 Reprocesando orden {ORDEN_ID}...")
print(f"📤 Resultado irá SOLO a: {EMAIL_ADMIN} (para revisión antes de enviar a la cliente)")
print(f"🎵 Blob: {BLOB_NAME}\n")

try:
    resp = requests.post(endpoint, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    print("✅ ¡Reproceso iniciado con éxito!")
    print(f"   Mensaje: {data.get('message')}")
    print(f"   URL preview: {data.get('fresh_url_preview', 'N/A')}")
    print(f"\n⏳ El procesamiento toma ~3-5 minutos.")
    print(f"📧 Recibirás el correo en: {EMAIL_ADMIN}")
except requests.exceptions.HTTPError as err:
    print(f"❌ Error HTTP {resp.status_code}: {err}")
    print(f"   Respuesta: {resp.text}")
except Exception as e:
    print(f"❌ Error de conexión: {e}")
