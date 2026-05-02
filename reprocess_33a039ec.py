"""
Script de reprocesamiento de emergencia.
Orden: 33a039ec-51c6-4eb2-93b8-28fd31c7c5ef
Clase 17 - Miocardio y Electrofisiología Cardíaca

Para: yarineira0311@gmail.com (principal)
BCC:  admin@redaxiontcp.com | chris.rodval@gmail.com
"""

import os, sys

# ── Cargar variables de entorno ──────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# Forzar directorio correcto para rutas relativas (static/generated, etc.)
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── Imports del proyecto ─────────────────────────────────────────────────────
from services.transcription import transcribir_audio
from services.text_processing import procesar_txt_con_chatgpt
from services.formatting import guardar_como_docx, convert_to_pdf
from services.quiz_generation import generar_quiz_desde_docx
from services.formatting import guardar_quiz_como_docx
from services.delivery import enviar_correo_con_adjuntos
from services.storage import upload_file_to_gcs

# ── Parámetros de la orden ───────────────────────────────────────────────────
ORDEN_ID       = "33a039ec-51c6-4eb2-93b8-28fd31c7c5ef"
AUDIO_URL      = (
    "https://storage.googleapis.com/redaxion_audios/"
    "33a039ec-51c6-4eb2-93b8-28fd31c7c5ef_Clase_17._P1_-_Miocardio_y_Electrofisiologia_Cardiaca_.m4a"
    "?X-Goog-Algorithm=GOOG4-RSA-SHA256"
    "&X-Goog-Credential=redaxion-uploader%40genuine-polymer-461218-j5.iam.gserviceaccount.com"
    "%2F20260501%2Fauto%2Fstorage%2Fgoog4_request"
    "&X-Goog-Date=20260501T235848Z"
    "&X-Goog-Expires=604800"
    "&X-Goog-SignedHeaders=host"
    "&X-Goog-Signature=5933feae3f9a13555273d76be7e93cc99051ac02d40466e6904be2fae146221902478341a9922b8986e2cd21febcea2a69cd334b45372ea861e61d5aadb64a91ab4b2fe502ccab2419932851c7ac68100399bdebd6ee69e271fedc40abe2f73b3997e9cbfba3240467ab2a56b1d1fd105ed754e47ee7d75d3130cd4252fd4c07e4e5bc4251b137f18e327ab640eea46e3637673b6681c050adeece58cc1d7b0b8ae31ea017546076b51b57a0aaf8550fc2f24611eec7827a2edc7b2727119bdcde23d20d3e7f37bcaa22e657d90320d09eb1675913f3759217e26072d4f61ba27c05f6803d09f72a15f53eee9304039be5de91c797bcd81dfa1b7d6b8ac15322"
)
COLOR        = "morado pastel"
COLUMNAS       = "una"
CLIENTE        = "Yarineira"

TO_EMAIL       = "yarineira0311@gmail.com"
BCC_EMAILS     = ["admin@redaxiontcp.com", "chris.rodval@gmail.com"]

os.makedirs("static/generated", exist_ok=True)

# ── Paths locales ────────────────────────────────────────────────────────────
nombre_doc   = "Clase_17_Miocardio_Electrofisiologia"
path_txt     = f"static/generated/{ORDEN_ID}.txt"
path_docx    = f"static/generated/RedaXion - El Fascinante Mundo de las Células Cardíacas.docx"
path_pdf     = f"static/generated/RedaXion - El Fascinante Mundo de las Células Cardíacas.pdf"
nombre_quiz  = f"RedaQuiz - El Fascinante Mundo de las Células Cardíacas.docx"
path_quiz    = f"static/generated/{nombre_quiz}"
path_quiz_pdf = f"static/generated/RedaQuiz - El Fascinante Mundo de las Células Cardíacas.pdf"


def main():
    print("\n" + "="*70)
    print(f"🔧 REPROCESAMIENTO: {ORDEN_ID}")
    print("="*70 + "\n")

    # ── 1. Transcripción ─────────────────────────────────────────────────────
    print("🎙️  Paso 1/5 — Leyendo transcripción completa de AssemblyAI...")
    with open("assembly_transcription.txt", "r", encoding="utf-8") as f:
        transcription_text = f.read()
    word_count = len(transcription_text.split())
    print(f"   ✅ Transcripción cargada: {word_count} palabras")

    # Guardar raw para el pipeline
    with open(path_txt, "w", encoding="utf-8") as f:
        f.write(transcription_text)
    print(f"   💾 Texto raw guardado en: {path_txt}")

    # ── 2. Procesamiento GPT ─────────────────────────────────────────────────
    print("\n🧠 Paso 2/5 — Procesando con GPT-4o...")
    texto_procesado = procesar_txt_con_chatgpt(path_txt)
    print(f"   ✅ Texto procesado: {len(texto_procesado.split())} palabras")

    # ── 3. Generar DOCX + PDF principal ─────────────────────────────────────
    print(f"\n📄 Paso 3/5 — Generando DOCX y PDF...")
    guardar_como_docx(texto_procesado, path_docx, color=COLOR, columnas=COLUMNAS)
    print(f"   ✅ DOCX guardado: {path_docx}")
    path_pdf_result = convert_to_pdf(path_docx, color=COLOR)
    if path_pdf_result:
        import shutil
        if path_pdf_result != path_pdf:
            shutil.copy(path_pdf_result, path_pdf)
    print(f"   ✅ PDF guardado: {path_pdf}")

    # ── 4. Generar Quiz ──────────────────────────────────────────────────────
    print(f"\n📝 Paso 4/5 — Generando Quiz...")
    preguntas_quiz = generar_quiz_desde_docx(path_docx)
    guardar_quiz_como_docx(preguntas_quiz, path_quiz, color=COLOR, columnas=COLUMNAS)
    path_quiz_pdf_result = convert_to_pdf(path_quiz, color=COLOR)
    if path_quiz_pdf_result:
        import shutil
        if path_quiz_pdf_result != path_quiz_pdf:
            shutil.copy(path_quiz_pdf_result, path_quiz_pdf)
    print(f"   ✅ Quiz DOCX: {path_quiz}")
    print(f"   ✅ Quiz PDF: {path_quiz_pdf}")

    # ── 5. Enviar correo ─────────────────────────────────────────────────────
    print(f"\n📧 Paso 5/5 — Enviando correo a {TO_EMAIL} (BCC: {BCC_EMAILS})...")

    archivos_adjuntos = []
    for p in [path_docx, path_quiz]:
        if p and os.path.exists(p):
            archivos_adjuntos.append(p)
    for p in [path_pdf, path_quiz_pdf]:
        if p and os.path.exists(p):
            archivos_adjuntos.append(p)

    cuerpo = f"""Hola {CLIENTE},

¡Tu pedido de RedaXion está listo! 🚀

Lamentamos la demora — hubo un inconveniente técnico con el procesamiento inicial de tu pedido. Hemos corregido el problema y generado nuevamente tu documento completo.

Adjuntamos los documentos generados:
  1. 📄 Documento Transcrito y Mejorado (PDF y DOCX editable)
  2. 📝 Quiz de Repaso (PDF y DOCX editable)

Clase: Clase 17 - Miocardio y Electrofisiología Cardíaca

Si tienes cualquier consulta, no dudes en escribirnos.

Gracias por confiar en nosotros.
Equipo RedaXion
"""

    enviar_correo_con_adjuntos(
        destinatario=TO_EMAIL,
        asunto=f"✅ [Recuperado] Tu RedaXion está lista - Miocardio y Electrofisiología",
        cuerpo=cuerpo,
        lista_archivos=archivos_adjuntos,
        bcc=BCC_EMAILS
    )

    print("\n" + "="*70)
    print("🎉 REPROCESAMIENTO COMPLETO")
    print(f"   📧 Enviado a: {TO_EMAIL}")
    print(f"   📨 BCC: {', '.join(BCC_EMAILS)}")
    print(f"   📎 Adjuntos: {len(archivos_adjuntos)} archivos")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
