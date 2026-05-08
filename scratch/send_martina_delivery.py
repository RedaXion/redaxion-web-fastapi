import os
import requests
import sys
from dotenv import load_dotenv

# Ensure we are in the right directory to import services
sys.path.append("/Users/christopherrodriguez/~:Code:RedaXionWeb/redaxion-web-fastapi")

from services.database import create_discount_code
from services.delivery import enviar_correo_con_adjuntos

load_dotenv()

# 1. Configuración
CLIENT_EMAIL = "martinahenriquez050@gmail.com"
CLIENT_NAME = "Martina"
ORDER_ID = "625ce564-f834-4ddf-a13b-b34e2aae8f4c"
DISCOUNT_CODE = "MARTINA-REDAXION80"

# 2. Crear Código de Descuento
print(f"🎟️ Creando código de descuento {DISCOUNT_CODE}...")
try:
    create_discount_code(
        code=DISCOUNT_CODE,
        discount_percent=80,
        max_uses=1,
        expiry_date="2026-12-31"
    )
    print("✅ Código creado con éxito.")
except Exception as e:
    print(f"⚠️ Error creando código (quizás ya existe): {e}")

# 3. Descargar Quiz desde GCS (para adjuntarlo)
QUIZ_URL = "https://storage.googleapis.com/redaxion_audios/625ce564/Quiz-Tolerancia_Inmunitaria_Clave.pdf"
QUIZ_LOCAL_PATH = "/Users/christopherrodriguez/Desktop/Quiz_Tolerancia.pdf"

print("📥 Descargando Quiz desde GCS...")
r = requests.get(QUIZ_URL)
if r.status_code == 200:
    with open(QUIZ_LOCAL_PATH, 'wb') as f:
        f.write(r.content)
    print("✅ Quiz descargado.")
else:
    print(f"❌ Falló descarga de Quiz: {r.status_code}")
    QUIZ_LOCAL_PATH = None

# 4. Preparar Correo
DOC_LOCAL_PATH = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria_Con_Esquemas.pdf"

asunto = "🎁 Disculpas y Entrega de tus Documentos RedaXion - Fisiopatología"

cuerpo = f"""Hola {CLIENT_NAME},

Te escribo personalmente para hacerte entrega de los documentos de tu clase de Fisiopatología.

Primero que todo, quisiera pedirte mis más sinceras disculpas. Tuvimos un fallo crítico en nuestro sistema de generación de visuales debido a una saturación de nuestros servidores (un "colapso" técnico), lo que retrasó la entrega de tu pedido y nos obligó a realizar mantenimientos de emergencia.

Como solución para no hacerte esperar más, hemos implementado una versión especial de tu documento donde los esquemas visuales han sido incluidos al final del archivo. Lamentamos que no hayan quedado integrados entre el texto como es habitual, pero es la forma en que pudimos asegurar la fidelidad del contenido técnico tras el fallo del sistema.

Adjunto encontrarás:
1. Tu documento de estudio con esquemas visuales (Tolerancia Inmunitaria).
2. Tu Quiz de repaso personalizado.

En agradecimiento por tu paciencia y la confianza que has depositado en RedaXion, queremos compensarte con un código de descuento especial del 80% para tu próxima orden:

Código: {DISCOUNT_CODE}
(Válido por un uso, para que tu siguiente pedido te salga solo unos $300 pesos aprox).

Nuevamente, te agradecemos por elegirnos. Estamos trabajando para que esto no vuelva a ocurrir y esperamos que este material te sea de gran utilidad para tus estudios.

¡Mucho éxito en tus exámenes!

Atentamente,
El Equipo de RedaXion
"""

adjuntos = [DOC_LOCAL_PATH]
if QUIZ_LOCAL_PATH:
    adjuntos.append(QUIZ_LOCAL_PATH)

# 5. Enviar Correo
print(f"📧 Enviando correo a {CLIENT_EMAIL}...")
try:
    enviar_correo_con_adjuntos(
        destinatario=CLIENT_EMAIL,
        asunto=asunto,
        cuerpo=cuerpo,
        lista_archivos=adjuntos
    )
    print("✅ ¡Correo enviado exitosamente!")
except Exception as e:
    print(f"❌ Error al enviar correo: {e}")
