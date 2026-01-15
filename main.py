import os
import uuid
import asyncio
from typing import Optional

from fastapi import FastAPI, UploadFile, Form, HTTPException, Request, BackgroundTasks, Response, Depends
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
from services.storage import get_storage_client, upload_file_to_gcs

# Load environment variables
load_dotenv()

app = FastAPI(title="RedaXion API")

# --- Security Configuration ---
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "change-me-in-production")  # For admin endpoints
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# Add CORS middleware - restricted to allowed origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],  # Configurar en Railway
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Initialize DB on Startup
@app.on_event("startup")
def startup_event():
    database.init_db()
    database.init_analytics_tables()
    database.init_comments_table()
    # Deactivate old codes
    database.deactivate_discount_code("DESCUENTO80")
    print("✅ Base de datos, analytics y comentarios inicializados")

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# --- Configuration ---
MERCADOPAGO_ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
print(f"📦 GCS_BUCKET_NAME configurado: {GCS_BUCKET_NAME or '(no configurado)'}")
# Prices in CLP
PRICE_AMOUNT = 3000  # Transcripción de clase
PRICE_CURRENCY = "CLP"

# Prices for special services
EXAM_PRICE = 1500  # Generador de Pruebas
MEETING_PRICE = 2000  # Transcripción de Reuniones

# Base URL for callbacks (use production URL in Railway)
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8002")

# --- Clients ---
# Initialize Mercado Pago SDK
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

# Initialize GCS Client via service
storage_client = get_storage_client()
if storage_client and os.getenv("GCS_BUCKET_NAME"):
    try:
        bucket = storage_client.bucket(os.getenv("GCS_BUCKET_NAME"))
        # Ensure CORS is set once
        bucket.cors = [{
            "origin": ["*"],
            "method": ["GET", "PUT", "POST", "OPTIONS"],
            "responseHeader": ["Content-Type", "Access-Control-Allow-Origin"],
            "maxAgeSeconds": 3600
        }]
        bucket.patch()
        print("✅ GCS CORS ensured via service")
    except Exception as e:
        print(f"⚠️ Warning config CORS: {e}")

# --- Services ---
from services.transcription import transcribir_audio_async
from services.text_processing import procesar_txt_con_chatgpt
from services.formatting import guardar_como_docx, guardar_quiz_como_docx, convert_to_pdf
from services.quiz_generation import generar_quiz_desde_docx
from services.delivery import subir_archivo_a_drive, enviar_correo_con_adjuntos, enviar_notificacion_error

# New Special Services
from services.exam_generator import generar_prueba
from services.exam_formatting import guardar_examen_como_docx, guardar_examen_como_pdf
from services.meeting_processing import procesar_reunion
from services.meeting_formatting import guardar_acta_reunion_como_docx, guardar_acta_reunion_como_pdf
from services.document_extraction import extract_context_from_files
from services.napkin_integration import generate_napkin_visual

# Payment Gateway - "flow" or "mercadopago"
from services.flow_payment import crear_pago_flow, obtener_estado_pago, status_code_to_string
PAYMENT_GATEWAY = os.getenv("PAYMENT_GATEWAY", "flow")
print(f"💳 Payment Gateway: {PAYMENT_GATEWAY.upper()}")

# Authentication Service
from services.auth import hash_password, verify_password, create_access_token, decode_access_token

# ORDERS_DB Removed - Using SQLite now

def generar_nombre_documento(texto: str, orden_id: str) -> str:
    """
    Generate a short descriptive name (2-3 words) from document content using GPT.
    Falls back to shortened orden_id on error.
    """
    import re
    from openai import OpenAI
    
    # Fallback name
    fallback_name = f"Transcripcion-{orden_id[:8]}"
    
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return fallback_name
            
        client = OpenAI(api_key=api_key)
        
        # Take first ~2000 chars for context
        texto_muestra = texto[:2000] if len(texto) > 2000 else texto
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cheap
            messages=[
                {"role": "system", "content": "Eres un asistente que genera títulos cortos. Responde SOLO con 2-3 palabras descriptivas, sin puntuación ni paréntesis."},
                {"role": "user", "content": f"Genera un título de 2-3 palabras para este contenido académico:\n\n{texto_muestra}"}
            ],
            temperature=0.3,
            max_tokens=20
        )
        
        nombre_raw = response.choices[0].message.content.strip()
        # Sanitize: remove special chars, limit length
        nombre_limpio = re.sub(r'[^\w\s-]', '', nombre_raw).strip().replace(' ', '_')
        
        # Validate result
        if len(nombre_limpio) < 3 or len(nombre_limpio) > 50:
            return fallback_name
            
        print(f"📝 Nombre de documento generado: {nombre_limpio}")
        return nombre_limpio
        
    except Exception as e:
        print(f"⚠️ Error generando nombre de documento: {e}")
        return fallback_name


# Helper functions for dashboard routing (async wrappers)
async def _run_exam_generation(orden_id: str, order: dict, metadata: dict):
    """Async wrapper to run exam generation from dashboard."""
    print(f"🎓 [DASHBOARD] Starting exam generation for {orden_id}")
    await procesar_y_enviar_prueba(
        orden_id,
        metadata.get("tema"),
        metadata.get("asignatura"),
        metadata.get("nivel"),
        metadata.get("preguntas_alternativa"),
        metadata.get("preguntas_desarrollo"),
        metadata.get("dificultad"),
        order.get("email"),
        order.get("client"),
        metadata.get("color", "azul elegante"),
        metadata.get("eunacom", False),
        metadata.get("context_material")
    )

async def _run_meeting_processing(orden_id: str, order: dict, metadata: dict):
    """Async wrapper to run meeting processing from dashboard."""
    print(f"📋 [DASHBOARD] Starting meeting processing for {orden_id}")
    await procesar_y_enviar_reunion(
        orden_id,
        order.get("audio_url"),
        metadata.get("titulo_reunion", ""),
        metadata.get("asistentes", ""),
        metadata.get("agenda", ""),
        order.get("email"),
        order.get("client")
    )

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
        
        # Note: Napkin visual generation is handled internally by guardar_como_docx
        # It analyzes the document, selects key sections, and embeds visuals automatically
        
        # 3. Generate Main DOCX (includes Napkin visual generation)
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
        
        # Generate descriptive document name from content
        nombre_descriptivo = generar_nombre_documento(texto_procesado, orden_id)
        
        # Update DB with files
        # Upload to GCS if configured - using descriptive names
        url_pdf_remote = upload_file_to_gcs(path_pdf, f"{nombre_descriptivo}.pdf")
        url_doc_remote = upload_file_to_gcs(path_docx, f"{nombre_descriptivo}.docx")
        url_quiz_pdf_remote = upload_file_to_gcs(path_quiz_pdf, f"Quiz-{nombre_descriptivo}.pdf")
        url_quiz_doc_remote = upload_file_to_gcs(path_quiz, f"Quiz-{nombre_descriptivo}.docx")

        # Use remote URLs if upload succeeded, else local
        base_url_path = "/static/generated"
        final_url_pdf = url_pdf_remote or f"{base_url_path}/{os.path.basename(path_pdf)}"
        final_url_doc = url_doc_remote or f"{base_url_path}/{os.path.basename(path_docx)}"
        final_url_quiz_pdf = url_quiz_pdf_remote or f"{base_url_path}/{os.path.basename(path_quiz_pdf)}" if path_quiz_pdf else None
        
        # Update DB with files
        files_list = []

        if final_url_pdf:
            files_list.append({"name": "Documento Final", "url": final_url_pdf, "type": "pdf"})

        if final_url_quiz_pdf:
             files_list.append({"name": "Quiz PDF", "url": final_url_quiz_pdf, "type": "pdf"})

        # Also add DOCX for reference
        if final_url_doc:
            files_list.append({"name": "Documento Editable", "url": final_url_doc, "type": "docx"})

        database.update_order_files(orden_id, files_list)
        database.update_order_status(orden_id, "completed")
             
        print(f"[{orden_id}] Archivos generados y disponibles.")
        
        # 7. Notify Client
        # Check if email already sent
        order_info = database.get_order(orden_id)
        email_sent = order_info.get("email_sent", 0) if order_info else 0

        if correo_cliente and not email_sent:
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
             database.mark_order_email_sent(orden_id)
             print(f"[{orden_id}] Correo enviado.")
        elif email_sent:
             print(f"[{orden_id}] Correo ya enviado anteriormente. Omitiendo.")

        database.update_order_status(orden_id, "completed")

        # ... (Delivery logic) ...

    except Exception as e:
        print(f"[{orden_id}] Error en el procesamiento: {e}")
        database.update_order_status(orden_id, "error")
        # Notificar al administrador del error
        enviar_notificacion_error(
            orden_id=orden_id,
            error_message=str(e),
            error_type="transcripción",
            customer_email=correo_cliente
        )

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

# --- Authentication Routes ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/registro", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/mi-cuenta", response_class=HTMLResponse)
async def mi_cuenta_page(request: Request):
    return templates.TemplateResponse("mi_cuenta.html", {"request": request})

# --- Special Services API Endpoints ---

# --- Discount Codes API ---
@app.post("/api/validate-discount")
async def validate_discount(code: str = Form(...)):
    """Validate a discount code and return discount info."""
    result = database.validate_discount_code(code)
    return result

@app.post("/api/create-discount-code")
async def create_discount_code_endpoint(
    admin_key: str = Form(...),  # Required admin authentication
    code: str = Form(...),
    discount_percent: int = Form(...),
    max_uses: int = Form(None),
    expiry_date: str = Form(None)
):
    """Create a new discount code (admin only - requires ADMIN_SECRET)."""
    # Validate admin authentication
    if admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Acceso denegado - clave admin inválida")
    
    # Validate discount percent range
    if discount_percent < 0 or discount_percent > 100:
        raise HTTPException(status_code=400, detail="Porcentaje debe estar entre 0 y 100")
    
    success = database.create_discount_code(code, discount_percent, max_uses, expiry_date)
    if success:
        return {"success": True, "message": f"Código {code.upper()} creado con {discount_percent}% descuento"}
    else:
        raise HTTPException(status_code=400, detail="Código ya existe")


# --- Authentication API ---

async def get_current_user(request: Request):
    """Dependency to get current authenticated user from JWT cookie."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    
    payload = decode_access_token(token)
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    user = database.get_user_by_id(user_id)
    return user


@app.post("/api/auth/register")
async def register_user(
    response: Response,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    """Register a new user account."""
    # Validate email not already registered
    existing = database.get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=400, detail="Este correo ya está registrado")
    
    # Validate password length
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    
    # Create user
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)
    success = database.create_user(user_id, email, password_hash, name)
    
    if not success:
        raise HTTPException(status_code=500, detail="Error creando usuario")
    
    # Link existing orders with this email to the user
    database.link_orders_to_user(email, user_id)
    
    # Generate token and set cookie
    token = create_access_token({"sub": user_id, "email": email})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=60 * 60 * 24 * 7  # 7 days
    )
    
    print(f"✅ Usuario registrado: {email}")
    return {"success": True, "user": {"id": user_id, "name": name, "email": email}}


@app.post("/api/auth/login")
async def login_user(
    response: Response,
    email: str = Form(...),
    password: str = Form(...)
):
    """Login with email and password."""
    user = database.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    # Generate token
    token = create_access_token({"sub": user["id"], "email": email})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=60 * 60 * 24 * 7  # 7 days
    )
    
    print(f"✅ Usuario logueado: {email}")
    return {"success": True, "user": {"id": user["id"], "name": user["name"], "email": email}}


@app.get("/api/auth/me")
async def get_me(request: Request):
    """Get current logged in user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return {
        "id": user["id"], 
        "name": user["name"], 
        "email": user["email"]
    }


@app.post("/api/auth/logout")
async def logout_user(response: Response):
    """Logout - clear auth cookie."""
    response.delete_cookie("access_token")
    return {"success": True}


@app.get("/api/auth/orders")
async def get_user_orders(request: Request):
    """Get all orders for the logged in user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    
    orders = database.get_orders_by_user_id(user["id"])
    
    # Also get orders by email that might not be linked yet
    email_orders = database.get_orders_by_email(user["email"])
    
    # Merge and dedupe
    order_ids = {o["id"] for o in orders}
    for order in email_orders:
        if order["id"] not in order_ids:
            orders.append(order)
            # Link this order to the user
            database.update_order_user_id(order["id"], user["id"])
    
    # Sort by created_at descending
    orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {"orders": orders}


@app.post("/api/reprocess-order")
async def reprocess_order_endpoint(
    background_tasks: BackgroundTasks,
    admin_key: str = Form(...),
    orden_id: str = Form(...),
    audio_url: str = Form(...),
    email: str = Form(...),
    nombre: str = Form(...),
    color: str = Form("azul elegante"),
    columnas: str = Form("una")
):
    """Emergency endpoint to reprocess an order manually (admin only)."""
    if admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    
    # Create order in DB
    order_data = {
        "id": orden_id,
        "status": "processing",
        "client": nombre,
        "email": email,
        "color": color,
        "columnas": columnas,
        "files": [],
        "audio_url": audio_url,
        "service_type": "transcription"
    }
    
    try:
        database.create_order(order_data)
    except:
        # Order might exist, update status instead
        database.update_order_status(orden_id, "processing")
    
    # Start processing
    user_metadata = {
        "email": email,
        "client": nombre,
        "color": color,
        "columnas": columnas
    }
    background_tasks.add_task(
        procesar_audio_y_documentos, orden_id, audio_url, user_metadata
    )
    
    print(f"🔧 [ADMIN] Reprocesando orden {orden_id} para {email}")
    return {"success": True, "message": f"Orden {orden_id} en reprocesamiento"}


async def procesar_y_enviar_prueba(orden_id: str, tema: str, asignatura: str, nivel: str,
                                    preguntas_alternativa: int, preguntas_desarrollo: int,
                                    dificultad: int, correo: str, nombre: str,
                                    color: str = "azul elegante", eunacom: bool = False,
                                    context_material: str = None):
    """Background task to generate exam and send to client."""
    print(f"[{orden_id}] Generando prueba: {asignatura} - {tema} (EUNACOM: {eunacom}, Color: {color})")
    if context_material:
        print(f"[{orden_id}] Con material de contexto: {len(context_material)} caracteres")
    database.update_order_status(orden_id, "processing")
    
    try:
        # Generate exam with ChatGPT
        resultado = generar_prueba(tema, asignatura, nivel, preguntas_alternativa, 
                                   preguntas_desarrollo, dificultad, eunacom=eunacom,
                                   context_material=context_material)
        
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
        # Check if email already sent
        order_info = database.get_order(orden_id)
        email_sent = order_info.get("email_sent", 0) if order_info else 0
        
        if correo and not email_sent:
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
            database.mark_order_email_sent(orden_id)
            print(f"[{orden_id}] Correo enviado a {correo}")
        elif email_sent:
            print(f"[{orden_id}] Correo ya enviado anteriormente. Omitiendo.")
            
    except Exception as e:
        print(f"[{orden_id}] Error generando prueba: {e}")
        database.update_order_status(orden_id, "error")
        # Notificar al administrador del error
        enviar_notificacion_error(
            orden_id=orden_id,
            error_message=str(e),
            error_type="generador de pruebas",
            customer_email=correo
        )


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
    action: str = Form("pay"),    # "pay" or "skip" for testing
    context_files: list[UploadFile] = [],  # Optional context files
    discount_code: str = Form(None)  # Optional discount code
):
    """Create a test/exam order and generate payment."""
    orden_id = str(uuid.uuid4())
    
    # Calculate price with discount
    base_price = EXAM_PRICE
    discount_percent = 0
    final_price = base_price
    FLOW_MIN_AMOUNT = 350  # Flow minimum payment in CLP
    
    if discount_code:
        discount_result = database.validate_discount_code(discount_code)
        if discount_result.get("valid"):
            discount_percent = discount_result.get("discount_percent", 0)
            final_price = int(base_price * (1 - discount_percent / 100))
            # Enforce minimum price for Flow
            if final_price < FLOW_MIN_AMOUNT:
                final_price = FLOW_MIN_AMOUNT
                print(f"🏷️ Código {discount_code.upper()} aplicado: {discount_percent}% off → mínimo ${final_price}")
            else:
                print(f"🏷️ Código {discount_code.upper()} aplicado: {discount_percent}% off → ${final_price}")
            # Increment usage count
            database.increment_code_usage(discount_code)
        else:
            print(f"⚠️ Código inválido: {discount_code} - {discount_result.get('reason')}")
    
    # Extract text from uploaded context files
    context_material = None
    if context_files:
        print(f"📎 Procesando {len(context_files)} archivos de contexto...")
        files_data = []
        total_size = 0
        for file in context_files:
            if file.filename:  # Skip empty file inputs
                file_bytes = await file.read()
                total_size += len(file_bytes)
                files_data.append((file.filename, file_bytes))
        
        # Check total size (150MB limit)
        if total_size > 150 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Total de archivos excede 150MB")
        
        if files_data:
            context_material = extract_context_from_files(files_data)
            print(f"✅ Contexto extraído: {len(context_material)} caracteres de {len(files_data)} archivo(s)")
    
    # Store exam params in metadata field for DB persisting
    exam_metadata = {
        "tema": tema,
        "asignatura": asignatura,
        "nivel": nivel,
        "preguntas_alternativa": preguntas_alternativa,
        "preguntas_desarrollo": preguntas_desarrollo,
        "dificultad": dificultad,
        "color": color,
        "eunacom": eunacom,
        "has_context": bool(context_material),
        "discount_code": discount_code.upper() if discount_code else None,
        "discount_percent": discount_percent,
        "final_price": final_price
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
            "metadata": exam_metadata,
            "paid_amount": final_price,
            "discount_code": discount_code or "",
            "discount_percent": discount_percent
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
            color, eunacom, context_material
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
        "metadata": exam_metadata,
        "paid_amount": final_price,
        "discount_code": discount_code or "",
        "discount_percent": discount_percent
    }
    database.create_order(order_data)
    
    print(f"Nueva orden de prueba: {orden_id} - {asignatura} (Gateway: {gateway}, Precio: ${final_price})")
    
    try:
        # Use Flow or MercadoPago based on user selection
        if gateway == "flow":
            resultado_pago = crear_pago_flow(
                orden_id=orden_id,
                monto=final_price,  # Use discounted price
                email=correo,
                descripcion=f"Generador de Pruebas - {asignatura}" + (f" ({discount_percent}% desc.)" if discount_percent else ""),
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
                    "id": orden_id,
                    "title": f"Generador de Pruebas - {asignatura}",
                    "description": f"Prueba de {asignatura} - Nivel {nivel} - {preguntas_alternativa} alt. + {preguntas_desarrollo} desarrollo",
                    "category_id": "services",
                    "quantity": 1,
                    "unit_price": float(final_price),
                    "currency_id": PRICE_CURRENCY
                }],
                "payer": {"email": correo, "name": nombre},
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
                },
                "notification_url": f"{BASE_URL}/webhook/mercadopago"
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
        # Upload to GCS if configured
        url_pdf_acta_remote = upload_file_to_gcs(path_pdf, f"{orden_id}_acta.pdf")
        url_docx_acta_remote = upload_file_to_gcs(path_docx, f"{orden_id}_acta.docx")
        
        # Use remote URLs if upload succeeded, else local
        base_url_path = "/static/generated"
        final_url_pdf = url_pdf_acta_remote or f"{base_url_path}/Acta-{orden_id}.pdf"
        final_url_docx = url_docx_acta_remote or f"{base_url_path}/Acta-{orden_id}.docx"
        
        # Update database with final URLs
        files_list = [
            {"name": "Acta PDF", "url": final_url_pdf, "type": "pdf"},
            {"name": "Acta Editable DOCX", "url": final_url_docx, "type": "docx"}
        ]
        database.update_order_files(orden_id, files_list)
        
        database.update_order_status(orden_id, "completed")
        print(f"✅ Orden {orden_id} completada.")
        
        print(f"[{orden_id}] Acta generada: {path_pdf}")
        
        # 4. Update DB (This section is now redundant with the GCS upload logic above)
        # import os
        # base_url_path = "/static/generated"
        # files_list = [
        #     {"name": "Acta PDF", "url": f"{base_url_path}/Acta-{orden_id}.pdf", "type": "pdf"},
        #     {"name": "Acta Editable", "url": f"{base_url_path}/Acta-{orden_id}.docx", "type": "docx"}
        # ]
        # database.update_order_files(orden_id, files_list)
        # database.update_order_status(orden_id, "completed")
        
        # 5. Send email
        # Check if email already sent
        order_info = database.get_order(orden_id)
        email_sent = order_info.get("email_sent", 0) if order_info else 0

        if correo and not email_sent:
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
            database.mark_order_email_sent(orden_id)
            print(f"[{orden_id}] Correo enviado a {correo}")
        elif email_sent:
            print(f"[{orden_id}] Correo ya enviado anteriormente. Omitiendo.")
            
    except Exception as e:
        print(f"[{orden_id}] Error procesando reunión: {e}")
        database.update_order_status(orden_id, "error")
        # Notificar al administrador del error
        enviar_notificacion_error(
            orden_id=orden_id,
            error_message=str(e),
            error_type="transcripción de reunión",
            customer_email=correo
        )


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
    action: str = Form("pay"),    # "pay" or "skip" for testing
    discount_code: str = Form(None)  # Optional discount code
):
    """Create a meeting transcription order."""
    
    # Calculate price with discount
    base_price = MEETING_PRICE
    discount_percent = 0
    final_price = base_price
    FLOW_MIN_AMOUNT = 350  # Flow minimum payment in CLP
    
    if discount_code:
        discount_result = database.validate_discount_code(discount_code)
        if discount_result.get("valid"):
            discount_percent = discount_result.get("discount_percent", 0)
            final_price = int(base_price * (1 - discount_percent / 100))
            # Enforce minimum price for Flow
            if final_price < FLOW_MIN_AMOUNT:
                final_price = FLOW_MIN_AMOUNT
                print(f"🏷️ Código {discount_code.upper()} aplicado: {discount_percent}% off → mínimo ${final_price}")
            else:
                print(f"🏷️ Código {discount_code.upper()} aplicado: {discount_percent}% off → ${final_price}")
            database.increment_code_usage(discount_code)
        else:
            print(f"⚠️ Código inválido: {discount_code} - {discount_result.get('reason')}")
    
    meeting_metadata = {
        "titulo_reunion": titulo_reunion,
        "asistentes": asistentes,
        "agenda": agenda,
        "discount_code": discount_code.upper() if discount_code else None,
        "discount_percent": discount_percent,
        "final_price": final_price
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
            "metadata": meeting_metadata,
            "paid_amount": final_price,
            "discount_code": discount_code or "",
            "discount_percent": discount_percent
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
        "metadata": meeting_metadata,
        "paid_amount": final_price,
        "discount_code": discount_code or "",
        "discount_percent": discount_percent
    }
    database.create_order(order_data)
    
    print(f"Nueva orden de reunión: {orden_id} - {titulo_reunion or 'Sin título'} (Gateway: {gateway}, Precio: ${final_price})")
    
    try:
        # Use Flow or MercadoPago based on user selection
        if gateway == "flow":
            resultado_pago = crear_pago_flow(
                orden_id=orden_id,
                monto=final_price,  # Use discounted price
                email=correo,
                descripcion="Transcripción de Reunión - RedaXion" + (f" ({discount_percent}% desc.)" if discount_percent else ""),
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
                    "id": orden_id,
                    "title": "Transcripción de Reunión - RedaXion",
                    "description": f"Acta de reunión: {titulo_reunion[:50] if titulo_reunion else 'Sin título'}",
                    "category_id": "services",
                    "quantity": 1,
                    "unit_price": float(final_price),
                    "currency_id": PRICE_CURRENCY
                }],
                "payer": {"email": correo, "name": nombre},
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
                },
                "notification_url": f"{BASE_URL}/webhook/mercadopago"
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
    CRITICAL: Must always return HTTP 200 to Flow, never 500.
    """
    try:
        form_data = await request.form()
        token = form_data.get("token")
        
        if not token:
            print("⚠️ Flow webhook: No token received")
            # Even on error, return 200 to Flow to prevent retries
            return Response(content="OK", status_code=200, media_type="text/plain")
        
        # Safe token logging (handle short tokens)
        token_preview = token[:20] if len(token) > 20 else token
        print(f"🔵 Flow webhook recibido: token={token_preview}...")
        
        # Get payment status from Flow
        try:
            status_data = obtener_estado_pago(token)
        except Exception as e:
            print(f"❌ Error crítico obteniendo estado: {e}")
            traceback.print_exc()
            return Response(content="OK", status_code=200, media_type="text/plain")
        
        if not status_data or "error" in status_data:
            error_msg = status_data.get('error') if status_data else 'No response'
            print(f"❌ Error obteniendo estado de pago: {error_msg}")
            return Response(content="OK", status_code=200, media_type="text/plain")
        
        flow_status = status_data.get("status", 0)
        commerce_order = status_data.get("commerceOrder")  # This is our orden_id
        
        print(f"📋 Flow status: {flow_status} ({status_code_to_string(flow_status)}) - Order: {commerce_order}")
        
        if flow_status == 2:  # PAGADA (Paid)
            # Get order from database
            order = database.get_order(commerce_order)
            
            if order and order.get("status") == "pending":
                service_type = order.get("service_type", "")
                metadata = order.get("metadata", {})
                print(f"🔍 DEBUG WEBHOOK: service_type='{service_type}', has_metadata={bool(metadata)}, metadata_keys={list(metadata.keys()) if metadata else []}")
                
                # Trigger processing based on service type
                if service_type == "exam":
                    # For exam, retrieve metadata from DB
                    if not metadata:
                        print(f"⚠️ Exam order {commerce_order} has no metadata - cannot generate")
                        database.update_order_status(commerce_order, "error")
                    else:
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
                    
                elif service_type == "meeting":
                    database.update_order_status(commerce_order, "paid")
                    
                    # Try to retrieve metadata if available
                    metadata = order.get("metadata", {})
                    
                    # Launch meeting processing
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
                    # Standard transcription order - START PROCESSING
                    database.update_order_status(commerce_order, "paid")
                    
                    user_metadata = {
                        "email": order.get("email"),
                        "client": order.get("client"),
                        "color": order.get("color", "azul elegante"),
                        "columnas": order.get("columnas", "una")
                    }
                    background_tasks.add_task(
                        procesar_audio_y_documentos,
                        commerce_order,
                        order.get("audio_url"),
                        user_metadata
                    )
                    print(f"✅ Pago confirmado y transcripción iniciada: {commerce_order}")
            else:
                if not order:
                    print(f"⚠️ Order {commerce_order} not found in database")
                else:
                    print(f"ℹ️ Order {commerce_order} already processed (status: {order.get('status')})")
        
        elif flow_status == 3:  # RECHAZADA (Rejected)
            if commerce_order:
                database.update_order_status(commerce_order, "failed")
            print(f"❌ Pago rechazado para orden: {commerce_order}")
            
        elif flow_status == 4:  # ANULADA (Cancelled)
            if commerce_order:
                database.update_order_status(commerce_order, "cancelled")
            print(f"⚠️ Pago anulado para orden: {commerce_order}")
        
        return Response(content="OK", status_code=200, media_type="text/plain")
        
    except Exception as e:
        print(f"❌ Error en webhook de Flow: {e}")
        traceback.print_exc()
        # CRITICAL: ALWAYS return 200 to Flow to prevent retries
        return Response(content="OK", status_code=200, media_type="text/plain")


@app.api_route("/api/flow-return", methods=["GET", "POST"])
async def flow_return(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Flow return URL (User redirection after payment).
    Flow redirects here ONLY on successful payment.
    We get orden_id from query params (we put it there when creating payment).
    Note: Flow uses GET redirect, but we accept POST as fallback.
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
            print(f"🔍 DEBUG MP WEBHOOK: service_type='{service_type}', has_metadata={bool(metadata)}, metadata_keys={list(metadata.keys()) if metadata else []}")
            
            # Process based on service type
            if service_type == "exam":
                if not metadata:
                    print(f"⚠️ Exam order {orden_id} has no metadata - cannot generate, returning error")
                    database.update_order_status(orden_id, "error")
                    return RedirectResponse(url=f"/dashboard?external_reference={orden_id}", status_code=303)
                    
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
                # Default: Transcription order
                user_metadata = {
                    "email": order.get("email"),
                    "client": order.get("client"),
                    "color": order.get("color", "azul elegante"),
                    "columnas": order.get("columnas", "una")
                }
                background_tasks.add_task(
                    procesar_audio_y_documentos,
                    orden_id,
                    order.get("audio_url"),
                    user_metadata
                )
                print(f"🚀 [PRODUCTION] Transcription processing started for order {orden_id}")
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
    gateway: str = Form("mercadopago"),  # "flow" or "mercadopago"
    action: str = Form("pay"),   # "pay" or "skip" for testing
    discount_code: str = Form(None),  # Optional discount code
    estimated_minutes: int = Form(None)  # Optional estimated processing time
):
    """
    Create order with pre-uploaded audio from GCS.
    Used for large files that bypass Railway's upload limits.
    """
    
    # Calculate price with discount
    base_price = PRICE_AMOUNT
    discount_percent = 0
    final_price = base_price
    FLOW_MIN_AMOUNT = 350  # Flow minimum payment in CLP
    
    if discount_code:
        discount_result = database.validate_discount_code(discount_code)
        if discount_result.get("valid"):
            discount_percent = discount_result.get("discount_percent", 0)
            final_price = int(base_price * (1 - discount_percent / 100))
            # Enforce minimum price for Flow
            if final_price < FLOW_MIN_AMOUNT:
                final_price = FLOW_MIN_AMOUNT
                print(f"🏷️ Código {discount_code.upper()} aplicado: {discount_percent}% off → mínimo ${final_price}")
            else:
                print(f"🏷️ Código {discount_code.upper()} aplicado: {discount_percent}% off → ${final_price}")
            database.increment_code_usage(discount_code)
        else:
            print(f"⚠️ Código inválido: {discount_code} - {discount_result.get('reason')}")
    
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
            "service_type": "transcription",
            "metadata": {
                "estimated_minutes": estimated_minutes
            } if estimated_minutes else {}
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
        "audio_url": audio_url,
        "metadata": {
            "estimated_minutes": estimated_minutes
        } if estimated_minutes else {}
    }
    database.create_order(order_data)
    
    print(f"Nueva orden GCS recibida (DB): {orden_id} - Cliente: {nombre} (Gateway: {gateway}, Precio: ${final_price})")

    try:
        # Use Flow or MercadoPago based on user selection
        if gateway == "flow":
            resultado_pago = crear_pago_flow(
                orden_id=orden_id,
                monto=final_price,
                email=correo,
                descripcion="Transcripción RedaXion" + (f" ({discount_percent}% desc.)" if discount_percent else ""),
                url_retorno=f"{BASE_URL}/api/flow-return?orden_id={orden_id}",
                url_confirmacion=f"{BASE_URL}/api/flow-webhook",
                optional_data=None
            )
            
            if resultado_pago.get("mock"):
                # Mock payment - start processing immediately
                user_metadata = {
                    "email": correo,
                    "client": nombre,
                    "color": color,
                    "columnas": columnas
                }
                background_tasks.add_task(
                    procesar_audio_y_documentos, orden_id, audio_url, user_metadata
                )
            
            checkout_url = resultado_pago.get("checkout_url")
            if not checkout_url:
                error_msg = resultado_pago.get("error", "Error creando pago Flow")
                raise HTTPException(status_code=400, detail=error_msg)
            
            return {"orden_id": orden_id, "checkout_url": checkout_url}
        
        else:
            # MercadoPago
            preference_data = {
                "items": [
                    {
                        "id": orden_id,
                        "title": "Transcripción RedaXion",
                        "description": f"Transcripción de audio con análisis - {color}",
                        "category_id": "services",
                        "quantity": 1,
                        "unit_price": float(final_price),
                        "currency_id": PRICE_CURRENCY
                    }
                ],
                "payer": {
                    "email": correo,
                    "name": nombre
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
                },
                "notification_url": f"{BASE_URL}/webhook/mercadopago"
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
                service_type = order.get("service_type", "")
                metadata = order.get("metadata", {})
                print(f"🔍 DASHBOARD ROUTING: order={orden_id}, service_type='{service_type}', has_metadata={bool(metadata)}")
                
                if service_type == "exam":
                    if metadata:
                        database.update_order_status(orden_id, "paid")
                        asyncio.create_task(_run_exam_generation(orden_id, order, metadata))
                    else:
                        print(f"⚠️ Exam order {orden_id} missing metadata")
                        database.update_order_status(orden_id, "error")
                elif service_type == "meeting":
                    database.update_order_status(orden_id, "paid")
                    asyncio.create_task(_run_meeting_processing(orden_id, order, metadata))
                else:
                    # Default: transcription
                    database.update_order_status(orden_id, "paid")
                    asyncio.create_task(procesar_audio_y_documentos(orden_id, order.get("audio_url"), order))
            
            # Re-trigger if error (Retry logic) - same routing logic
            if order["status"] == "error" and (mock == "true" or payment_status == "approved"):
                service_type = order.get("service_type", "")
                metadata = order.get("metadata", {})
                print(f"🔄 RETRYING order {orden_id}, service_type='{service_type}'")
                
                if service_type == "exam" and metadata:
                    asyncio.create_task(_run_exam_generation(orden_id, order, metadata))
                elif service_type == "meeting":
                    asyncio.create_task(_run_meeting_processing(orden_id, order, metadata))
                else:
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
                        service_type = order.get("service_type", "")
                        metadata = order.get("metadata", {})
                        print(f"🔍 MP WEBHOOK ROUTING: order={orden_id}, service_type='{service_type}', has_metadata={bool(metadata)}")
                        
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
                        else:
                            # Default: transcription
                            background_tasks.add_task(
                                procesar_audio_y_documentos, 
                                orden_id, 
                                audio_public_url=order.get("audio_url"),
                                user_metadata=order
                            )
        
        return JSONResponse(status_code=200, content={"status": "received"})
    except Exception as e:
        print(f"Webhook Error: {e}")
        return JSONResponse(status_code=200, content={"status": "error"})


# === Admin Dashboard ===
import hashlib
from starlette.responses import Response

ADMIN_DASHBOARD_PASSWORD = os.getenv("ADMIN_DASHBOARD_PASSWORD", "redaxionSCR21")

# Analytics tracking middleware
@app.middleware("http")
async def track_page_views(request: Request, call_next):
    response = await call_next(request)
    
    # Only track GET requests to HTML pages (not API or static)
    path = request.url.path
    if request.method == "GET" and not path.startswith("/api") and not path.startswith("/static") and not path.startswith("/admin"):
        try:
            # Hash IP for privacy
            client_ip = request.client.host if request.client else "unknown"
            ip_hash = hashlib.md5(client_ip.encode()).hexdigest()[:16]
            
            database.record_page_view(
                path=path,
                referrer=request.headers.get("referer"),
                user_agent=request.headers.get("user-agent", "")[:200],
                ip_hash=ip_hash
            )
        except Exception as e:
            pass  # Don't break the request if tracking fails
    
    return response


def verify_admin_session(request: Request) -> bool:
    """Check if user has valid admin session."""
    session_token = request.cookies.get("admin_session")
    expected_token = hashlib.sha256(ADMIN_DASHBOARD_PASSWORD.encode()).hexdigest()
    return session_token == expected_token


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Admin login page."""
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})


@app.post("/admin/auth")
async def admin_auth(request: Request, password: str = Form(...)):
    """Authenticate admin."""
    if password == ADMIN_DASHBOARD_PASSWORD:
        token = hashlib.sha256(ADMIN_DASHBOARD_PASSWORD.encode()).hexdigest()
        response = RedirectResponse(url="/admin/dashboard", status_code=303)
        response.set_cookie(
            key="admin_session",
            value=token,
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="strict"
        )
        return response
    
    return templates.TemplateResponse("admin_login.html", {
        "request": request,
        "error": "Contraseña incorrecta"
    })


@app.get("/admin/logout")
async def admin_logout():
    """Logout admin."""
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("admin_session")
    return response


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Admin dashboard with all metrics."""
    if not verify_admin_session(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    
    try:
        # Get all analytics data
        analytics = database.get_analytics_summary()
        sales = database.get_sales_summary()
        costs = database.calculate_estimated_costs(sales)
        recent_orders = database.get_recent_orders(20)
        discount_stats = database.get_discount_codes_stats()
        comments = database.get_all_comments(50)
        
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "analytics": analytics,
            "sales": sales,
            "costs": costs,
            "recent_orders": recent_orders,
            "discount_stats": discount_stats,
            "comments": comments
        })
    except Exception as e:
        print(f"❌ Error loading admin dashboard: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("admin_login.html", {
            "request": request, 
            "error": f"Error interno cargando dashboard: {str(e)}"
        })


@app.get("/api/admin/metrics")
async def admin_metrics_api(request: Request):
    """API endpoint for admin metrics (requires authentication)."""
    if not verify_admin_session(request):
        raise HTTPException(status_code=401, detail="Not authorized")
    
    analytics = database.get_analytics_summary()
    sales = database.get_sales_summary()
    costs = database.calculate_estimated_costs(sales)
    
    return {
        "analytics": analytics,
        "sales": sales,
        "costs": costs
    }


@app.post("/api/admin/deactivate-code/{code}")
async def admin_deactivate_code(request: Request, code: str):
    """Deactivate a discount code."""
    if not verify_admin_session(request):
        raise HTTPException(status_code=401, detail="Not authorized")
    
    database.deactivate_discount_code(code)
    return {"success": True, "message": f"Código {code} desactivado"}


@app.post("/api/admin/activate-code/{code}")
async def admin_activate_code(request: Request, code: str):
    """Activate a discount code."""
    if not verify_admin_session(request):
        raise HTTPException(status_code=401, detail="Not authorized")
    
    database.activate_discount_code(code)
    return {"success": True, "message": f"Código {code} activado"}


@app.post("/api/admin/create-code")
async def admin_create_code(
    request: Request,
    code: str = Form(...),
    discount_percent: int = Form(...)
):
    """Create a new discount code."""
    if not verify_admin_session(request):
        raise HTTPException(status_code=401, detail="Not authorized")
    
    success = database.create_discount_code(code, discount_percent)
    if success:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    else:
        raise HTTPException(status_code=400, detail=f"El código {code} ya existe")
@app.post("/api/admin/complete-order/{orden_id}")
async def admin_complete_order(request: Request, orden_id: str):
    """Mark an order as completed (admin only)."""
    if not verify_admin_session(request):
        raise HTTPException(status_code=401, detail="Not authorized")
    
    order = database.get_order(orden_id)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    database.update_order_status(orden_id, "completed")
    print(f"✅ [ADMIN] Orden {orden_id} marcada como completada manualmente")
    return {"success": True, "message": f"Orden {orden_id} marcada como completada"}


@app.post("/api/admin/mark-pending/{orden_id}")
async def admin_mark_pending(request: Request, orden_id: str):
    """Mark an order as pending (admin only)."""
    if not verify_admin_session(request):
        raise HTTPException(status_code=401, detail="Not authorized")
    
    order = database.get_order(orden_id)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    database.update_order_status(orden_id, "pending")
    print(f"⏳ [ADMIN] Orden {orden_id} marcada como pendiente manualmente")
    return {"success": True, "message": f"Orden {orden_id} marcada como pendiente"}


@app.post("/api/comments")
async def post_comment(
    order_id: Optional[str] = Form(None),
    page: str = Form(...),
    name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    comment: str = Form(...)
):
    """Post a new comment."""
    success = database.add_comment(order_id, page, name, email, comment)
    if success:
        return {"success": True, "message": "Comentario enviado correctamente"}
    else:
        raise HTTPException(status_code=500, detail="Error al enviar comentario")

@app.get("/api/admin/comments")
async def get_comments(request: Request, limit: int = 50):
    """Get all comments (admin only)."""
    if not verify_admin_session(request):
        raise HTTPException(status_code=401, detail="No autorizado")
    
    comments = database.get_all_comments(limit)
    return {"comments": comments}

