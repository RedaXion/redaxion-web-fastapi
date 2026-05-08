import os
import sys
import asyncio
import requests
import time

# Add root to sys.path
sys.path.append("/Users/christopherrodriguez/~:Code:RedaXionWeb/redaxion-web-fastapi")

import main
from main import procesar_audio_y_documentos
from services.database import update_order_status

# Custom transcribe function to use local file without polling (sync)
async def custom_transcribe_async(audio_url, cliente_email, cliente_nombre, orden_id):
    print("\n[MODO LOCAL] Iniciando transcripción subiendo el archivo local (Modo Síncrono)...")
    local_path = "/Users/christopherrodriguez/Downloads/353004c5-b06b-4c43-aad8-b82373602964_clase.mp3"
    
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"No se encontró el archivo en {local_path}")
        
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    DEEPGRAM_BATCH_ENDPOINT = "https://api.deepgram.com/v1/listen"
    
    DEEPGRAM_HEADERS = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/octet-stream"
    }
    
    params = {
        "model":         "nova-2",
        "language":      "es",
        "smart_format":  "true",
        "punctuate":     "true",
        "diarize":       "false",
        # Quitamos callback_method=polling para ver si ese es el problema con archivos locales
    }
    
    print(f"🚀 [Deepgram Local] Subiendo archivo y esperando respuesta: {local_path}...")
    
    with open(local_path, "rb") as f:
        r = requests.post(
            DEEPGRAM_BATCH_ENDPOINT,
            headers=DEEPGRAM_HEADERS,
            params=params,
            data=f,
            timeout=600  # 10 minutos de timeout para esperar el resultado
        )
    
    r.raise_for_status()
    response_data = r.json()
    
    # Extract transcript
    transcript = (
        response_data
        .get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("transcript", "")
    )
    
    if transcript:
        words = len(transcript.split())
        print(f"✅ [Deepgram Local] Transcripción completada: {words} palabras.")
        return transcript
    else:
        print(f"⚠️ [Deepgram Local] Respuesta inesperada: {response_data}")
        raise RuntimeError("Deepgram no retornó transcript.")

# Monkey-patch main directly
main.transcribir_audio_async = custom_transcribe_async

async def main_run():
    orden_id = "353004c5-b06b-4c43-aad8-b82373602964"
    audio_url = "dummy_url_not_used_because_of_monkey_patch"
    
    user_metadata = {
        "email": "chris.rodval@gmail.com",
        "client": "Fabian Pardo (Test Local Sync)",
        "color": "amatista",
        "columnas": "una"
    }
    
    print(f"Iniciando reprocesamiento LOCAL para la orden {orden_id}...")
    print(f"El correo se enviará a: {user_metadata['email']}")
    
    try:
        # Update status to pending to clear any previous error state
        update_order_status(orden_id, "pending")
        
        # Run the pipeline
        await procesar_audio_y_documentos(
            orden_id=orden_id,
            audio_public_url=audio_url,
            user_metadata=user_metadata
        )
        print("✅ Reprocesamiento completado.")
    except Exception as e:
        print(f"❌ Error durante el reprocesamiento: {e}")

if __name__ == "__main__":
    asyncio.run(main_run())
