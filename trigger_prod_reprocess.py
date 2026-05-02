import os
import requests
from dotenv import load_dotenv

load_dotenv()

PROD_URL = os.environ.get("PROD_URL", "https://redaxion-web-fastapi-production.up.railway.app")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")

if not ADMIN_SECRET:
    ADMIN_SECRET = input("Ingresa el ADMIN_SECRET de producción: ").strip()

endpoint = f"{PROD_URL}/api/admin/reprocess-from-gcs"

payload = {
    "admin_key": ADMIN_SECRET,
    "orden_id": "33a039ec-51c6-4eb2-93b8-28fd31c7c5ef",
    "gcs_blob_name": "33a039ec-51c6-4eb2-93b8-28fd31c7c5ef_Clase_17._P1_-_Miocardio_y_Electrofisiologia_Cardiaca_.m4a",
    "email_to": "yarineira0311@gmail.com",
    "email_bcc": "admin@redaxiontcp.com,chris.rodval@gmail.com",
    "nombre": "Yarineira",
    "color": "azul elegante",
    "columnas": "una"
}

print(f"Enviando petición a {endpoint}...")
try:
    resp = requests.post(endpoint, data=payload)
    resp.raise_for_status()
    print("✅ ¡Éxito!")
    print(resp.json())
except requests.exceptions.HTTPError as err:
    print(f"❌ Error HTTP: {err}")
    print(f"Respuesta del servidor: {resp.text}")
except Exception as e:
    print(f"❌ Error conectando: {e}")
