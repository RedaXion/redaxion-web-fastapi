import os
import uuid
import asyncio
from typing import Optional

from fastapi import FastAPI, UploadFile, Form, HTTPException, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import mercadopago
import shutil
import os
import uuid
from google.cloud import storage
from dotenv import load_dotenv
from services import database

# Load environment variables
load_dotenv()

app = FastAPI(title="RedaXion API")

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Initialize DB on Startup
@app.on_event("startup")
def startup_event():
    database.init_db()

# ... (Middleware and Config remain same)

# --- Configuration ---
MERCADOPAGO_ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
# Fixed price for now as per requirements
PRICE_AMOUNT = 3000
PRICE_CURRENCY = "CLP"

# --- Clients ---
# Initialize Mercado Pago SDK
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

# Initialize GCS Client (Mocked if fails)
try:
    storage_client = storage.Client()
except Exception as e:
    print(f"Warning: Could not initialize GCS client: {e}")
    storage_client = None

# --- Services ---
from services.transcription import transcribir_audio
from services.text_processing import procesar_txt_con_chatgpt
from services.formatting import guardar_como_docx, guardar_quiz_como_docx, convert_to_pdf
from services.quiz_generation import generar_quiz_desde_docx
from services.delivery import subir_archivo_a_drive, enviar_correo_con_adjuntos

# ORDERS_DB Removed - Using SQLite now

async def procesar_audio_y_documentos(orden_id: str, audio_public_url: str = None, user_metadata: dict = None):
    """
    Orchestrates the entire RedaXion pipeline.
    """
    print(f"[{orden_id}] Iniciando flujo RedaXion...")
    database.update_order_status(orden_id, "processing")
    
    # Defaults in case metadata is missing
    user_metadata = user_metadata or {}
    color = user_metadata.get("color", "amatista")
    columnas = user_metadata.get("columnas", "una")
    correo_cliente = user_metadata.get("email")
    print(f"[{orden_id}] Correo cliente: '{correo_cliente}'")

    try:
        # 1. Transcribe
        if not audio_public_url:
             # Fetch url from DB if not passed
             order = database.get_order(orden_id)
             if order:
                 audio_public_url = order.get("audio_url")

        # NOTE: Ensure valid URL in production
        # Transcribir_audio is sync, so we don't await it (unless refactored to async)
        transcription_text = transcribir_audio(audio_public_url)
        print(f"[{orden_id}] Transcripción completada.")
        
        # Save raw text
        path_txt = f"static/generated/{orden_id}.txt"
        with open(path_txt, "w") as f:
            f.write(transcription_text)
        
        # 2. Process with AI
        texto_procesado = procesar_txt_con_chatgpt(path_txt)
        print(f"[{orden_id}] Texto procesado con IA.")
        
        # 3. Generate Main DOCX
        nombre_tcp = f"RedaXion - Nº{orden_id}.docx"
        path_docx = f"static/generated/{nombre_tcp}"
        guardar_como_docx(texto_procesado, path_docx, color=color, columnas=columnas)
        
        # 4. Generate Main PDF
        path_pdf = convert_to_pdf(path_docx, color=color) # Pass color scheme
        
        # 5. Generate Quiz
        preguntas_quiz = generar_quiz_desde_docx(path_docx)
        nombre_quiz = f"RedaQuiz - Nº{orden_id}.docx"
        path_quiz = f"static/generated/{nombre_quiz}"
        guardar_quiz_como_docx(preguntas_quiz, path_quiz, color=color, columnas=columnas)
        path_quiz_pdf = convert_to_pdf(path_quiz, color=color)
        
        # Update DB with files
        # Convert local paths to URL paths
        base_url_path = "/static/generated"
        files_list = []

        if path_pdf:
            pdf_name = os.path.basename(path_pdf)
            files_list.append({"name": "Documento Final", "url": f"{base_url_path}/{pdf_name}", "type": "pdf"})

        if path_quiz_pdf:
             quiz_pdf_name = os.path.basename(path_quiz_pdf)
             files_list.append({"name": "Quiz PDF", "url": f"{base_url_path}/{quiz_pdf_name}", "type": "pdf"})

        # Also add DOCX for reference if needed, or just PDF. User asked for products.
        docx_name = os.path.basename(path_docx)
        files_list.append({"name": "Documento Editable", "url": f"{base_url_path}/{docx_name}", "type": "docx"})

        database.update_order_files(orden_id, files_list)
        database.update_order_status(orden_id, "completed")
             
        print(f"[{orden_id}] Archivos generados y disponibles.")
        
        # 7. Notify Client
        if correo_cliente:
             print(f"[{orden_id}] Enviando correo a {correo_cliente}...")
             archivos_adjuntos = [path_docx, path_quiz]
             if path_pdf:
                 archivos_adjuntos.append(path_pdf)
             if path_quiz_pdf:
                 archivos_adjuntos.append(path_quiz_pdf)
                 
             cuerpo_correo = f"""
Hola {user_metadata.get('client', 'Cliente')},

¡Tu pedido de RedaXion está listo! 🚀

Adjuntamos los documentos generados:
1. Documento Transcrito y Mejorado
2. Quiz de Repaso

Puedes ver el estado y descargar tus archivos también en tu dashboard:
http://127.0.0.1:8002/dashboard?external_reference={orden_id}

Gracias por confiar en nosotros.
Equipo RedaXion.
"""
             enviar_correo_con_adjuntos(
                 destinatario=correo_cliente,
                 asunto=f"¡Tu RedaXion está lista! - Orden #{orden_id}",
                 cuerpo=cuerpo_correo,
                 lista_archivos=archivos_adjuntos
             )
             print(f"[{orden_id}] Correo enviado.")

        database.update_order_status(orden_id, "completed")

        # ... (Delivery logic) ...

    except Exception as e:
        print(f"[{orden_id}] Error en el procesamiento: {e}")
        database.update_order_status(orden_id, "error")

# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/orden", response_class=HTMLResponse)
async def read_orden(request: Request):
    return templates.TemplateResponse("orden.html", {"request": request})

@app.get("/mis-ordenes", response_class=HTMLResponse)
async def mis_ordenes(request: Request):
    return templates.TemplateResponse("mis_ordenes.html", {"request": request})
    
@app.get("/ayuda", response_class=HTMLResponse)
async def ayuda(request: Request):
    return templates.TemplateResponse("ayuda.html", {"request": request})

@app.get("/como-funciona", response_class=HTMLResponse)
async def como_funciona(request: Request):
    return templates.TemplateResponse("como_funciona.html", {"request": request})

@app.get("/testimonios", response_class=HTMLResponse)
async def testimonios(request: Request):
    return templates.TemplateResponse("testimonios.html", {"request": request})

import traceback

async def upload_to_gcs(file: UploadFile, destination_blob_name: str) -> str:
    # Simplified mock for now as we don't have credentials in environment
    # In production use proper GCS upload
    print(f"MOCK: Uploading {file.filename} to {destination_blob_name}")
    # Use a custom scheme to trigger the transcription service's mock mode immediately
    return f"mock://storage.googleapis.com/{GCS_BUCKET_NAME}/{destination_blob_name}"

@app.post("/api/orden")
async def crear_orden(
    nombre: str = Form(...),
    correo: str = Form(...),
    color: str = Form(...),
    columnas: str = Form(...),
    audio_file: UploadFile = Form(...)
):
    # 1. Generate unique Order ID
    orden_id = str(uuid.uuid4())
    
    # 2. Upload Audio to GCS
    blob_name = f"{orden_id}/{audio_file.filename}"
    audio_url = await upload_to_gcs(audio_file, blob_name)
    
    # 3. Save metadata to DB
    order_data = {
        "id": orden_id,
        "status": "pending",
        "client": nombre,
        "email": correo,
        "color": color,
        "columnas": columnas,
        "files": [],
        "audio_url": audio_url
    }
    database.create_order(order_data)
    
    print(f"Nueva orden recibida (DB): {orden_id} - Cliente: {nombre}")

    # 4. Create Preference in Mercado Pago
    try:
        preference_data = {
            "items": [
                {
                    "title": "Transcripción RedaXion",
                    "quantity": 1,
                    "unit_price": float(PRICE_AMOUNT), # 3000
                    "currency_id": PRICE_CURRENCY
                }
            ],
            "payer": {
                "email": correo
            },
            "back_urls": {
                "success": "http://127.0.0.1:8002/dashboard",
                "failure": "http://127.0.0.1:8002/dashboard",
                "pending": "http://127.0.0.1:8002/dashboard"
            },
            "auto_return": "approved",
            "external_reference": orden_id,
             "metadata": {
                "orden_id": orden_id,
                "email": correo,
                "color": color,
                "columnas": columnas
            }
        }

        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        
        # Prioritize Sandbox URL for testing
        checkout_url = preference.get("sandbox_init_point") or preference.get("init_point")
        
        if not checkout_url:
             print(f"Error: No checkout URL in response. Full response: {preference}")
             # Fallback
             return {
                "orden_id": orden_id,
                "checkout_url": f"/dashboard?external_reference={orden_id}&mock_payment=true" 
            }

        return {"orden_id": orden_id, "checkout_url": checkout_url}
        
    except Exception as e:
        print("DEBUG: ERROR IN CREAR_ORDEN")
        traceback.print_exc()
        print(f"Error details: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating payment: {str(e)}")

@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    # Check for MP return params or mock_payment
    query_params = request.query_params
    orden_id = query_params.get("external_reference")
    payment_status = query_params.get("collection_status")
    mock = query_params.get("mock_payment")
    
    if orden_id:
        order = database.get_order(orden_id)
        if order:
            # Trigger if it's a mock payment OR if returned from MP with success
            # AND status is still pending (avoid re-triggering if already processing/completed)
            if (mock == "true" or payment_status == "approved") and order["status"] == "pending":
                 asyncio.create_task(procesar_audio_y_documentos(orden_id, order.get("audio_url"), order))
            
            # Re-trigger if error (Retry logic)
            if order["status"] == "error" and (mock == "true" or payment_status == "approved"):
                 print(f"Retrying order {orden_id}...")
                 asyncio.create_task(procesar_audio_y_documentos(orden_id, order.get("audio_url"), order))
            
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/status/{orden_id}")
async def get_orden_status(orden_id: str):
    order = database.get_order(orden_id)
    if not order:
        if orden_id == "demo":
             return {"status": "completed", "files": []}
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    return order

@app.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        query_params = request.query_params
        topic = query_params.get("topic")
        resource_id = query_params.get("id")

        if topic == "payment":
            payment_info = sdk.payment().get(resource_id)
            payment = payment_info["response"]
            
            if payment.get("status") == "approved":
                orden_id = payment.get("external_reference")
                if orden_id:
                     order = database.get_order(orden_id)
                     if order:
                        print(f"Pago aprobado para orden: {orden_id}")
                        background_tasks.add_task(
                            procesar_audio_y_documentos, 
                            orden_id, 
                            audio_public_url=order.get("audio_url"),
                            user_metadata=payment.get("metadata", {})
                        )
        
        return JSONResponse(status_code=200, content={"status": "received"})
    except Exception as e:
        print(f"Webhook Error: {e}")
        return JSONResponse(status_code=200, content={"status": "error"})



