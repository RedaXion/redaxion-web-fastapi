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

def enviar_correo_con_adjuntos(destinatario: str, asunto: str, cuerpo: str, lista_archivos: List[str], bcc: List[str] = None):
    """
    Sends email with attachments.
    Tries Resend API first (works on Railway), then SMTP as fallback.
    
    Args:
        destinatario: Main recipient email address.
        asunto: Email subject.
        cuerpo: Email body (plain text).
        lista_archivos: List of file paths to attach.
        bcc: Optional list of BCC email addresses (hidden from main recipient).
    """
    # Try Resend API first (recommended for Railway)
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if resend_api_key:
        try:
            return _enviar_con_resend(resend_api_key, destinatario, asunto, cuerpo, lista_archivos, bcc=bcc)
        except Exception as e:
            print(f"⚠️ Resend failed: {e}. Trying SMTP...")
    
    # Fallback to SMTP
    return _enviar_con_smtp(destinatario, asunto, cuerpo, lista_archivos, bcc=bcc)

def _enviar_con_resend(api_key: str, destinatario: str, asunto: str, cuerpo: str, lista_archivos: List[str], bcc: List[str] = None):
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
    
    if bcc:
        payload["bcc"] = bcc
    
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload
    )
    
    if response.status_code == 200:
        print(f"✅ Email enviado via Resend a {destinatario}" + (f" (BCC: {bcc})" if bcc else ""))
    else:
        print(f"❌ Resend error: {response.status_code} - {response.text}")
        raise Exception(f"Resend failed: {response.text}")

def _enviar_con_smtp(destinatario: str, asunto: str, cuerpo: str, lista_archivos: List[str], bcc: List[str] = None):
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
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg.set_content(cuerpo)

    for archivo_path in lista_archivos:
        if not archivo_path or not os.path.exists(archivo_path):
            print(f"Warning: Attachment not found: {archivo_path}")
            continue
            
        nombre = os.path.basename(archivo_path)
        with open(archivo_path, "rb") as f:
            contenido = f.read()
        msg.add_attachment(contenido, maintype="application", subtype="octet-stream", filename=nombre)

    all_recipients = [destinatario] + (bcc or [])
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(remitente, clave_app)
            smtp.send_message(msg, to_addrs=all_recipients)
        print(f"✅ Email enviado via SMTP a {destinatario}" + (f" (BCC: {bcc})" if bcc else ""))
    except Exception as e:
        print(f"Error sending email via SMTP: {e}")


def enviar_notificacion_error(orden_id: str, error_message: str, error_type: str = "orden", customer_email: str = None):
    """
    Notifica al administrador cuando ocurre un error crítico en el sistema.
    
    Args:
        orden_id: ID de la orden que falló
        error_message: Mensaje de error detallado
        error_type: Tipo de error (orden, pago, transcripción, etc.)
        customer_email: Email del cliente afectado (opcional)
    """
    admin_email = "chris.rodval@gmail.com"
    
    asunto = f"🚨 ERROR en RedaXion - {error_type.upper()} #{orden_id}"
    
    import datetime
    cuerpo = f"""
¡Alerta de Error en RedaXion!

Tipo de Error: {error_type}
Orden ID: {orden_id}
Cliente: {customer_email or 'N/A'}
Fecha/Hora: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

DETALLES DEL ERROR:
{error_message}

---
Por favor revisa los logs del sistema y contacta al cliente si es necesario.

Dashboard: {os.environ.get('BASE_URL', 'http://localhost:8000')}/dashboard?external_reference={orden_id}
"""
    
    try:
        # Intentar enviar sin adjuntos para notificaciones de error
        enviar_correo_con_adjuntos(
            destinatario=admin_email,
            asunto=asunto,
            cuerpo=cuerpo,
            lista_archivos=[]
        )
        print(f"✅ Notificación de error enviada al administrador para orden {orden_id}")
    except Exception as e:
        print(f"⚠️ No se pudo enviar notificación de error: {e}")
        # No queremos que falle todo si no se puede enviar el email de notificación

