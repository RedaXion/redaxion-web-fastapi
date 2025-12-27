#!/usr/bin/env python3
"""
Script de emergencia para enviar la orden de Julio Riquelme
Los archivos ya están en GCS, solo falta enviar el correo.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Datos de la orden
ORDEN_ID = "2a1b4040-5bf3-4c70-9690-0693c4ea04ec"
CLIENTE_EMAIL = "julio.cra@gmail.com"
CLIENTE_NOMBRE = "Julio Riquelme"

# URLs de los archivos en GCS (ya subidos según los logs)
GCS_BASE = "https://storage.googleapis.com/redaxion_audios"
ARCHIVOS = {
    "documento_pdf": f"{GCS_BASE}/{ORDEN_ID}_documento.pdf",
    "documento_docx": f"{GCS_BASE}/{ORDEN_ID}_documento.docx",
    "quiz_pdf": f"{GCS_BASE}/{ORDEN_ID}_quiz.pdf",
    "quiz_docx": f"{GCS_BASE}/{ORDEN_ID}_quiz.docx",
}

# URL del dashboard
BASE_URL = os.getenv("BASE_URL", "https://redaxion-web-production.up.railway.app")

def enviar_correo():
    """Enviar correo al cliente con los links de descarga."""
    from services.delivery import enviar_correo_con_adjuntos
    
    cuerpo = f"""Hola {CLIENTE_NOMBRE},

¡Tu pedido de RedaXion está listo! 🚀

Puedes descargar tus documentos desde los siguientes enlaces:

📄 Documento Final (PDF):
{ARCHIVOS['documento_pdf']}

📝 Documento Editable (DOCX):
{ARCHIVOS['documento_docx']}

📚 Quiz de Repaso (PDF):
{ARCHIVOS['quiz_pdf']}

📝 Quiz Editable (DOCX):
{ARCHIVOS['quiz_docx']}

También puedes ver tu orden en tu dashboard:
{BASE_URL}/dashboard?external_reference={ORDEN_ID}

¡Gracias por confiar en RedaXion!
Equipo RedaXion.
"""

    print(f"📧 Enviando correo a {CLIENTE_EMAIL}...")
    print(f"📦 Orden ID: {ORDEN_ID}")
    print(f"👤 Cliente: {CLIENTE_NOMBRE}")
    print()
    
    try:
        enviar_correo_con_adjuntos(
            destinatario=CLIENTE_EMAIL,
            asunto=f"¡Tu RedaXion está lista! - Orden #{ORDEN_ID[:8]}",
            cuerpo=cuerpo,
            lista_archivos=[]  # Sin adjuntos, solo links
        )
        print("✅ ¡Correo enviado exitosamente!")
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")
        print("\n📋 Copia este mensaje y envíalo manualmente:")
        print("="*60)
        print(f"Para: {CLIENTE_EMAIL}")
        print(f"Asunto: ¡Tu RedaXion está lista! - Orden #{ORDEN_ID[:8]}")
        print("-"*60)
        print(cuerpo)
        print("="*60)

if __name__ == "__main__":
    enviar_correo()
