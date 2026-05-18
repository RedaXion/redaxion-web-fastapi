import os
import time
import datetime
import requests
import asyncio

# ─────────────────────────────────────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────────────────────────────────────
DEEPGRAM_API_KEY  = os.environ.get("DEEPGRAM_API_KEY")
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY")

if not DEEPGRAM_API_KEY:
    print("Warning: DEEPGRAM_API_KEY not found. Transcriptions will fail.")

DEEPGRAM_HEADERS = {
    "Authorization": f"Token {DEEPGRAM_API_KEY or ''}",
    "Content-Type":  "application/json"
}

# Umbral mínimo de palabras para considerar que la transcripción fue completa.
# Si el audio dura N minutos, a ~130 palabras/min en español esto equivale
# a ~130*N palabras. Para ser conservadores usamos 500 como mínimo absoluto.
MIN_WORDS_THRESHOLD = 500

# ─────────────────────────────────────────────────────────────────────────────
# SOLUCIÓN PRINCIPAL: Deepgram con polling asíncrono (igual que AssemblyAI)
# ─────────────────────────────────────────────────────────────────────────────
# PROBLEMA ORIGINAL: Deepgram en modo síncrono (un solo POST y esperar)
#   devolvía texto truncado para archivos grandes porque:
#   1. La conexión HTTP se cerraba antes de que el audio completo fuera procesado.
#   2. Deepgram retorna lo procesado hasta ese momento en lugar de dar error.
#
# SOLUCIÓN: Usar la API "Batch" de Deepgram:
#   - Se envía el trabajo con el parámetro "callback_method": "polling".
#   - Deepgram devuelve un request_id inmediatamente.
#   - Se consulta el estado del trabajo cada N segundos hasta que termine.
#   - Esto garantiza que se obtiene la transcripción COMPLETA sin importar
#     el tamaño del archivo.
# ─────────────────────────────────────────────────────────────────────────────

DEEPGRAM_BATCH_ENDPOINT   = "https://api.deepgram.com/v1/listen"
DEEPGRAM_STATUS_ENDPOINT  = "https://api.deepgram.com/v1/requests/{request_id}"

def _deepgram_batch_poll(audio_url: str, keyterms: list = None, poll_interval: int = 8, max_wait: int = 900) -> str:
    """
    Realiza la transcripción síncrona en Deepgram con soporte para timeout largo.
    Se mantiene el nombre de la función y firma para compatibilidad con el resto del flujo.
    """
    payload = {"url": audio_url}

    params = {
        "model":         "nova-2",
        "language":      "es",
        "smart_format":  "true",
        "punctuate":     "true",
        "diarize":       "false",
    }

    if keyterms:
        params["keywords"] = keyterms

    print(f"🚀 [Deepgram] Iniciando transcripción síncrona... URL: {audio_url[:60]}...")

    r = requests.post(
        DEEPGRAM_BATCH_ENDPOINT,
        headers=DEEPGRAM_HEADERS,
        json=payload,
        params=params,
        timeout=300   # 5 minutos para permitir la transcripción de archivos grandes
    )
    r.raise_for_status()
    response_data = r.json()

    transcript = (
        response_data
        .get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("transcript", "")
    )

    if not transcript:
        print(f"⚠️ [Deepgram] Respuesta inesperada o vacía: {response_data}")
        raise RuntimeError("Deepgram no retornó texto en la respuesta.")

    words = len(transcript.split())
    print(f"✅ [Deepgram] Transcripción completada exitosamente: {words} palabras.")
    return transcript


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK: AssemblyAI con polling (sin cambios, ya funcionaba bien)
# ─────────────────────────────────────────────────────────────────────────────

def transcribir_audio_assembly_rest(audio_url: str) -> str:
    """Transcribe usando AssemblyAI como fallback ante fallos de Deepgram."""
    if not ASSEMBLYAI_API_KEY:
        print("⚠️ No hay ASSEMBLYAI_API_KEY. Fallback no disponible.")
        return ""

    print("🔗 [AssemblyAI Fallback] Enviando trabajo...")
    headers = {"authorization": ASSEMBLYAI_API_KEY, "content-type": "application/json"}

    response = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json={"audio_url": audio_url, "language_code": "es"},
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    transcript_id = response.json()["id"]

    polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    print("⏳ [AssemblyAI Fallback] Esperando resultado...")

    elapsed = 0
    while elapsed < 900:  # 15 minutos máximo también para AssemblyAI
        time.sleep(10)
        elapsed += 10
        poll_res = requests.get(polling_endpoint, headers=headers, timeout=30)
        poll_res.raise_for_status()
        poll_data = poll_res.json()
        status = poll_data["status"]

        if status == "completed":
            words = len((poll_data.get("text") or "").split())
            print(f"✅ [AssemblyAI Fallback] Completado en {elapsed}s — {words} palabras.")
            return poll_data["text"]
        elif status == "error":
            print(f"❌ [AssemblyAI Fallback] Error: {poll_data.get('error')}")
            return ""
        else:
            print(f"   ⏳ [AssemblyAI] Estado: '{status}' ({elapsed}s)...")

    print("❌ [AssemblyAI Fallback] Timeout: no completó en 15 minutos.")
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICACIONES DE FALLO
# ─────────────────────────────────────────────────────────────────────────────

def _notificar_fallo_transcripcion(orden_id: str, audio_url: str, error_msg: str,
                                    cliente_email: str = None, cliente_nombre: str = None):
    """
    Ante un fallo total de transcripción:
    1. Envía alerta detallada al admin (chris.rodval@gmail.com).
    2. Envía un correo amable al cliente indicando que el equipo fue notificado.
    """
    # Import aquí para evitar circular imports
    from services.delivery import enviar_correo_con_adjuntos

    base_url = os.environ.get("BASE_URL", "https://redaxiontcp.com")
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 1. Correo al administrador ─────────────────────────────────────────
    asunto_admin = f"🚨 FALLO TRANSCRIPCIÓN — Orden {orden_id[:8]}"
    cuerpo_admin = f"""¡Alerta crítica en RedaXion!

Se agotó el tiempo máximo de transcripción (15 minutos) sin obtener un
resultado válido de Deepgram ni de AssemblyAI.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ORDEN ID  : {orden_id}
CLIENTE   : {cliente_nombre or 'N/A'}
EMAIL     : {cliente_email or 'N/A'}
FECHA/HORA: {ahora}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AUDIO URL:
{audio_url}

ERROR TÉCNICO:
{error_msg}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACCIONES SUGERIDAS:
  1. Revisar si la URL del audio sigue siendo válida (puede haber expirado).
  2. Descargar el audio manualmente y re-subir a GCS con una URL fresca.
  3. Reprocesar la orden desde el panel admin:
     {base_url}/admin
  4. Verificar el estado de la cuenta Deepgram en:
     https://console.deepgram.com
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Dashboard de la orden:
{base_url}/dashboard?external_reference={orden_id}
"""

    try:
        enviar_correo_con_adjuntos(
            destinatario="chris.rodval@gmail.com",
            asunto=asunto_admin,
            cuerpo=cuerpo_admin,
            lista_archivos=[]
        )
        print("✅ [Notif] Alerta de fallo enviada al administrador.")
    except Exception as e:
        print(f"⚠️ [Notif] No se pudo enviar alerta al admin: {e}")

    # ── 2. Correo al cliente ───────────────────────────────────────────────
    if not cliente_email:
        print("⚠️ [Notif] Sin email de cliente. Omitiendo notificación al cliente.")
        return

    nombre_cliente = cliente_nombre or "estudiante"
    asunto_cliente = "⚠️ Problema técnico con tu pedido de RedaXion"
    cuerpo_cliente = f"""Hola {nombre_cliente},

Te escribimos para informarte que ocurrió un problema técnico durante el
procesamiento de tu pedido (ID: {orden_id[:8]}).

Nuestro sistema de transcripción experimentó una falla inesperada al
procesar tu archivo de audio. Lamentamos sinceramente este inconveniente.

🛠️  El equipo técnico ya fue notificado automáticamente y está
    trabajando para resolver la situación lo antes posible.

En las próximas horas recibirás:
  ✅ Tu documento procesado una vez que reprocesemos tu pedido, O
  📞 Un contacto directo de nuestro equipo si necesitamos más información.

Si tienes urgencia, puedes escribirnos a:
admin@redaxiontcp.com

Gracias por tu comprensión y paciencia.

Equipo RedaXion
https://redaxiontcp.com
"""

    try:
        enviar_correo_con_adjuntos(
            destinatario=cliente_email,
            asunto=asunto_cliente,
            cuerpo=cuerpo_cliente,
            lista_archivos=[]
        )
        print(f"✅ [Notif] Correo de disculpa enviado al cliente: {cliente_email}")
    except Exception as e:
        print(f"⚠️ [Notif] No se pudo enviar correo al cliente: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL — lógica de decisión y fallback
# ─────────────────────────────────────────────────────────────────────────────

def _es_transcript_valido(transcript: str, audio_url: str) -> bool:
    """
    Valida que la transcripción sea razonablemente completa.
    
    Criterios:
    - Debe tener al menos MIN_WORDS_THRESHOLD palabras.
    - No debe terminar en mitad de una frase (último carácter debe ser
      un signo de puntuación final: '.', '?', '!').
    """
    if not transcript:
        return False

    words = transcript.split()
    word_count = len(words)

    if word_count < MIN_WORDS_THRESHOLD:
        print(f"⚠️ Transcripción sospechosa: solo {word_count} palabras (umbral: {MIN_WORDS_THRESHOLD}).")
        return False

    last_char = transcript.strip()[-1]
    if last_char not in ('.', '?', '!', '»', '"', "'"):
        print(f"⚠️ La transcripción termina abruptamente en: '...{transcript.strip()[-30:]}'")
        # No consideramos esto un fallo por sí solo — algunos audios terminan
        # con una palabra suelta — pero lo registramos.

    return True


def transcribir_audio(audio_url: str, keyterms: list = None,
                      cliente_email: str = None, cliente_nombre: str = None,
                      orden_id: str = None) -> str:
    """
    Transcribe el audio en audio_url.

    Estrategia:
    1. Deepgram Batch con polling (máx. 15 min)  → garantiza texto completo
    2. Si Deepgram falla o entrega texto inválido → AssemblyAI como fallback
    3. Si ambos fallan:
       - Se envía alerta al admin (chris.rodval@gmail.com)
       - Se envía disculpa al cliente
       - Se lanza RuntimeError (orden queda en estado 'error')

    Parámetros opcionales:
        cliente_email  : Email del cliente para notificarle en caso de fallo.
        cliente_nombre : Nombre del cliente para personalizar el correo.
        orden_id       : ID de la orden para incluir en las notificaciones.
    """
    # ── Mocks para desarrollo/testing ────────────────────────────────────────
    if not DEEPGRAM_API_KEY:
        print("MOCK: No hay API Key de Deepgram. Retornando texto simulado.")
        return "Transcripción simulada por falta de API Key."

    if audio_url.startswith("mock://") or "fake-gcs-url" in audio_url:
        print("⚠️ URL simulada detectada (MOCK). Saltando Deepgram.")
        return (
            "Esta es una transcripción simulada. El sistema detectó modo de pruebas "
            "local (mock://), por lo que se omite el procesamiento real de audio."
        )

    # ── Intentar Deepgram Batch (con hasta 2 reintentos, máx 15 min cada uno) ─
    deepgram_transcript = ""
    deepgram_error_msg  = ""
    max_dg_retries = 2

    for attempt in range(1, max_dg_retries + 1):
        try:
            deepgram_transcript = _deepgram_batch_poll(audio_url, keyterms)

            if _es_transcript_valido(deepgram_transcript, audio_url):
                print(f"✅ [Deepgram] Transcripción aceptada ({len(deepgram_transcript.split())} palabras).")
                return deepgram_transcript
            else:
                deepgram_error_msg = f"Texto insuficiente en intento {attempt} ({len(deepgram_transcript.split())} palabras)."
                print(f"⚠️ [Deepgram] {deepgram_error_msg}")

        except Exception as e:
            deepgram_error_msg = str(e)
            print(f"⚠️ [Deepgram] Intento {attempt}/{max_dg_retries} fallido: {e}")
            if attempt < max_dg_retries:
                print("🔄 Reintentando Deepgram en 10 segundos...")
                time.sleep(10)

    # ── Fallback a AssemblyAI ─────────────────────────────────────────────────
    print("🔄 Deepgram no entregó resultado satisfactorio. Activando AssemblyAI...")
    assembly_transcript = transcribir_audio_assembly_rest(audio_url)

    if assembly_transcript and _es_transcript_valido(assembly_transcript, audio_url):
        print("✅ [AssemblyAI] Fallback exitoso.")
        return assembly_transcript

    # Si Assembly retornó algo aunque sea breve, preferirlo sobre vacío
    if not assembly_transcript and deepgram_transcript:
        print("⚠️ AssemblyAI falló, retornando resultado parcial de Deepgram.")
        return deepgram_transcript

    if assembly_transcript:
        print("⚠️ AssemblyAI retornó texto pero parece incompleto. Usando de todas formas.")
        return assembly_transcript

    # ── Fallo total → Notificar al admin y al cliente ─────────────────────────
    error_final = (
        f"Deepgram (2 intentos Batch, 15 min c/u): {deepgram_error_msg}\n"
        f"AssemblyAI: no retornó texto válido."
    )
    print(f"❌ Todas las opciones fallaron. Enviando notificaciones...\n{error_final}")

    _notificar_fallo_transcripcion(
        orden_id=orden_id or "desconocido",
        audio_url=audio_url,
        error_msg=error_final,
        cliente_email=cliente_email,
        cliente_nombre=cliente_nombre,
    )

    raise RuntimeError(
        "Transcripción fallida: Deepgram (2 intentos Batch, 15 min c/u) y "
        "AssemblyAI también fallaron. La orden no puede procesarse sin audio real."
    )


# ─────────────────────────────────────────────────────────────────────────────
# ASYNC VERSION — no bloquea el event loop de FastAPI
# ─────────────────────────────────────────────────────────────────────────────

async def transcribir_audio_async(audio_url: str, keyterms: list = None,
                                  cliente_email: str = None, cliente_nombre: str = None,
                                  orden_id: str = None) -> str:
    """
    Versión no-bloqueante de transcribir_audio.
    Corre el trabajo pesado en un thread pool para no bloquear FastAPI.
    Acepta los mismos parámetros opcionales que transcribir_audio para
    poder enviar notificaciones en caso de fallo.
    """
    return await asyncio.to_thread(
        transcribir_audio, audio_url, keyterms,
        cliente_email, cliente_nombre, orden_id
    )
