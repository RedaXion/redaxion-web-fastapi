"""
Flow Payment Service - Integration with Flow Chile (flow.cl)

Provides functions to create payments and handle webhooks with Flow.
"""

import os
import hashlib
import hmac
from typing import Optional

# Try to import pyflowcl, fallback to mock if not installed
try:
    from pyflowcl import Payment
    from pyflowcl.Clients import ApiClient
    FLOW_AVAILABLE = True
except ImportError:
    FLOW_AVAILABLE = False
    print("⚠️ pyflowcl no instalado. Usando mock para Flow.")


# Configuration
FLOW_API_URL = os.getenv("FLOW_API_URL", "https://www.flow.cl/api")
FLOW_SANDBOX_URL = "https://sandbox.flow.cl/api"


def get_flow_client():
    """Create and return a Flow API client."""
    api_key = os.getenv("FLOW_API_KEY")
    api_secret = os.getenv("FLOW_API_SECRET")
    
    if not api_key or not api_secret:
        print("⚠️ FLOW_API_KEY o FLOW_API_SECRET no configurados")
        return None
    
    # Use sandbox in development
    use_sandbox = os.getenv("FLOW_SANDBOX", "true").lower() == "true"
    api_url = FLOW_SANDBOX_URL if use_sandbox else FLOW_API_URL
    
    if not FLOW_AVAILABLE:
        return None
    
    return ApiClient(
        api_url=api_url,
        api_key=api_key,
        api_secret=api_secret,
    )


def crear_pago_flow(
    orden_id: str,
    monto: int,
    email: str,
    descripcion: str,
    url_retorno: str,
    url_confirmacion: str,
    optional_data: Optional[dict] = None
) -> dict:
    """
    Create a payment in Flow and return the checkout URL.
    
    Args:
        orden_id: Unique order identifier
        monto: Amount in CLP (integer, no decimals)
        email: Customer email
        descripcion: Payment description/subject
        url_retorno: URL to redirect after payment
        url_confirmacion: Webhook URL for payment confirmation
        optional_data: Additional data to include
        
    Returns:
        dict with checkout_url, flow_order, and token
    """
    client = get_flow_client()
    
    if not client:
        # Mock response for development
        print(f"🧪 [MOCK] Creando pago Flow: {orden_id} - ${monto} CLP")
        mock_token = f"mock_token_{orden_id[:8]}"
        return {
            "success": True,
            "checkout_url": f"{url_retorno}?external_reference={orden_id}&mock=true",
            "flow_order": f"mock_{orden_id[:8]}",
            "token": mock_token,
            "mock": True
        }
    
    try:
        # Sanitize description for Flow (remove newlines, limit length)
        clean_description = descripcion.replace('\n', ' ').replace('\r', '').strip()[:100]
        
        pago_data = {
            "subject": clean_description,
            "commerceOrder": orden_id,
            "amount": int(monto),
            "email": email,
            "urlConfirmation": url_confirmacion,
            "urlReturn": url_retorno,
        }
        
        # Add optional data if provided (must be JSON string for Flow)
        if optional_data:
            import json
            pago_data["optional"] = json.dumps(optional_data)
        
        print(f"💳 Creando pago Flow: {orden_id} - ${monto} CLP")
        resultado = Payment.create(client, pago_data)
        
        # pyflowcl returns a PaymentResponse object, access properties with dot notation
        checkout_url = f"{resultado.url}?token={resultado.token}"
        
        print(f"✅ Pago Flow creado: {resultado.flowOrder}")
        
        return {
            "success": True,
            "checkout_url": checkout_url,
            "flow_order": str(resultado.flowOrder),
            "token": str(resultado.token)
        }
        
    except Exception as e:
        print(f"❌ Error creando pago Flow: {e}")
        # Return error dict instead of raising exception to crash endpoint
        return {
            "success": False, 
            "error": f"Error comunicando con Flow: {str(e)}",
            "checkout_url": None,
            "mock": False
        }


def obtener_estado_pago(token: str) -> dict:
    """
    Get the status of a payment by token.
    NEVER raises exceptions - always returns a dict.
    """
    print(f"🔵 [NEW CODE] obtener_estado_pago called with token={token[:20]}...")
    
    client = get_flow_client()
    
    if not client:
        return {"status": 2, "statusStr": "PAGADA", "mock": True}
    
    # Try pyflowcl first, but ALWAYS fallback to manual on ANY error
    try:
        print(f"🔍 Trying pyflowcl getStatus...")
        resultado = Payment.getStatus(client, {"token": token.strip()})
        print(f"✅ pyflowcl succeeded")
        # Convert PaymentStatusResponse to dict if needed
        if hasattr(resultado, '__dict__'):
            return vars(resultado)
        return resultado
    except Exception as e:
        # Catch ALL exceptions including GenericError from pyflowcl
        error_msg = str(e)[:100] if str(e) else type(e).__name__
        print(f"⚠️ pyflowcl failed: {error_msg}")
        print(f"🔄 Switching to manual implementation...")
    
    # Always try manual method as fallback
    try:
        return obtener_estado_pago_manual(token)
    except Exception as e2:
        print(f"❌ Manual method also failed: {e2}")
        # Return a safe default that won't crash the webhook
        return {"error": str(e2), "status": 0}

def obtener_estado_pago_manual(token: str) -> dict:
    """Manual implementation of Flow getStatus to avoid library issues."""
    import httpx
    import hashlib
    import hmac
    
    api_key = os.getenv("FLOW_API_KEY")
    secret = os.getenv("FLOW_API_SECRET")
    use_sandbox = os.getenv("FLOW_SANDBOX", "true").lower() == "true"
    base_url = "https://sandbox.flow.cl/api" if use_sandbox else "https://www.flow.cl/api"
    
    # 1. Prepare parameters sorted alphabetically
    params = {
        "apiKey": api_key,
        "token": token
    }
    
    # 2. Generate signature string: key1value1key2value2...
    keys_sorted = sorted(params.keys())
    to_sign = "".join([f"{k}{params[k]}" for k in keys_sorted])
    
    # 3. Calculate HMAC SHA256
    signature = hmac.new(
        secret.encode('utf-8'),
        to_sign.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    params["s"] = signature
    
    print(f"🔐 Firma Manual Generada: {signature[:10]}... para string: {to_sign[:20]}...")
    
    try:
        url = f"{base_url}/payment/getStatus"
        with httpx.Client() as client:
            response = client.get(url, params=params)
            
        print(f"📡 Respuesta Flow Manual: {response.status_code}")
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error Flow API Manual: {response.text}")
            return {"error": f"Flow Error {response.status_code}: {response.text}"}
            
    except Exception as e:
        print(f"❌ Excepción manual Flow: {e}")
        return {"error": str(e)}
    """
    Verify the signature of a Flow webhook notification.
    
    Args:
        data: The data received in the webhook
        firma_recibida: The signature from Flow
        
    Returns:
        True if signature is valid, False otherwise
    """
    api_secret = os.getenv("FLOW_API_SECRET")
    
    if not api_secret:
        print("⚠️ No se puede verificar firma: FLOW_API_SECRET no configurado")
        return False
    
    # Sort keys and create string to sign
    sorted_keys = sorted(data.keys())
    to_sign = "&".join(f"{k}={data[k]}" for k in sorted_keys if k != "s")
    
    # Create HMAC-SHA256 signature
    firma_calculada = hmac.new(
        api_secret.encode(),
        to_sign.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(firma_calculada, firma_recibida)


# Payment status codes from Flow
FLOW_STATUS = {
    1: "pending",      # Pendiente de pago
    2: "completed",    # Pagada
    3: "rejected",     # Rechazada
    4: "cancelled",    # Anulada
}


def status_code_to_string(status_code: int) -> str:
    """Convert Flow status code to our internal status string."""
    return FLOW_STATUS.get(status_code, "unknown")
