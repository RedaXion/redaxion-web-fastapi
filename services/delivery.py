import smtplib
from email.message import EmailMessage
import os
from typing import List
import requests
import base64

def subir_archivo_a_drive(file_path: str, filename: str, orden_id: str):
    """
    Simulates GDrive upload.
    User did not provide logic for this, so using Mock.
    """
    print(f"MOCK: Uploading {filename} to Goole Drive for Order {orden_id}...")
    # TODO: Implement real GDrive logic using google-api-python-client

def enviar_correo_con_adjuntos(destinatario: str, asunto: str, cuerpo: str, lista_archivos: List[str]):
    """
    Sends email with attachments.
    Tries Resend API first (works on Railway), then SMTP as fallback.
    """
    # Try Resend API first (recommended for Railway)
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if resend_api_key:
        try:
            return _enviar_con_resend(resend_api_key, destinatario, asunto, cuerpo, lista_archivos)
        except Exception as e:
            print(f"⚠️ Resend failed: {e}. Trying SMTP...")
    
    # Fallback to SMTP
    return _enviar_con_smtp(destinatario, asunto, cuerpo, lista_archivos)

def _enviar_con_resend(api_key: str, destinatario: str, asunto: str, cuerpo: str, lista_archivos: List[str]):
    """Send email using Resend API (works on Railway)."""
    from_email = os.environ.get("RESEND_FROM_EMAIL", "RedaXion <noreply@redaxiontcp.com>")
    
    # Prepare attachments
    attachments = []
    for archivo_path in lista_archivos:
        if not archivo_path or not os.path.exists(archivo_path):
            continue
        nombre = os.path.basename(archivo_path)
        with open(archivo_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        attachments.append({
            "filename": nombre,
            "content": content
        })
    
    payload = {
        "from": from_email,
        "to": [destinatario],
        "subject": asunto,
        "text": cuerpo,
        "attachments": attachments
    }
    
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload
    )
    
    if response.status_code == 200:
        print(f"✅ Email enviado via Resend a {destinatario}")
    else:
        print(f"❌ Resend error: {response.status_code} - {response.text}")
        raise Exception(f"Resend failed: {response.text}")

def _enviar_con_smtp(destinatario: str, asunto: str, cuerpo: str, lista_archivos: List[str]):
    """Send email using SMTP (may not work on Railway)."""
    remitente = os.environ.get("REDA_CORREO_REMITENTE")
    clave_app = os.environ.get("REDA_CLAVE_APP_GMAIL")

    if not remitente or not clave_app:
        print(f"DEBUG EMAIL: Remitente present? {bool(remitente)}, Clave present? {bool(clave_app)}")
        print("Warning: Email credentials not found. Skipping email.")
        return

    msg = EmailMessage()
    msg["From"] = remitente
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.set_content(cuerpo)

    for archivo_path in lista_archivos:
        if not archivo_path or not os.path.exists(archivo_path):
            print(f"Warning: Attachment not found: {archivo_path}")
            continue
            
        nombre = os.path.basename(archivo_path)
        with open(archivo_path, "rb") as f:
            contenido = f.read()
        msg.add_attachment(contenido, maintype="application", subtype="octet-stream", filename=nombre)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(remitente, clave_app)
            smtp.send_message(msg)
        print(f"✅ Email enviado via SMTP a {destinatario}")
    except Exception as e:
        print(f"Error sending email via SMTP: {e}")
