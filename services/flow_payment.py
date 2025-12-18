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
        pago_data = {
            "subject": descripcion,
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
    
    Returns:
        dict with payment status information
    """
    client = get_flow_client()
    
    if not client:
        return {"status": 2, "statusStr": "PAGADA", "mock": True}
    
    try:
        # Debug Info
        print(f"🔍 Debug Flow getStatus - Token: '{token}'")
        print(f"🔍 Debug Flow Client URL: {client.api_url}")
        
        # Clean token just in case
        token = token.strip()
        
        resultado = Payment.getStatus(client, {"token": token})
        return resultado
    except Exception as e:
        print(f"❌ Error obteniendo estado de pago: {e}")
        return {"error": str(e)}


def verificar_firma_webhook(data: dict, firma_recibida: str) -> bool:
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
