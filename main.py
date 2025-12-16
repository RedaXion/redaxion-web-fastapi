import os
import uuid
import asyncio
from typing import Optional

from fastapi import FastAPI, UploadFile, Form, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import mercadopago
from google.cloud import storage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="RedaXion API")

# CORS configuration (allow all for now, restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration ---
MERCADOPAGO_ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
# Fixed price for now as per requirements
PRICE_AMOUNT = 3000
PRICE_CURRENCY = "CLP"

# --- Clients ---
# Initialize Mercado Pago SDK
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

# Initialize GCS Client
# Assumes GOOGLE_APPLICATION_CREDENTIALS is set or environment has implicit access
try:
    storage_client = storage.Client()
except Exception as e:
    print(f"Warning: Could not initialize GCS client: {e}")
    storage_client = None

# --- Logic ---


# --- Services ---
from services.transcription import transcribir_audio
from services.text_processing import procesar_txt_con_chatgpt
from services.formatting import guardar_como_docx, guardar_quiz_como_docx, convert_to_pdf
from services.quiz_generation import generar_quiz_desde_docx
from services.delivery import subir_archivo_a_drive, enviar_correo_con_adjuntos

async def procesar_audio_y_documentos(orden_id: str, audio_public_url: str = None, user_metadata: dict = None):
    """
    Orchestrates the entire RedaXion pipeline.
    """
    print(f"[{orden_id}] Iniciando flujo RedaXion...")
    
    # Defaults in case metadata is missing
    user_metadata = user_metadata or {}
    color = user_metadata.get("color", "amatista")
    columnas = user_metadata.get("columnas", "una")
    correo_cliente = user_metadata.get("email")
    # For now, simplistic check or default to what legacy code did
    es_solo_texto = "solo texto" in user_metadata.get("tipo_entrega", "").lower()

    try:
        # 1. Transcribe Audio
        # If we didn't receive a public URL, we might need to rely on the internally uploaded GCS URL
        # audio_public_url should be passed from the webhook or deduced
        if not audio_public_url and user_metadata.get("gcs_audio_url"):
             # Convert gs:// to https://storage.googleapis.com if public or signed
             # For now, we assume the service can handle the GCS URI or we utilize the public input
             audio_public_url = user_metadata.get("gcs_audio_url")
        
        texto_transcrito = transcribir_audio(audio_public_url)
        print(f"[{orden_id}] Transcripción completada.")
        
        # Save raw text
        path_txt = f"/tmp/{orden_id}.txt"
        with open(path_txt, "w") as f:
            f.write(texto_transcrito)
        
        # 2. Process with AI (ChatGPT / Napkin)
        texto_procesado = procesar_txt_con_chatgpt(path_txt)
        print(f"[{orden_id}] Texto procesado con IA.")
        
        # 3. Generate Main DOCX
        nombre_tcp = f"RedaXion - Nº{orden_id}.docx"
        path_docx = f"/tmp/{nombre_tcp}"
        guardar_como_docx(texto_procesado, path_docx, color=color, columnas=columnas)
        
        # 4. Generate Main PDF
        path_pdf = convert_to_pdf(path_docx)
        
        # 5. Generate Quiz
        preguntas_quiz = generar_quiz_desde_docx(path_docx)
        nombre_quiz = f"RedaQuiz - Nº{orden_id}.docx"
        path_quiz = f"/tmp/{nombre_quiz}"
        guardar_quiz_como_docx(preguntas_quiz, path_quiz, color=color, columnas=columnas)
        path_quiz_pdf = convert_to_pdf(path_quiz)
        
        # 6. Upload to Drive (and GCS if needed for persistence)
        # Legacy code uploaded to Drive. We keep that logic in 'subir_archivo_a_drive'
        subir_archivo_a_drive(path_docx, nombre_tcp, orden_id)
        if path_pdf: 
            subir_archivo_a_drive(path_pdf, nombre_tcp.replace(".docx", ".pdf"), orden_id)
        subir_archivo_a_drive(path_quiz, nombre_quiz, orden_id)
        if path_quiz_pdf:
             subir_archivo_a_drive(path_quiz_pdf, nombre_quiz.replace(".docx", ".pdf"), orden_id)
             
        print(f"[{orden_id}] Archivos generados y subidos.")
        
        # 7. Notify Client
        if correo_cliente:
            asunto = f"Tu transcripción Nº{orden_id} ya está lista ✅"
            cuerpo = "Hola, adjuntamos tus archivos..."
            adjuntos = [path_docx, path_quiz]
            if path_pdf: adjuntos.append(path_pdf)
            if path_quiz_pdf: adjuntos.append(path_quiz_pdf)
            
            enviar_correo_con_adjuntos(correo_cliente, asunto, cuerpo, adjuntos)
            print(f"[{orden_id}] Correo enviado a {correo_cliente}.")
            
    except Exception as e:
        print(f"[{orden_id}] Error en el procesamiento: {e}")
        # traceback.print_exc() (verify if imported or available)

async def upload_to_gcs(file: UploadFile, destination_blob_name: str) -> str:
    """Uploads a file to the bucket."""
    if not storage_client or not GCS_BUCKET_NAME:
        print("GCS not configured, skipping upload.")
        return "https://fake-gcs-url.com/simulated_upload"
    
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        
        # Read file content and upload
        # Warning: For very large files, this might need chunked upload or signed URLs
        content = await file.read()
        blob.upload_from_string(content, content_type=file.content_type)
        
        print(f"File uploaded to {destination_blob_name}.")
        return f"gs://{GCS_BUCKET_NAME}/{destination_blob_name}"
    except Exception as e:
        print(f"Failed to upload to GCS: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload audio: {str(e)}")

# --- Endpoints ---

@app.post("/api/orden")
async def crear_orden(
    nombre: str = Form(...),
    correo: str = Form(...),
    color: str = Form(...),
    columnas: str = Form(...),
    tipo_entrega: str = Form(...),
    audio_file: UploadFile = Form(...)
):
    """
    Recibe los datos del formulario y el audio.
    1. Sube audio a GCS.
    2. Genera ID de orden.
    3. Crea preferencia de pago en Mercado Pago.
    4. Retorna URL de pago.
    """
    # 1. Generate unique Order ID
    orden_id = str(uuid.uuid4())
    print(f"Nueva orden recibida: {orden_id} - Cliente: {nombre}")

    # 2. Upload Audio to GCS
    # Structure: uploads/{orden_id}/{filename}
    file_extension = audio_file.filename.split('.')[-1]
    gcs_path = f"uploads/{orden_id}/audio.{file_extension}"
    
    # Upload (async/await to not block)
    gcs_url = await upload_to_gcs(audio_file, gcs_path)
    
    # 3. Create Mercado Pago Preference
    if not MERCADOPAGO_ACCESS_TOKEN:
         raise HTTPException(status_code=500, detail="Mercado Pago token not configured.")

    preference_data = {
        "items": [
            {
                "id": "redaxion-service",
                "title": "Servicio RedaXion (Transcripción + Documento)",
                "quantity": 1,
                "currency_id": PRICE_CURRENCY,
                "unit_price": PRICE_AMOUNT
            }
        ],
        "payer": {
            "name": nombre,
            "email": correo
        },
        "metadata": {
            "orden_id": orden_id,
            "color": color,
            "columnas": columnas,
            "tipo_entrega": tipo_entrega,
            "gcs_audio_url": gcs_url
        },
        "external_reference": orden_id,
        "back_urls": {
            "success": "https://tusitio.com/exito", # Replace with actual frontend URLs
            "failure": "https://tusitio.com/fallo",
            "pending": "https://tusitio.com/pendiente"
        },
        "auto_return": "approved"
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        
        # Prioritize Sandbox URL for testing
        checkout_url = preference.get("sandbox_init_point") or preference.get("init_point")
        
        if not checkout_url:
            print(f"Error: No checkout URL in response. Full response: {preference}")

        return {
            "orden_id": orden_id,
            "checkout_url": checkout_url
        }
        
    except Exception as e:
        print(f"Error creating MP preference: {e}")
        raise HTTPException(status_code=500, detail="Error generating payment preference")


@app.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Recibe notificaciones de Mercado Pago.
    Si topic=payment y status=approved, inicia el procesamiento.
    """
    # Mercado Pago sends query params: id, topic (or type)
    # Sometimes data is in the body. We check query params primarily for 'topic' and 'id'.
    try:
        query_params = request.query_params
        topic = query_params.get("topic") or query_params.get("type")
        resource_id = query_params.get("id") or query_params.get("data.id")

        if topic == "payment":
            # Verify payment status with MP API
            payment_info = sdk.payment().get(resource_id)
            payment = payment_info["response"]
            
            status = payment.get("status")
            status_detail = payment.get("status_detail")
            
            print(f"Webhook recibido. Payment ID: {resource_id}, Status: {status}")

            if status == "approved":
                # Extract metadata or external_reference
                external_ref = payment.get("external_reference")
                metadata = payment.get("metadata", {})
                
                orden_id = external_ref or metadata.get("orden_id")
                
                if orden_id:
                    print(f"Pago aprobado para orden {orden_id}. Iniciando procesamiento...")
                    # Trigger processing in background to reply 200 OK fast
                    background_tasks.add_task(
                        procesar_audio_y_documentos, 
                        orden_id, 
                        audio_public_url=metadata.get("gcs_audio_url"),
                        user_metadata=metadata
                    )
                else:
                    print("Pago aprobado pero no se encontró orden_id.")

        return JSONResponse(status_code=200, content={"status": "received"})

    except Exception as e:
        print(f"Error processing webhook: {e}")
        # Always return 200 to MP to stop retries, unless it's a critical error we want to retry
        return JSONResponse(status_code=200, content={"status": "error", "error": str(e)})

@app.get("/")
def home():
    return {"message": "RedaXion API is running"}
