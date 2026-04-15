import os
import requests
import time
import random
from io import BytesIO
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
NAPKIN_API_URL = "https://api.napkin.ai"

# Fallback chain: Primary → Backup 1 → Backup 2 → Backup 3
# Each entry: (account_name, api_key)
NAPKIN_ACCOUNTS = [
    ("Principal",   os.getenv("NAPKIN_API_KEY")),
    ("RXRESPALDO",  os.getenv("NAPKIN_API_KEY_BACKUP1")),
    ("RX2RESPALDO", os.getenv("NAPKIN_API_KEY_BACKUP2")),
    ("RX3RESPALDO", os.getenv("NAPKIN_API_KEY_BACKUP3")),
]

# Rate limiting
RATE_LIMIT_DELAY = 0.6  # seconds between requests

# Visual style variations
VISUAL_QUERIES = [
    "diagram",
    "flowchart",
    "mind map",
    "infographic",
    "concept map",
    "process flow",
    "hierarchy chart",
]


class NapkinCreditsExhausted(Exception):
    """Raised when a Napkin account returns 402 (insufficient credits)."""
    pass


def _create_visual_request(content: str, language: str, api_key: str) -> Optional[str]:
    """
    Create a visual generation request with a specific API key.

    Returns:
        request_id (str) if successful.
        None if any non-credit error occurred.

    Raises:
        NapkinCreditsExhausted if the account has no credits (402).
    """
    visual_style = random.choice(VISUAL_QUERIES)
    print(f"   🎲 Estilo visual: {visual_style}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "content": content,
        "format": "png",
        "language": language,
        "visual_query": visual_style,
        "number_of_visuals": 1
    }

    try:
        response = requests.post(
            f"{NAPKIN_API_URL}/v1/visual",
            headers=headers,
            json=payload,
            timeout=30
        )

        # Log rate limit info if available
        remaining = response.headers.get("x-ratelimit-remaining")
        if remaining:
            print(f"   Rate limit restante: {remaining}")

        print(f"   Status: {response.status_code}")

        if response.status_code == 402:
            # Credits exhausted — signal to try next account
            raise NapkinCreditsExhausted(f"Créditos agotados (402)")

        if response.status_code in [200, 201]:
            result = response.json()
            request_id = result.get("id") or result.get("request_id")
            if request_id:
                print(f"   ✅ Request creado: {request_id}")
                return request_id
            else:
                print(f"   ❌ No se obtuvo request_id. Respuesta: {result}")
                return None

        print(f"   ❌ Error HTTP {response.status_code}: {response.text[:200]}")
        return None

    except NapkinCreditsExhausted:
        raise  # propagate to caller
    except requests.exceptions.Timeout:
        print(f"   ❌ Timeout al crear solicitud")
        return None
    except Exception as e:
        print(f"   ❌ Error inesperado: {e}")
        return None


def _poll_visual_status(
    request_id: str,
    api_key: str,
    timeout: int = 60,
    poll_interval: float = 2.0
) -> Optional[Dict[str, Any]]:
    """
    Poll the status of a visual generation request.
    Returns status data on completion, None on failure/timeout.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    start_time = time.time()
    attempt = 0

    while (time.time() - start_time) < timeout:
        attempt += 1
        try:
            response = requests.get(
                f"{NAPKIN_API_URL}/v1/visual/{request_id}/status",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                status_data = response.json()
                status = status_data.get("status")
                print(f"   [{attempt}] Estado: {status}")

                if status == "completed":
                    print(f"   ✅ Visual generado")
                    return status_data
                elif status == "failed":
                    print(f"   ❌ Generación fallida: {status_data.get('error', 'unknown')}")
                    return None
                elif status in ["pending", "processing"]:
                    time.sleep(poll_interval)
                else:
                    print(f"   ⚠️ Estado desconocido: {status}")
                    time.sleep(poll_interval)
            else:
                print(f"   ❌ Error al verificar estado: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            print(f"   ❌ Timeout verificando estado")
            return None
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None

    print(f"   ⏱️ Timeout alcanzado ({timeout}s)")
    return None


def _download_visual(file_url: str, api_key: str) -> Optional[BytesIO]:
    """Download a generated visual file."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(file_url, headers=headers, timeout=30)
        if response.status_code == 200:
            print(f"   📥 Visual descargado ({len(response.content)} bytes)")
            return BytesIO(response.content)
        print(f"   ❌ Error descargando visual: {response.status_code}")
        return None
    except requests.exceptions.Timeout:
        print(f"   ❌ Timeout descargando visual")
        return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def _try_generate_with_key(text: str, language: str, api_key: str) -> Optional[BytesIO]:
    """
    Try to generate a visual with a specific API key.
    Returns image BytesIO on success, None on failure.
    Propagates NapkinCreditsExhausted so the caller can try the next account.
    """
    # Step 1: Create request (may raise NapkinCreditsExhausted)
    request_id = _create_visual_request(text, language, api_key)
    if not request_id:
        return None

    # Respect rate limiting
    time.sleep(RATE_LIMIT_DELAY)

    # Step 2: Poll for completion
    status_data = _poll_visual_status(request_id, api_key, timeout=60, poll_interval=3.0)
    if not status_data:
        return None

    # Step 3: Extract file URL
    generated_files = status_data.get("generated_files", [])
    if not generated_files:
        print("   ❌ No se generaron archivos")
        return None

    file_url = generated_files[0].get("url")
    if not file_url:
        print("   ❌ No se encontró URL del archivo")
        return None

    # Step 4: Download
    return _download_visual(file_url, api_key)


def generate_napkin_visual(text: str, language: str = "es-ES") -> Optional[BytesIO]:
    """
    Generate a visual from text using Napkin AI with automatic fallback.

    Tries accounts in order: Principal → RXRESPALDO → RX2RESPALDO → RX3RESPALDO.
    Switches to the next account automatically on 402 (credits exhausted).

    Returns:
        BytesIO with PNG image data, or None if all accounts fail.
    """
    # Validate input
    if not text or len(text.strip()) < 10:
        print("⚠️ Texto demasiado corto para generar visual")
        return None

    # Truncate if needed
    max_length = 1500
    if len(text) > max_length:
        text = text[:max_length] + "..."
        print(f"⚠️ Texto truncado a {max_length} caracteres para ahorrar créditos")


    # Filter to only accounts that have a key configured
    active_accounts = [(name, key) for name, key in NAPKIN_ACCOUNTS if key]

    if not active_accounts:
        print("⚠️ No hay NAPKIN_API_KEY configurada. Saltando generación de visual.")
        return None

    print(f"\n{'='*60}")
    print(f"🎨 GENERANDO VISUAL CON NAPKIN AI")
    print(f"{'='*60}")
    print(f"Cuentas disponibles: {[n for n, _ in active_accounts]}")
    print(f"Contenido: {text[:80]}...")
    print(f"Idioma: {language}\n")

    for account_name, api_key in active_accounts:
        print(f"🔑 Intentando con cuenta: {account_name}")
        try:
            image_data = _try_generate_with_key(text, language, api_key)
            if image_data:
                print(f"✅ Visual generado con cuenta: {account_name}")
                print(f"{'='*60}\n")
                return image_data
            else:
                print(f"⚠️ {account_name} falló (error no relacionado con créditos). Siguiente cuenta...")
                continue

        except NapkinCreditsExhausted:
            print(f"💳 {account_name}: créditos agotados → pasando a siguiente cuenta...")
            continue
        except Exception as e:
            print(f"❌ Error inesperado con {account_name}: {e}")
            continue

    print("❌ Todas las cuentas de Napkin fallaron. El documento se generará sin visual.")
    print(f"{'='*60}\n")
    return None
