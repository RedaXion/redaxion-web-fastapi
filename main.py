import os
import uuid
import asyncio
from typing import Optional

from fastapi import FastAPI, UploadFile, Form, HTTPException, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
import traceback
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

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
print(f"📦 GCS_BUCKET_NAME configurado: {GCS_BUCKET_NAME or '(no configurado)'}")
# Fixed price for now as per requirements
PRICE_AMOUNT = 3000
PRICE_CURRENCY = "CLP"

# Price for special services (Generador de Pruebas, Transcribe Tu Reunión)
SPECIAL_SERVICES_PRICE = 1500

# Base URL for callbacks (use production URL in Railway)
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8002")

# --- Clients ---
# Initialize Mercado Pago SDK
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

# Initialize GCS Client
storage_client = None
try:
    # Option 1: Try loading from JSON env var (Railway)
    gcs_credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if gcs_credentials_json:
        import json
        from google.oauth2 import service_account
        credentials_dict = json.loads(gcs_credentials_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)
        storage_client = storage.Client(credentials=credentials, project=credentials_dict.get("project_id"))
        print("✅ GCS Client inicializado desde GOOGLE_CREDENTIALS_JSON")
    else:
        # Option 2: Try default credentials (local dev with gcloud auth)
        storage_client = storage.Client()
        print("✅ GCS Client inicializado con credenciales por defecto")
    
    # Configure CORS on bucket for direct browser uploads
    if storage_client and GCS_BUCKET_NAME:
        try:
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            bucket.cors = [
                {
                    "origin": ["*"],  # Allow all origins for now
                    "method": ["GET", "PUT", "POST", "OPTIONS"],
                    "responseHeader": ["Content-Type", "Access-Control-Allow-Origin"],
                    "maxAgeSeconds": 3600
                }
            ]
            bucket.patch()
            print("✅ CORS configurado en bucket GCS")
        except Exception as e:
            print(f"⚠️ No se pudo configurar CORS en bucket: {e}")
            
except Exception as e:
    print(f"⚠️ Warning: Could not initialize GCS client: {e}")
    print("   El sistema usará almacenamiento local como fallback.")
    storage_client = None

# --- Services ---
from services.transcription import transcribir_audio_async
from services.text_processing import procesar_txt_con_chatgpt
from services.formatting import guardar_como_docx, guardar_quiz_como_docx, convert_to_pdf
from services.quiz_generation import generar_quiz_desde_docx
from services.delivery import subir_archivo_a_drive, enviar_correo_con_adjuntos

# New Special Services
from services.exam_generator import generar_prueba
from services.exam_formatting import guardar_examen_como_docx, guardar_examen_como_pdf
from services.meeting_processing import procesar_reunion
from services.meeting_formatting import guardar_acta_reunion_como_docx, guardar_acta_reunion_como_pdf

# Payment Gateway - "flow" or "mercadopago"
from services.flow_payment import crear_pago_flow, obtener_estado_pago, status_code_to_string
PAYMENT_GATEWAY = os.getenv("PAYMENT_GATEWAY", "flow")
print(f"💳 Payment Gateway: {PAYMENT_GATEWAY.upper()}")

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

        # Use async transcription - runs in thread pool so server stays responsive
        transcription_text = await transcribir_audio_async(audio_public_url)
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
{BASE_URL}/dashboard?external_reference={orden_id}

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

# --- Special Services Routes ---
@app.get("/generador-pruebas", response_class=HTMLResponse)
async def generador_pruebas(request: Request):
    return templates.TemplateResponse("generador_pruebas.html", {"request": request})

@app.get("/transcribe-reunion", response_class=HTMLResponse)
async def transcribe_reunion(request: Request):
    return templates.TemplateResponse("transcribe_reunion.html", {"request": request})

@app.get("/soluciones-ia", response_class=HTMLResponse)
async def soluciones_ia(request: Request):
    return templates.TemplateResponse("soluciones_ia.html", {"request": request})


# --- Special Services API Endpoints ---

async def procesar_y_enviar_prueba(orden_id: str, tema: str, asignatura: str, nivel: str,
                                    preguntas_alternativa: int, preguntas_desarrollo: int,
                                    dificultad: int, correo: str, nombre: str,
                                    color: str = "azul elegante", eunacom: bool = False):
    """Background task to generate exam and send to client."""
    print(f"[{orden_id}] Generando prueba: {asignatura} - {tema} (EUNACOM: {eunacom}, Color: {color})")
    database.update_order_status(orden_id, "processing")
    
    try:
        # Generate exam with ChatGPT
        resultado = generar_prueba(tema, asignatura, nivel, preguntas_alternativa, 
                                   preguntas_desarrollo, dificultad, eunacom=eunacom)
        
        if not resultado["success"]:
            raise Exception(resultado.get("error", "Error generando prueba"))
        
        # Get separate exam and solucionario content
        contenido_examen = resultado.get("examen", resultado.get("contenido", ""))
        contenido_solucionario = resultado.get("solucionario", "")
        nombre_prueba = resultado.get("nombre_prueba", f"Prueba {asignatura}")
        
        # Sanitize nombre_prueba for filename (remove special chars)
        import re
        nombre_archivo = re.sub(r'[^\w\s-]', '', nombre_prueba).strip().replace(' ', '_')
        
        # Generate Exam DOCX and PDF with AI-generated name
        path_docx_examen = f"static/generated/{nombre_archivo}-{orden_id}.docx"
        path_pdf_examen = f"static/generated/{nombre_archivo}-{orden_id}.pdf"
        
        guardar_examen_como_docx(contenido_examen, path_docx_examen, color=color)
        guardar_examen_como_pdf(contenido_examen, path_pdf_examen, color=color)
        
        print(f"[{orden_id}] Prueba '{nombre_prueba}' generada: {path_pdf_examen}")
        
        # Generate Solucionario DOCX and PDF (separate file)
        path_docx_solucionario = f"static/generated/Solucionario-{nombre_archivo}-{orden_id}.docx"
        path_pdf_solucionario = f"static/generated/Solucionario-{nombre_archivo}-{orden_id}.pdf"
        
        if contenido_solucionario:
            guardar_examen_como_docx(contenido_solucionario, path_docx_solucionario, color=color)
            guardar_examen_como_pdf(contenido_solucionario, path_pdf_solucionario, color=color)
            print(f"[{orden_id}] Solucionario generado: {path_pdf_solucionario}")
        
        # Update DB with files
        import os
        base_url_path = "/static/generated"
        files_list = [
            {"name": f"{nombre_prueba} - PDF", "url": f"{base_url_path}/{nombre_archivo}-{orden_id}.pdf", "type": "pdf"},
            {"name": f"{nombre_prueba} - Editable", "url": f"{base_url_path}/{nombre_archivo}-{orden_id}.docx", "type": "docx"},
            {"name": "Solucionario - PDF", "url": f"{base_url_path}/Solucionario-{nombre_archivo}-{orden_id}.pdf", "type": "pdf"},
            {"name": "Solucionario - Editable", "url": f"{base_url_path}/Solucionario-{nombre_archivo}-{orden_id}.docx", "type": "docx"}
        ]
        database.update_order_files(orden_id, files_list)
        database.update_order_status(orden_id, "completed")
        
        # Send email
        if correo:
            cuerpo = f"""Hola {nombre},

¡Tu prueba de {asignatura} está lista! 🎓

Tema: {tema}
Nivel: {nivel}
Dificultad: {dificultad}/10
Preguntas de alternativa: {preguntas_alternativa}
Preguntas de desarrollo: {preguntas_desarrollo}

Adjuntamos:
📝 Prueba (PDF y DOCX editable)
✅ Solucionario con justificaciones (PDF y DOCX editable)

Puedes ver y descargar tus archivos en:
{BASE_URL}/dashboard?external_reference={orden_id}

Gracias por usar RedaXion.
"""
            enviar_correo_con_adjuntos(
                destinatario=correo,
                asunto=f"Tu Prueba de {asignatura} está lista - RedaXion",
                cuerpo=cuerpo,
                lista_archivos=[path_pdf_examen, path_docx_examen, path_pdf_solucionario, path_docx_solucionario]
            )
            print(f"[{orden_id}] Correo enviado a {correo}")
            
    except Exception as e:
        print(f"[{orden_id}] Error generando prueba: {e}")
        database.update_order_status(orden_id, "error")


@app.post("/api/crear-prueba")
async def crear_prueba(
    background_tasks: BackgroundTasks,
    nombre: str = Form(...),
    correo: str = Form(...),
    tema: str = Form(...),
    asignatura: str = Form(...),
    nivel: str = Form(...),
    preguntas_alternativa: int = Form(...),
    preguntas_desarrollo: int = Form(...),
    dificultad: int = Form(7),
    color: str = Form("azul elegante"),
    eunacom: bool = Form(False),
    gateway: str = Form("flow"),  # User's payment gateway choice
    action: str = Form("pay")     # "pay" or "skip" for testing
):
    """Create a test/exam order and generate payment."""
    orden_id = str(uuid.uuid4())
    
    # Store exam params in metadata field for DB persisting
    exam_metadata = {
        "tema": tema,
        "asignatura": asignatura,
        "nivel": nivel,
        "preguntas_alternativa": preguntas_alternativa,
        "preguntas_desarrollo": preguntas_desarrollo,
        "dificultad": dificultad,
        "color": color,
        "eunacom": eunacom
    }
    
    # Handle Skip Payment (Test Mode)
    if action == "skip":
        print(f"⏩ SKIP PAYMENT: Creating paid order {orden_id}")
        order_data = {
            "id": orden_id,
            "status": "paid",  # Direct to paid
            "client": nombre,
            "email": correo,
            "files": [],
            "audio_url": "",
            "service_type": "exam",
            "metadata": exam_metadata
        }
        database.create_order(order_data)
        
        # Determine strictness prompt based on EUNACOM mode
        if eunacom:
            # EUNACOM implies strict medical format
            pass
            
        # Start background processing immediately
        background_tasks.add_task(
            procesar_y_enviar_prueba, orden_id, tema, asignatura, nivel,
            preguntas_alternativa, preguntas_desarrollo, dificultad, correo, nombre,
            color, eunacom
        )
        
        # Redirect to dashboard
        # Redirect to dashboard via JSON
        return {
            "orden_id": orden_id,
            "checkout_url": f"/dashboard?external_reference={orden_id}"
        }

    order_data = {
        "id": orden_id,
        "status": "pending",
        "client": nombre,
        "email": correo,
        "files": [],
        "audio_url": "",
        "service_type": "exam",
        "metadata": exam_metadata
    }
    database.create_order(order_data)
    
    print(f"Nueva orden de prueba: {orden_id} - {asignatura} (Gateway: {gateway})")
    
    try:
        # Use Flow or MercadoPago based on user selection
        if gateway == "flow":
            resultado_pago = crear_pago_flow(
                orden_id=orden_id,
                monto=SPECIAL_SERVICES_PRICE,
                email=correo,
                descripcion=f"Generador de Pruebas - {asignatura}",
                url_retorno=f"{BASE_URL}/api/flow-return?orden_id={orden_id}",
                url_confirmacion=f"{BASE_URL}/api/flow-webhook",
                # No sending optional_data to Flow to avoid Error 2002 (Too long)
                # We retrieve metadata from DB in webhook using order_id
                optional_data=None 
            )
            
            if resultado_pago.get("mock"):
                # Mock payment - start processing immediately
                background_tasks.add_task(
                    procesar_y_enviar_prueba, orden_id, tema, asignatura, nivel,
                    preguntas_alternativa, preguntas_desarrollo, dificultad, correo, nombre,
                    color, eunacom
                )
            
            checkout_url = resultado_pago.get("checkout_url")
            if not checkout_url:
                # Return 400 so frontend shows alert with message, avoiding 500 HTML
                error_msg = resultado_pago.get("error", "Error creando pago Flow")
                raise HTTPException(status_code=400, detail=error_msg)
            
            return {"orden_id": orden_id, "checkout_url": checkout_url}
        
        else:
            # MercadoPago (legacy)
            preference_data = {
                "items": [{
                    "title": f"Generador de Pruebas - {asignatura}",
                    "quantity": 1,
                    "unit_price": float(SPECIAL_SERVICES_PRICE),
                    "currency_id": PRICE_CURRENCY
                }],
                "payer": {"email": correo},
                "back_urls": {
                    "success": f"{BASE_URL}/dashboard",
                    "failure": f"{BASE_URL}/dashboard",
                    "pending": f"{BASE_URL}/dashboard"
                },
                "external_reference": orden_id,
                "metadata": {
                    "orden_id": orden_id,
                    "service_type": "exam",
                    **exam_metadata
                }
            }
            
            if "127.0.0.1" not in BASE_URL and "localhost" not in BASE_URL:
                preference_data["auto_return"] = "approved"
            
            preference_response = sdk.preference().create(preference_data)
            preference = preference_response["response"]
            checkout_url = preference.get("init_point") or preference.get("sandbox_init_point")
            
            if not checkout_url:
                # Mock payment for testing
                background_tasks.add_task(
                    procesar_y_enviar_prueba, orden_id, tema, asignatura, nivel,
                    preguntas_alternativa, preguntas_desarrollo, dificultad, correo, nombre,
                    color, eunacom
                )
                return {"orden_id": orden_id, "checkout_url": f"/dashboard?external_reference={orden_id}"}
            
            return {"orden_id": orden_id, "checkout_url": checkout_url}
        
    except Exception as e:
        print(f"Error creating exam order: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def procesar_y_enviar_reunion(orden_id: str, audio_url: str, titulo: str,
                                     asistentes: str, agenda: str, correo: str, nombre: str):
    """Background task to transcribe meeting and generate minutes."""
    print(f"[{orden_id}] Procesando reunión: {titulo or 'Sin título'}")
    database.update_order_status(orden_id, "processing")
    
    try:
        # 1. Transcribe audio with AssemblyAI
        transcripcion = await transcribir_audio_async(audio_url)
        print(f"[{orden_id}] Transcripción completada")
        
        # 2. Process with ChatGPT meeting prompt
        resultado = procesar_reunion(transcripcion, titulo, asistentes, agenda)
        
        if not resultado["success"]:
            raise Exception(resultado.get("error", "Error procesando reunión"))
        
        contenido = resultado["contenido"]
        
        # 3. Generate DOCX and PDF
        path_docx = f"static/generated/Acta-{orden_id}.docx"
        path_pdf = f"static/generated/Acta-{orden_id}.pdf"
        
        guardar_acta_reunion_como_docx(contenido, path_docx)
        guardar_acta_reunion_como_pdf(contenido, path_pdf)
        
        print(f"[{orden_id}] Acta generada: {path_pdf}")
        
        # 4. Update DB
        import os
        base_url_path = "/static/generated"
        files_list = [
            {"name": "Acta PDF", "url": f"{base_url_path}/Acta-{orden_id}.pdf", "type": "pdf"},
            {"name": "Acta Editable", "url": f"{base_url_path}/Acta-{orden_id}.docx", "type": "docx"}
        ]
        database.update_order_files(orden_id, files_list)
        database.update_order_status(orden_id, "completed")
        
        # 5. Send email
        if correo:
            cuerpo = f"""Hola {nombre},

¡Tu acta de reunión está lista! 📋

{f'Reunión: {titulo}' if titulo else ''}

Adjuntamos el acta en formato PDF y DOCX (editable).
El documento incluye:
- Resumen ejecutivo
- Decisiones tomadas
- Lista de acciones con responsables
- Preguntas pendientes
- Bloqueadores identificados

Puedes ver y descargar tus archivos en:
{BASE_URL}/dashboard?external_reference={orden_id}

Gracias por usar RedaXion.
"""
            enviar_correo_con_adjuntos(
                destinatario=correo,
                asunto=f"Tu Acta de Reunión está lista - RedaXion",
                cuerpo=cuerpo,
                lista_archivos=[path_pdf, path_docx]
            )
            print(f"[{orden_id}] Correo enviado a {correo}")
            
    except Exception as e:
        print(f"[{orden_id}] Error procesando reunión: {e}")
        database.update_order_status(orden_id, "error")


@app.post("/api/crear-orden-reunion")
async def crear_orden_reunion(
    background_tasks: BackgroundTasks,
    nombre: str = Form(...),
    correo: str = Form(...),
    titulo_reunion: str = Form(""),
    asistentes: str = Form(""),
    agenda: str = Form(""),
    audio_url: str = Form(...),
    orden_id: str = Form(...),
    gateway: str = Form("flow"),  # User's payment gateway choice
    action: str = Form("pay")     # "pay" or "skip" for testing
):
    """Create a meeting transcription order."""
    meeting_metadata = {
        "titulo_reunion": titulo_reunion,
        "asistentes": asistentes,
        "agenda": agenda
    }
    
    # Handle Skip Payment (Test Mode)
    if action == "skip":
        print(f"⏩ SKIP PAYMENT: Creating paid meeting order {orden_id}")
        order_data = {
            "id": orden_id,
            "status": "paid",  # Direct to paid
            "client": nombre,
            "email": correo,
            "color": "azul elegante",
            "columnas": "una",
            "files": [],
            "audio_url": audio_url,
            "service_type": "meeting",
            "metadata": meeting_metadata
        }
        database.create_order(order_data)
        
        # Start background processing immediately
        background_tasks.add_task(
            procesar_y_enviar_reunion, orden_id, audio_url, titulo_reunion,
            asistentes, agenda, correo, nombre
        )
        
        # Redirect to dashboard
        # Redirect to dashboard via JSON
        return {
            "orden_id": orden_id,
            "checkout_url": f"/dashboard?external_reference={orden_id}"
        }


    
    # Save to DB
    order_data = {
        "id": orden_id,
        "status": "pending",
        "client": nombre,
        "email": correo,
        "color": "azul elegante",
        "columnas": "una",
        "files": [],
        "audio_url": audio_url,
        "service_type": "meeting",
        "metadata": meeting_metadata
    }
    database.create_order(order_data)
    
    print(f"Nueva orden de reunión: {orden_id} - {titulo_reunion or 'Sin título'} (Gateway: {gateway})")
    
    try:
        # Use Flow or MercadoPago based on user selection
        if gateway == "flow":
            resultado_pago = crear_pago_flow(
                orden_id=orden_id,
                monto=SPECIAL_SERVICES_PRICE,
                email=correo,
                descripcion="Transcripción de Reunión - RedaXion",
                url_retorno=f"{BASE_URL}/api/flow-return?orden_id={orden_id}",
                url_confirmacion=f"{BASE_URL}/api/flow-webhook",
                # No sending optional_data to Flow to avoid Error 2002 (Too long)
                optional_data=None
            )
            
            if resultado_pago.get("mock"):
                # Mock payment - start processing immediately
                background_tasks.add_task(
                    procesar_y_enviar_reunion, orden_id, audio_url, titulo_reunion,
                    asistentes, agenda, correo, nombre
                )
            
            checkout_url = resultado_pago.get("checkout_url")
            if not checkout_url:
                error_msg = resultado_pago.get("error", "Error creando pago Flow")
                raise HTTPException(status_code=400, detail=error_msg)
            
            return {"orden_id": orden_id, "checkout_url": checkout_url}
        
        else:
            # MercadoPago (legacy)
            preference_data = {
                "items": [{
                    "title": "Transcripción de Reunión - RedaXion",
                    "quantity": 1,
                    "unit_price": float(SPECIAL_SERVICES_PRICE),
                    "currency_id": PRICE_CURRENCY
                }],
                "payer": {"email": correo},
                "back_urls": {
                    "success": f"{BASE_URL}/dashboard",
                    "failure": f"{BASE_URL}/dashboard",
                    "pending": f"{BASE_URL}/dashboard"
                },
                "external_reference": orden_id,
                "metadata": {
                    "orden_id": orden_id,
                    "service_type": "meeting",
                    **meeting_metadata
                }
            }
            
            if "127.0.0.1" not in BASE_URL and "localhost" not in BASE_URL:
                preference_data["auto_return"] = "approved"
            
            preference_response = sdk.preference().create(preference_data)
            preference = preference_response["response"]
            checkout_url = preference.get("init_point") or preference.get("sandbox_init_point")
            
            if not checkout_url:
                # Mock payment for testing
                background_tasks.add_task(
                    procesar_y_enviar_reunion, orden_id, audio_url, titulo_reunion,
                    asistentes, agenda, correo, nombre
                )
                return {"orden_id": orden_id, "checkout_url": f"/dashboard?external_reference={orden_id}"}
            
            return {"orden_id": orden_id, "checkout_url": checkout_url}
        
    except Exception as e:
        print(f"Error creating meeting order: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# --- Consulting / Soluciones IA ---

@app.post("/api/consulta-soluciones")
async def consulta_soluciones(
    nombre: str = Form(...),
    correo: str = Form(...),
    empresa: str = Form(""),
    descripcion: str = Form(...)
):
    """Receive AI solutions consulting requests and notify via email using Resend."""
    import httpx
    
    print(f"📩 Nueva consulta de soluciones IA de: {nombre} ({correo})")
    
    # Prepare email content
    email_html = f"""
    <h2>🤖 Nueva consulta de Soluciones IA</h2>
    <hr>
    <p><strong>Nombre:</strong> {nombre}</p>
    <p><strong>Correo:</strong> <a href="mailto:{correo}">{correo}</a></p>
    <p><strong>Empresa:</strong> {empresa or 'No especificada'}</p>
    <hr>
    <h3>Descripción de la necesidad:</h3>
    <p>{descripcion.replace(chr(10), '<br>')}</p>
    <hr>
    <p><em>Responder a: <a href="mailto:{correo}">{correo}</a></em></p>
    """
    
    resend_api_key = os.getenv("RESEND_API_KEY")
    admin_email = os.getenv("ADMIN_EMAIL", "contacto@redaxion.cl")
    # Use onboarding@resend.dev as default to avoid "domain not verified" errors
    sender_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    
    if resend_api_key:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {resend_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": f"RedaXion <{sender_email}>",
                        "to": [admin_email],
                        "subject": f"🤖 Nueva Consulta Soluciones IA - {nombre}",
                        "html": email_html,
                        "reply_to": correo
                    }
                )
                
                if response.status_code == 200:
                    print(f"✅ Email enviado via Resend a {admin_email}")
                else:
                    print(f"⚠️ Resend error: {response.status_code} - {response.text}")
                    
        except Exception as e:
            print(f"❌ Error enviando email: {e}")
    else:
        print(f"⚠️ RESEND_API_KEY no configurada. Consulta guardada en logs:")
        print(f"   Nombre: {nombre}, Email: {correo}, Empresa: {empresa}")
        print(f"   Descripción: {descripcion}")
    
    return {"success": True, "message": "Consulta recibida"}


# --- Test Endpoints (Skip Payment for Development) ---

@app.post("/api/crear-prueba-test")
async def crear_prueba_test(
    background_tasks: BackgroundTasks,
    nombre: str = Form(...),
    correo: str = Form(...),
    tema: str = Form(...),
    asignatura: str = Form(...),
    nivel: str = Form(...),
    preguntas_alternativa: int = Form(...),
    preguntas_desarrollo: int = Form(...),
    dificultad: int = Form(7)
):
    """Test endpoint - Create exam without payment (for development only)."""
    orden_id = str(uuid.uuid4())
    
    order_data = {
        "id": orden_id,
        "status": "pending",
        "client": nombre,
        "email": correo,
        "color": "azul elegante",
        "columnas": "una",
        "files": [],
        "audio_url": "",
        "service_type": "exam_test"
    }
    database.create_order(order_data)
    
    print(f"🧪 [TEST] Nueva orden de prueba (sin pago): {orden_id}")
    
    # Immediately start processing
    background_tasks.add_task(
        procesar_y_enviar_prueba, orden_id, tema, asignatura, nivel,
        preguntas_alternativa, preguntas_desarrollo, dificultad, correo, nombre
    )
    
    return {"orden_id": orden_id, "message": "Procesando en modo test"}


@app.post("/api/crear-orden-reunion-test")
async def crear_orden_reunion_test(
    background_tasks: BackgroundTasks,
    nombre: str = Form(...),
    correo: str = Form(...),
    titulo_reunion: str = Form(""),
    asistentes: str = Form(""),
    agenda: str = Form(""),
    audio_url: str = Form(...),
    orden_id: str = Form(...)
):
    """Test endpoint - Create meeting order without payment (for development only)."""
    order_data = {
        "id": orden_id,
        "status": "pending",
        "client": nombre,
        "email": correo,
        "color": "azul elegante",
        "columnas": "una",
        "files": [],
        "audio_url": audio_url,
        "service_type": "meeting_test"
    }
    database.create_order(order_data)
    
    print(f"🧪 [TEST] Nueva orden de reunión (sin pago): {orden_id}")
    
    # Immediately start processing
    background_tasks.add_task(
        procesar_y_enviar_reunion, orden_id, audio_url, titulo_reunion,
        asistentes, agenda, correo, nombre
    )
    
    return {"orden_id": orden_id, "message": "Procesando en modo test"}


# --- Flow Payment Webhook ---

@app.post("/api/flow-webhook")
async def flow_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Flow payment confirmation webhook.
    Flow sends a POST with token to confirm payment status.
    """
    try:
        form_data = await request.form()
        token = form_data.get("token")
        
        if not token:
            print("⚠️ Flow webhook: No token received")
            return JSONResponse({"error": "No token"}, status_code=400)
        
        print(f"🔵 [NEW CODE] Flow webhook recibido: token={token[:20]}...")
        
        # Get payment status from Flow
        try:
            status_data = obtener_estado_pago(token)
        except Exception as e:
            print(f"❌ Error crítico obteniendo estado: {e}")
            # Return success to Flow to avoid retries, but don't process order
            return "OK"
        
        if not status_data or "error" in status_data:
            print(f"❌ Error obteniendo estado de pago: {status_data.get('error') if status_data else 'No response'}")
            return "OK"  # Return OK to Flow to prevent retries
        
        flow_status = status_data.get("status", 0)
        commerce_order = status_data.get("commerceOrder")  # This is our orden_id
        
        print(f"📋 Flow status: {flow_status} ({status_code_to_string(flow_status)}) - Order: {commerce_order}")
        
        if flow_status == 2:  # PAGADA (Paid)
            # Get order from database
            order = database.get_order(commerce_order)
            
            if order and order.get("status") == "pending":
                service_type = order.get("service_type", "")
                
                # Trigger processing based on service type
                if service_type == "exam":
                    # For exam, retrieve metadata from DB
                    metadata = order.get("metadata", {})
                    if metadata:
                        database.update_order_status(commerce_order, "paid")
                        
                        # Launch generation task
                        background_tasks.add_task(
                            procesar_y_enviar_prueba, 
                            commerce_order, 
                            metadata.get("tema"), 
                            metadata.get("asignatura"), 
                            metadata.get("nivel"),
                            metadata.get("preguntas_alternativa"), 
                            metadata.get("preguntas_desarrollo"), 
                            metadata.get("dificultad"), 
                            order["email"], 
                            order["client"],
                            metadata.get("color", "azul elegante"),
                            metadata.get("eunacom", False)
                        )
                        print(f"✅ Pago confirmado y examen en generación: {commerce_order}")
                    else:
                        print(f"⚠️ Error: Orden de examen pagada pero sin metadatos: {commerce_order}")
                        database.update_order_status(commerce_order, "paid")
                    
                elif service_type == "meeting":
                    database.update_order_status(commerce_order, "paid")
                    
                    # Try to retrieve metadata if available
                    metadata = order.get("metadata", {})
                    
                    # Launch meeting meeting processing
                    background_tasks.add_task(
                        procesar_y_enviar_reunion, 
                        commerce_order, 
                        order.get("audio_url"), 
                        metadata.get("titulo_reunion", ""), 
                        metadata.get("asistentes", ""), 
                        metadata.get("agenda", ""), 
                        order["email"], 
                        order["client"]
                    )
                    print(f"✅ Pago confirmado y reunión en proceso: {commerce_order}")
                    
                else:
                    # Standard transcription order
                    database.update_order_status(commerce_order, "paid")
                    print(f"✅ Pago confirmado para orden: {commerce_order}")
        
        elif flow_status == 3:  # RECHAZADA (Rejected)
            database.update_order_status(commerce_order, "failed")
            print(f"❌ Pago rechazado para orden: {commerce_order}")
            
        elif flow_status == 4:  # ANULADA (Cancelled)
            database.update_order_status(commerce_order, "cancelled")
            print(f"⚠️ Pago anulado para orden: {commerce_order}")
        
        return "OK"
        
    except Exception as e:
        print(f"❌ Error en webhook de Flow: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/flow-return")
async def flow_return(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Flow return URL (User redirection after payment).
    Flow redirects here ONLY on successful payment.
    We get orden_id from query params (we put it there when creating payment).
    """
    try:
        # Get orden_id from our query param (we added it when creating the payment)
        query_params = dict(request.query_params)
        orden_id = query_params.get("orden_id")
        
        print(f"🔵 [PRODUCTION] Flow return: orden_id={orden_id}")
        
        if not orden_id:
            print("⚠️ Flow return: No orden_id in URL - redirecting to dashboard")
            return RedirectResponse(url="/dashboard", status_code=303)
        
        # Get order from database
        order = database.get_order(orden_id)
        
        if not order:
            print(f"⚠️ Flow return: Order {orden_id} not found in DB")
            return RedirectResponse(url="/dashboard", status_code=303)
        
        # If order is still pending, mark as paid and process
        if order.get("status") == "pending":
            database.update_order_status(orden_id, "paid")
            print(f"✅ Order {orden_id} marked as PAID")
            
            # Get metadata and service type
            metadata = order.get("metadata", {})
            service_type = order.get("service_type", "")
            
            # Process based on service type
            if service_type == "exam" and metadata:
                background_tasks.add_task(
                    procesar_y_enviar_prueba,
                    orden_id,
                    metadata.get("tema"),
                    metadata.get("asignatura"),
                    metadata.get("nivel"),
                    metadata.get("preguntas_alternativa"),
                    metadata.get("preguntas_desarrollo"),
                    metadata.get("dificultad"),
                    order["email"],
                    order["client"],
                    metadata.get("color", "azul elegante"),
                    metadata.get("eunacom", False)
                )
                print(f"🚀 [PRODUCTION] Exam generation started for order {orden_id}")
                
            elif service_type == "meeting":
                background_tasks.add_task(
                    procesar_y_enviar_reunion,
                    orden_id,
                    order.get("audio_url"),
                    metadata.get("titulo_reunion", ""),
                    metadata.get("asistentes", ""),
                    metadata.get("agenda", ""),
                    order["email"],
                    order["client"]
                )
                print(f"🚀 [PRODUCTION] Meeting processing started for order {orden_id}")
        else:
            print(f"ℹ️ Order {orden_id} already processed (status: {order.get('status')})")
        
        # Redirect to dashboard with order ID
        return RedirectResponse(url=f"/dashboard?external_reference={orden_id}", status_code=303)
        
    except Exception as e:
        print(f"❌ Error in flow_return: {e}")
        traceback.print_exc()
        return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/api/get-upload-url")
async def get_upload_url(filename: str = Form(...)):
    """
    Generate a signed URL for direct browser-to-GCS upload.
    Falls back to local upload endpoint if GCS is not configured.
    """
    orden_id = str(uuid.uuid4())
    safe_filename = sanitize_filename(filename)
    
    # If GCS is not configured, return local upload URL instead
    if not storage_client or not GCS_BUCKET_NAME:
        print(f"⚠️ GCS no disponible, usando subida local para: {safe_filename}")
        return JSONResponse({
            "success": True,
            "upload_url": f"{BASE_URL}/api/upload-local/{orden_id}",
            "public_url": f"{BASE_URL}/static/uploads/{orden_id}_{safe_filename}",
            "blob_name": f"{orden_id}_{safe_filename}",
            "orden_id": orden_id,
            "local_mode": True
        })
    
    try:
        blob_name = f"{orden_id}_{safe_filename}"
        
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        
        # Generate signed URL for PUT (upload)
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=60),
            method="PUT",
            content_type="application/octet-stream",
        )
        
        # Also generate the public URL for later use
        public_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(days=7),
            method="GET",
        )
        
        print(f"📤 URL de subida generada para: {blob_name}")
        
        return JSONResponse({
            "success": True,
            "upload_url": upload_url,
            "public_url": public_url,
            "blob_name": blob_name,
            "orden_id": orden_id
        })
        
    except Exception as e:
        print(f"❌ Error generando URL de subida: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/upload-local/{orden_id}")
async def upload_local(orden_id: str, request: Request):
    """
    Local file upload fallback when GCS is not configured.
    Saves file directly to static/uploads directory.
    """
    try:
        # Get the raw body (file content)
        content = await request.body()
        
        # Create uploads directory if needed
        upload_dir = "static/uploads"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Get filename from content-disposition header or use default
        filename = f"{orden_id}_audio.mp3"
        file_path = f"{upload_dir}/{filename}"
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(content)
        
        print(f"📁 Audio guardado localmente: {file_path} ({len(content)} bytes)")
        
        return JSONResponse({
            "success": True,
            "message": "File uploaded locally",
            "path": file_path
        })
        
    except Exception as e:
        print(f"❌ Error en subida local: {e}")
        raise HTTPException(status_code=500, detail=str(e))


import traceback
import re
from urllib.parse import quote
from datetime import timedelta

def sanitize_filename(filename: str) -> str:
    """Remove spaces and special characters from filename."""
    # Replace spaces with underscores
    filename = filename.replace(" ", "_")
    # Remove any characters that aren't alphanumeric, underscore, dash, or dot
    filename = re.sub(r'[^\w\-.]', '', filename)
    return filename

async def upload_to_gcs(file: UploadFile, destination_blob_name: str) -> str:
    """
    Uploads audio file to GCS and returns a public URL.
    Falls back to local storage if GCS is not configured.
    """
    # Sanitize the filename to avoid URL issues
    safe_filename = sanitize_filename(destination_blob_name.replace("/", "_"))
    
    if storage_client and GCS_BUCKET_NAME:
        try:
            print(f"📤 Intentando subir a GCS bucket: {GCS_BUCKET_NAME}")
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(safe_filename)
            
            content = await file.read()
            blob.upload_from_string(content, content_type=file.content_type or "audio/mpeg")
            
            # Generate a signed URL (valid for 7 days) instead of make_public()
            # This works with uniform bucket-level access
            public_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(days=7),
                method="GET"
            )
            
            print(f"✅ Audio subido a GCS: {safe_filename}")
            print(f"📎 URL firmada (válida 7 días): {public_url[:80]}...")
            return public_url
        except Exception as e:
            print(f"⚠️ Error subiendo a GCS: {e}")
            traceback.print_exc()
            print("   Usando almacenamiento local como fallback...")
            # Reset file position for fallback
            await file.seek(0)
    
    # Fallback: Local storage
    upload_dir = "static/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = f"{upload_dir}/{safe_filename}"
    
    # Reset file position if needed
    try:
        await file.seek(0)
    except:
        pass
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    print(f"📁 Audio guardado localmente: {file_path} ({len(content)} bytes)")
    
    # URL encode the path for safety
    public_url = f"{BASE_URL}/static/uploads/{quote(safe_filename)}"
    print(f"📎 URL pública: {public_url}")
    return public_url

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
                "success": f"{BASE_URL}/dashboard",
                "failure": f"{BASE_URL}/dashboard",
                "pending": f"{BASE_URL}/dashboard"
            },
            "external_reference": orden_id,
            "metadata": {
                "orden_id": orden_id,
                "email": correo,
                "color": color,
                "columnas": columnas
            }
        }
        
        # Only use auto_return in production (MercadoPago rejects localhost URLs)
        if "127.0.0.1" not in BASE_URL and "localhost" not in BASE_URL:
            preference_data["auto_return"] = "approved"

        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        
        # Use production URL first, fallback to sandbox
        checkout_url = preference.get("init_point") or preference.get("sandbox_init_point")
        
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

# --- New endpoint for direct GCS upload orders ---
@app.post("/api/orden-gcs")
async def crear_orden_gcs(
    background_tasks: BackgroundTasks,
    nombre: str = Form(...),
    correo: str = Form(...),
    color: str = Form(...),
    columnas: str = Form(...),
    audio_url: str = Form(...),  # Pre-uploaded GCS URL
    orden_id: str = Form(...),   # Order ID from get-upload-url
    action: str = Form("pay")    # "pay" or "skip" for testing
):
    """
    Create order with pre-uploaded audio from GCS.
    Used for large files that bypass Railway's upload limits.
    """
    
    # Handle Skip Payment (Test Mode)
    if action == "skip":
        print(f"⏩ SKIP PAYMENT: Creating paid order {orden_id}")
        order_data = {
            "id": orden_id,
            "status": "paid",  # Direct to paid
            "client": nombre,
            "email": correo,
            "color": color,
            "columnas": columnas,
            "files": [],
            "audio_url": audio_url,
            "service_type": "transcription"
        }
        database.create_order(order_data)
        
        # Start background processing immediately
        user_metadata = {
            "email": correo,
            "client": nombre,
            "color": color,
            "columnas": columnas
        }
        background_tasks.add_task(
            procesar_audio_y_documentos, orden_id, audio_url, user_metadata
        )
        
        return {
            "orden_id": orden_id,
            "checkout_url": f"/dashboard?external_reference={orden_id}"
        }
    
    # Normal payment flow
    # 1. Save metadata to DB
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
    
    print(f"Nueva orden GCS recibida (DB): {orden_id} - Cliente: {nombre}")

    # 2. Create Preference in Mercado Pago
    try:
        preference_data = {
            "items": [
                {
                    "title": "Transcripción RedaXion",
                    "quantity": 1,
                    "unit_price": float(PRICE_AMOUNT),
                    "currency_id": PRICE_CURRENCY
                }
            ],
            "payer": {
                "email": correo
            },
            "back_urls": {
                "success": f"{BASE_URL}/dashboard",
                "failure": f"{BASE_URL}/dashboard",
                "pending": f"{BASE_URL}/dashboard"
            },
            "external_reference": orden_id,
            "metadata": {
                "orden_id": orden_id,
                "email": correo,
                "color": color,
                "columnas": columnas
            }
        }
        
        # Only use auto_return in production
        if "127.0.0.1" not in BASE_URL and "localhost" not in BASE_URL:
            preference_data["auto_return"] = "approved"

        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        
        # Use production or sandbox URL
        checkout_url = preference.get("init_point") or preference.get("sandbox_init_point")
        
        if not checkout_url:
            print(f"Error: No checkout URL. Response: {preference}")
            return {
                "orden_id": orden_id,
                "checkout_url": f"/dashboard?external_reference={orden_id}&mock_payment=true" 
            }

        return {"orden_id": orden_id, "checkout_url": checkout_url}
        
    except Exception as e:
        print(f"ERROR IN CREAR_ORDEN_GCS: {e}")
        traceback.print_exc()
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



