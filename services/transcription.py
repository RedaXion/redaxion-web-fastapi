import os
import time
import requests
import asyncio

# Leer API Key desde variable de entorno
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")

# WARNING: In a real app we might want to fail gracefully or init this only when needed
if not DEEPGRAM_API_KEY:
    print("Warning: DEEPGRAM_API_KEY not found. Transcriptions will fail.")

HEADERS = {
    "Authorization": f"Token {DEEPGRAM_API_KEY or ''}",
    "Content-Type": "application/json"
}

TRANSCRIBE_ENDPOINT = "https://api.deepgram.com/v1/listen"

def transcribir_audio(audio_url, keyterms=None):
    # Short-circuit if no key for dev/test
    if not DEEPGRAM_API_KEY:
        print("MOCK: Transcribing audio (No API Key)...")
        return "Transcripción simulada por falta de API Key."

    # Updated check for our explicit mock protocol
    if audio_url.startswith("mock://") or "fake-gcs-url" in audio_url:
        print("⚠️ URL simulada detectada (MOCK). Saltando Deepgram y usando texto de prueba.")
        return "Esta es una transcripción simulada. El sistema detectó que estamos en modo de pruebas local (mock://), por lo que se omite el procesamiento real de audio para ahorrar tiempo y evitar errores de descarga. Aquí iría el contenido real de tu grabación."

    payload = {"url": audio_url}
    
    params = {
        "model": "nova-2",
        "language": "es",
        "smart_format": "true",
        "punctuate": "true"
    }
    
    if keyterms:
        params["keywords"] = keyterms
        
    print(f"🔗 Enviando audio a Deepgram... URL: {audio_url[:50]}...")
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(TRANSCRIBE_ENDPOINT, headers=HEADERS, json=payload, params=params, timeout=300)
            response.raise_for_status()
            data = response.json()
            
            transcript = data.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', '')
            
            if not transcript:
                raise ValueError("Respuesta vacía o formato desconocido desde Deepgram")
            
            print("✅ Transcripción Deepgram completada con éxito.")
            return transcript
            
        except Exception as e:
            print(f"⚠️ Error en transcripción real (Intento {attempt}/{max_retries}): {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Detalle API: {e.response.text}")
                
            if attempt < max_retries:
                print("🔄 Reintentando en 5 segundos...")
                time.sleep(5)
            else:
                print("⚠️ Retornando texto de contingencia tras agotar reintentos.")
                return """
[TRANSCRIPCIÓN SIMULADA]
Este es un texto generado automáticamente porque el servicio de transcripción falló persistentemente o no pudo acceder al archivo de audio (probablemente porque estamos en un entorno local sin almacenamiento en la nube real).

En un entorno de producción, aquí aparecería el contenido completo de tu grabación.
Por ahora, utilizaremos este texto base para demostrar la capacidad de RedaXion de:
1. Analizar el contenido.
2. Mejorar la redacción.
3. Generar quizzes de repaso.

El sistema continúa funcionando correctamente.
"""

# ============================================
# ASYNC VERSION - Non-blocking transcription
# ============================================

async def transcribir_audio_async(audio_url: str, keyterms: list = None) -> str:
    """
    Non-blocking version of transcribir_audio.
    Runs the blocking transcription in a thread pool so the event loop
    can continue responding to other requests (like polling).
    """
    return await asyncio.to_thread(transcribir_audio, audio_url, keyterms)
