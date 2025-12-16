import os
import time
import requests

# Leer API Key desde variable de entorno
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY")

# WARNING: In a real app we might want to fail gracefully or init this only when needed
if not ASSEMBLYAI_API_KEY:
    # raise ValueError("No se encontró la variable de entorno ASSEMBLYAI_API_KEY")
    print("Warning: ASSEMBLYAI_API_KEY not found. Transcriptions will fail.")

HEADERS = {
    "authorization": ASSEMBLYAI_API_KEY or "",
    "content-type": "application/json"
}

TRANSCRIBE_ENDPOINT = "https://api.assemblyai.com/v2/transcript"

def enviar_a_transcripcion(audio_url):
    payload = {
        "audio_url": audio_url,
        "language_code": "es"  # forzar español
    }
    response = requests.post(TRANSCRIBE_ENDPOINT, headers=HEADERS, json=payload)
    response.raise_for_status()
    transcript_id = response.json()["id"]
    print("📤 Transcripción enviada. ID:", transcript_id)
    return transcript_id

def esperar_resultado_transcripcion(transcript_id, espera=10):
    status_url = f"{TRANSCRIBE_ENDPOINT}/{transcript_id}"
    print("⏳ Esperando transcripción...")

    while True:
        response = requests.get(status_url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        if data["status"] == "completed":
            print("✅ Transcripción completada.")
            return data["text"]
        elif data["status"] == "error":
            raise Exception(f"❌ Error en transcripción: {data['error']}")

        print("⌛ Aún transcribiendo... esperando", espera, "segundos.")
        time.sleep(espera)

def transcribir_audio(audio_url):
    # Short-circuit if no key for dev/test
    if not ASSEMBLYAI_API_KEY:
        print("MOCK: Transcribing audio (No API Key)...")
        return "Transcripción simulada por falta de API Key."

    if "fake-gcs-url" in audio_url:
        print("⚠️ URL simulada detectada. Retornando transcripción de prueba para continuar flujo.")
        return "Esta es una transcripción simulada. El audio no pudo subirse a GCS por falta de credenciales, pero el sistema continúa para probar la redacción y generación de imágenes. Aquí iría el contenido real del audio."

    transcript_id = enviar_a_transcripcion(audio_url)
    texto = esperar_resultado_transcripcion(transcript_id)
    return texto
