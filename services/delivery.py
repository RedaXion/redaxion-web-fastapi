import smtplib
from email.message import EmailMessage
import os
from typing import List

def subir_archivo_a_drive(file_path: str, filename: str, orden_id: str):
    """
    Simulates GDrive upload.
    User did not provide logic for this, so using Mock.
    """
    print(f"MOCK: Uploading {filename} to Goole Drive for Order {orden_id}...")
    # TODO: Implement real GDrive logic using google-api-python-client

def enviar_correo_con_adjuntos(destinatario: str, asunto: str, cuerpo: str, lista_archivos: List[str]):
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
        # Verify file exists before attaching to prevent errors
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
    except Exception as e:
        print(f"Error sending email: {e}")
