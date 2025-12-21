"""
Napkin AI Integration Service for RedaXion

Provides visual generation using Napkin.ai API.
Replaces Unsplash and DALL-E as the sole image generation service.
"""

import os
import requests
import time
from io import BytesIO
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
NAPKIN_API_KEY = os.getenv("NAPKIN_API_KEY")
NAPKIN_API_URL = "https://api.napkin.ai"

# Rate limiting: Max 2 requests/second during developer preview
RATE_LIMIT_DELAY = 0.6  # seconds between requests (conservative)


def create_visual_request(content: str, language: str = "es-ES") -> Optional[str]:
    """
    Create a visual generation request with Napkin AI.
    
    Args:
        content: Text content to convert into a visual diagram
        language: BCP 47 language code (es-ES, en-US, etc.)
    
    Returns:
        Request ID if successful, None if failed
    """
    if not NAPKIN_API_KEY:
        print("⚠️ No NAPKIN_API_KEY configured. Skipping Napkin visual generation.")
        return None
    
    headers = {
        "Authorization": f"Bearer {NAPKIN_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "content": content,
        "format": "png",
        "language": language,
        "visual_query": "diagram",  # Request a diagram/scheme visualization
        "number_of_visuals": 1
    }
    
    try:
        print(f"🎨 Creando solicitud de visual en Napkin AI...")
        print(f"   URL: {NAPKIN_API_URL}/v1/visual")
        print(f"   Content length: {len(content)} chars")
        
        response = requests.post(
            f"{NAPKIN_API_URL}/v1/visual",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        # Log rate limit info
        if "x-ratelimit-remaining" in response.headers:
            remaining = response.headers.get("x-ratelimit-remaining")
            print(f"   Rate limit restante: {remaining}")
        
        print(f"   Status code: {response.status_code}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"   Response keys: {list(result.keys())}")
            request_id = result.get("id") or result.get("request_id")
            
            if request_id:
                print(f"✅ Solicitud creada: {request_id}")
                return request_id
            else:
                print(f"❌ No se obtuvo request_id en la respuesta")
                print(f"   Full response: {result}")
                return None
        else:
            print(f"❌ Error al crear visual: {response.status_code}")
            print(f"   Respuesta completa: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"❌ Timeout al crear visual en Napkin AI")
        return None
    except Exception as e:
        print(f"❌ Error inesperado al crear visual: {e}")
        import traceback
        traceback.print_exc()
        return None


def poll_visual_status(request_id: str, timeout: int = 60, poll_interval: float = 2.0) -> Optional[Dict[str, Any]]:
    """
    Poll the status of a visual generation request until completion or timeout.
    
    Args:
        request_id: The request ID from create_visual_request
        timeout: Maximum time to wait in seconds (default: 60)
        poll_interval: Time between status checks in seconds (default: 2.0)
    
    Returns:
        Status data with generated_files if successful, None if failed
    """
    if not NAPKIN_API_KEY:
        return None
    
    headers = {
        "Authorization": f"Bearer {NAPKIN_API_KEY}"
    }
    
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
                    print(f"✅ Visual generado exitosamente")
                    return status_data
                elif status == "failed":
                    print(f"❌ La generación del visual falló")
                    error_msg = status_data.get("error", "Unknown error")
                    print(f"   Error: {error_msg}")
                    return None
                elif status in ["pending", "processing"]:
                    # Continue polling
                    time.sleep(poll_interval)
                else:
                    print(f"⚠️ Estado desconocido: {status}")
                    time.sleep(poll_interval)
            else:
                print(f"❌ Error al verificar estado: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"❌ Timeout al verificar estado del visual")
            return None
        except Exception as e:
            print(f"❌ Error al verificar estado: {e}")
            return None
    
    print(f"⏱️ Timeout alcanzado después de {timeout}s")
    return None


def download_visual_file(file_url: str) -> Optional[BytesIO]:
    """
    Download a generated visual file from Napkin AI.
    
    Args:
        file_url: The URL of the generated file (from status response)
    
    Returns:
        BytesIO object with image data if successful, None if failed
    """
    if not NAPKIN_API_KEY:
        return None
    
    headers = {
        "Authorization": f"Bearer {NAPKIN_API_KEY}"
    }
    
    try:
        print(f"📥 Descargando visual de Napkin...")
        response = requests.get(file_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ Visual descargado ({len(response.content)} bytes)")
            return BytesIO(response.content)
        else:
            print(f"❌ Error al descargar visual: {response.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"❌ Timeout al descargar visual")
        return None
    except Exception as e:
        print(f"❌ Error al descargar visual: {e}")
        return None


def generate_napkin_visual(text: str, language: str = "es-ES") -> Optional[BytesIO]:
    """
    Complete workflow to generate a visual from text using Napkin AI.
    
    This is the main function to use for generating visuals.
    It handles the entire process: create request, poll status, download file.
    
    Args:
        text: Text content to convert into a visual
        language: BCP 47 language code (default: "es-ES" for Spanish)
    
    Returns:
        BytesIO object with PNG image data if successful, None if failed
    """
    if not NAPKIN_API_KEY:
        print("⚠️ No NAPKIN_API_KEY configurada. Saltando generación de visual.")
        return None
    
    # Validate input
    if not text or len(text.strip()) < 10:
        print("⚠️ Texto demasiado corto para generar visual")
        return None
    
    # Truncate if too long (Napkin might have limits)
    max_content_length = 2000
    if len(text) > max_content_length:
        text = text[:max_content_length] + "..."
        print(f"⚠️ Texto truncado a {max_content_length} caracteres")
    
    print(f"\n{'='*60}")
    print(f"🎨 GENERANDO VISUAL CON NAPKIN AI")
    print(f"{'='*60}")
    print(f"Contenido: {text[:100]}...")
    print(f"Idioma: {language}")
    print()
    
    # Step 1: Create visual request
    request_id = create_visual_request(text, language)
    if not request_id:
        return None
    
    # Respect rate limiting
    time.sleep(RATE_LIMIT_DELAY)
    
    # Step 2: Poll for completion
    status_data = poll_visual_status(request_id, timeout=60, poll_interval=3.0)
    if not status_data:
        return None
    
    # Step 3: Extract file URL
    generated_files = status_data.get("generated_files", [])
    if not generated_files:
        print("❌ No se generaron archivos")
        return None
    
    file_url = generated_files[0].get("url")
    if not file_url:
        print("❌ No se encontró URL del archivo")
        return None
    
    # Step 4: Download the file
    image_data = download_visual_file(file_url)
    
    if image_data:
        print(f"{'='*60}\n")
    
    return image_data
