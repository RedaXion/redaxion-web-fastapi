"""
kroki_integration.py — Sistema robusto de generación de esquemas visuales.

Jerarquía de generación (Kroki como primario):

  1. Mermaid via mermaid.ink  (rápido, gratis, sin auth)
  2. Mermaid via kroki.io     (fallback renderer, gratis, sin auth)
  3. PlantUML via plantuml.com (fallback de tipo diferente)
  4. Napkin AI                (último recurso — costoso, en formatting.py)

Robustez implementada:
  - Sanitización automática del código Mermaid generado por GPT.
  - Validación de PNG antes de retornar (evita pasar HTML de error a python-docx).
  - Auto-simplificación: si el primer intento de renderizado falla (400),
    se pide a GPT un diagrama más simple y se reintenta.
  - Múltiples renderers para el mismo diagrama Mermaid.
  - Todos los timeouts son explícitos y conservadores.
"""

import os
import json
import re
import zlib
import base64
import string
import requests
from io import BytesIO
from typing import Optional
from openai import OpenAI

# ---------------------------------------------------------------------------
# Color palette mapping
# ---------------------------------------------------------------------------
COLOR_MAP = {
    "azul elegante":  ("#4A66AC", "#D8DFEF"),
    "azul pastel":    ("#4F81BD", "#DCE5F0"),
    "rojo elegante":  ("#C10905", "#FFBFBF"),
    "rojo pastel":    ("#E32E91", "#F9D4E8"),
    "gris elegante":  ("#7F7F7F", "#E5E5E5"),
    "morado pastel":  ("#B553D9", "#D094E6"),
    "verde pastel":   ("#569F3B", "#DAEFD3"),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_png(data: bytes) -> bool:
    """Verifica que los bytes sean un PNG real (magic bytes correctos)."""
    return data[:8] == b'\x89PNG\r\n\x1a\n'


def _clean_mermaid_code(raw: str) -> str:
    """
    Limpia y sanitiza el código Mermaid generado por GPT.
    - Elimina bloques de markdown (```mermaid ... ```)
    - Elimina líneas vacías al inicio/fin
    - Escapa etiquetas de nodo que contienen caracteres especiales sin comillas
    """
    code = raw.strip()

    # Eliminar bloques de markdown
    if "```" in code:
        match = re.search(r"```(?:mermaid)?\s*([\s\S]*?)```", code)
        if match:
            code = match.group(1).strip()

    # Asegurar que las etiquetas con caracteres especiales estén entre comillas dobles.
    # Patrón: A[texto con (paréntesis) o acentos] → A["texto con (paréntesis) o acentos"]
    # Solo aplica cuando la etiqueta NO ya tiene comillas.
    def quote_node_label(m):
        bracket = m.group(1)   # '[' o '(' o '{'
        content = m.group(2)
        close   = m.group(3)   # ']' o ')' o '}'
        # Si ya tiene comillas, no tocar
        if content.startswith('"') or content.startswith("'"):
            return f"{bracket}{content}{close}"
        # Si contiene caracteres que rompen Mermaid, envolver en comillas
        if re.search(r'[(),:;{}#\[\]]', content):
            content = content.replace('"', "'")  # escapar comillas internas
            return f'{bracket}"{content}"{close}'
        return m.group(0)

    code = re.sub(r'(\[)([^\[\]"\']+?)(\])', quote_node_label, code)

    return code.strip()


def _mermaid_to_base64(mermaid_code: str) -> str:
    """Codifica el código Mermaid en base64 url-safe para mermaid.ink."""
    state = {"code": mermaid_code, "mermaid": {"theme": "default"}}
    return base64.urlsafe_b64encode(json.dumps(state).encode("utf-8")).decode("utf-8")


def plantuml_encode(plantuml_text: str) -> str:
    """Comprime y codifica texto PlantUML para la URL del servidor oficial."""
    utf8_text = plantuml_text.encode("utf-8")
    zlibbed_str = zlib.compress(utf8_text)[2:-4]
    plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + "-_"
    base64_alphabet   = string.ascii_uppercase + string.ascii_lowercase + string.digits + "+/"
    translator = bytes.maketrans(base64_alphabet.encode(), plantuml_alphabet.encode())
    encoded = base64.b64encode(zlibbed_str).translate(translator)
    return encoded.decode("utf-8")


# ---------------------------------------------------------------------------
# Mermaid Renderers (misma sintaxis, distintos servidores)
# ---------------------------------------------------------------------------

# Dimensiones máximas de salida para evitar diagramas imposibles de leer.
# El ancho base de renderizado de mermaid.ink se controla desde la URL.
# 800px de base con scale=2 → 1600px real, que luego python-docx escala al ancho del doc.
_MERMAID_INK_WIDTH = 800   # px base (no escalar a más — diagramas se vuelven ilegibles)
_MERMAID_INK_SCALE = 2     # escala de resolución (calidad)


def _render_mermaid_ink(mermaid_code: str) -> Optional[BytesIO]:
    """Renderiza Mermaid via mermaid.ink (primario)."""
    try:
        encoded = _mermaid_to_base64(mermaid_code)
        url = f"https://mermaid.ink/img/{encoded}?type=png&width={_MERMAID_INK_WIDTH}&scale={_MERMAID_INK_SCALE}"
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and _is_valid_png(r.content):
            print("   ✅ mermaid.ink: OK")
            return BytesIO(r.content)
        print(f"   ⚠️ mermaid.ink: status={r.status_code}")
        return None
    except Exception as e:
        print(f"   ⚠️ mermaid.ink: excepción — {e}")
        return None


def _render_kroki_io(mermaid_code: str) -> Optional[BytesIO]:
    """Renderiza Mermaid via kroki.io (fallback renderer)."""
    try:
        r = requests.post(
            "https://kroki.io/mermaid/png",
            data=mermaid_code.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        if r.status_code == 200 and _is_valid_png(r.content):
            print("   ✅ kroki.io: OK")
            return BytesIO(r.content)
        print(f"   ⚠️ kroki.io: status={r.status_code}")
        return None
    except Exception as e:
        print(f"   ⚠️ kroki.io: excepción — {e}")
        return None


def _try_render_mermaid(mermaid_code: str) -> Optional[BytesIO]:
    """
    Intenta renderizar código Mermaid usando múltiples backends.
    mermaid.ink → kroki.io
    """
    result = _render_mermaid_ink(mermaid_code)
    if result:
        return result
    print("   🔄 mermaid.ink falló → intentando kroki.io...")
    return _render_kroki_io(mermaid_code)


# ---------------------------------------------------------------------------
# GPT Mermaid Code Generator (con reintentos)
# ---------------------------------------------------------------------------

def _build_mermaid_prompt(text: str, color_theme: str, simplified: bool = False) -> str:
    primary, secondary = COLOR_MAP.get(color_theme.strip().lower(), ("#4A66AC", "#D8DFEF"))

    # Simplified = 4 nodos máx; normal = 5 nodos máx (aumento de complejidad del 5-10%)
    # Menos nodos → diagramas más compactos y legibles en el PDF.
    if simplified:
        complexity = (
            "Extrae SOLO los 4 conceptos esenciales. "
            "Texto de nodos: máximo 3 palabras simples, sin caracteres especiales."
        )
    else:
        complexity = (
            "Extrae exactamente 5 conceptos clave. No más de 5 nodos en total. "
            "Textos concisos: máximo 5 palabras por nodo."
        )

    return f"""Genera un diagrama de flujo en Mermaid.js para el texto académico dado.

REGLAS CRÍTICAS (si las incumples el renderizado falla):
1. Devuelve ÚNICAMENTE el código Mermaid. CERO texto adicional, CERO bloques ```.
2. Primera línea DEBE ser exactamente: flowchart LR
3. IDs de nodos: solo letras mayúsculas simples (A, B, C...). Sin números, sin guiones.
4. Etiquetas de nodos: SIEMPRE entre comillas dobles. Ejemplo: A["Texto del nodo"]
5. NUNCA uses paréntesis, llaves, corchetes ni caracteres especiales DENTRO de las etiquetas.
   Reemplaza: ( ) {{ }} [ ] por nada o por coma. Acentos sí están permitidos dentro de comillas.
6. Relaciones: solo usa --> o -- texto --> entre IDs simples.
7. {complexity}
8. Aplica estilo de color con classDef en la ÚLTIMA línea:
   classDef default fill:{secondary},stroke:{primary},stroke-width:2px,color:#000000;

TEXTO A DIAGRAMAR:
{text[:500]}
"""


def _generate_mermaid_with_gpt(text: str, color_theme: str, simplified: bool = False) -> Optional[str]:
    """Pide a GPT-4o-mini que genere código Mermaid. Retorna el código limpio o None."""
    prompt = _build_mermaid_prompt(text, color_theme, simplified)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",   # más rápido y barato que gpt-4o para esta tarea
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=400,
                timeout=20,
            )
            raw = response.choices[0].message.content.strip()
            return _clean_mermaid_code(raw)
        except Exception as e:
            print(f"   ⚠️ GPT Mermaid: excepción — {e}")
            pass

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        print("   🔄 Intentando con Claude para Mermaid...")
        try:
            import anthropic
            anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
                timeout=20
            )
            raw = response.content[0].text.strip()
            return _clean_mermaid_code(raw)
        except Exception as e:
            print(f"   ⚠️ Claude Mermaid: excepción — {e}")
            pass

    return None


# ---------------------------------------------------------------------------
# PlantUML (tipo de diagrama distinto, mayor diversidad visual)
# ---------------------------------------------------------------------------

def _build_plantuml_prompt(text: str, color_theme: str) -> str:
    primary, secondary = COLOR_MAP.get(color_theme.strip().lower(), ("#4A66AC", "#D8DFEF"))
    return f"""Genera un Diagrama de Clases simple en PlantUML para el texto académico dado.

REGLAS CRÍTICAS:
1. Devuelve ÚNICAMENTE el código PlantUML. CERO texto adicional, CERO bloques ```.
2. Empieza con @startuml y termina con @enduml.
3. Primera línea tras @startuml: skinparam shadowing false
4. Usa solo clases simples con campos cortos (sin métodos).
   Ejemplo:
   class "Concepto A" {{
     + Propiedad 1
     + Propiedad 2
   }}
5. Máximo 4 clases. Texto ultra corto (máximo 3 palabras por ítem).
6. Conéctalas con --> y etiquetas cortas.
7. Colorea con: skinparam classBackgroundColor {secondary}
                skinparam classBorderColor {primary}

TEXTO A DIAGRAMAR:
{text[:600]}
"""


def _generate_plantuml_with_gpt(text: str, color_theme: str) -> Optional[str]:
    prompt = _build_plantuml_prompt(text, color_theme)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=400,
                timeout=20,
            )
            raw = response.choices[0].message.content.strip()
            # Extraer bloque @startuml…@enduml
            match = re.search(r"(@startuml[\s\S]*?@enduml)", raw)
            return match.group(1).strip() if match else raw.strip()
        except Exception as e:
            print(f"   ⚠️ GPT PlantUML: excepción — {e}")
            pass

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        print("   🔄 Intentando con Claude para PlantUML...")
        try:
            import anthropic
            anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
                timeout=20
            )
            raw = response.content[0].text.strip()
            match = re.search(r"(@startuml[\s\S]*?@enduml)", raw)
            return match.group(1).strip() if match else raw.strip()
        except Exception as e:
            print(f"   ⚠️ Claude PlantUML: excepción — {e}")
            pass

    return None


def _render_plantuml(plantuml_code: str) -> Optional[BytesIO]:
    """Renderiza PlantUML usando el servidor oficial."""
    try:
        encoded = plantuml_encode(plantuml_code)
        url = f"https://www.plantuml.com/plantuml/png/{encoded}"
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and _is_valid_png(r.content):
            print("   ✅ plantuml.com: OK")
            return BytesIO(r.content)
        # plantuml.com devuelve a veces PNG de error con texto rojo — también es PNG válido
        # Solo rechazamos si no es PNG en absoluto
        if r.status_code == 200:
            print("   ⚠️ plantuml.com: respondió 200 pero no es PNG válido")
        else:
            print(f"   ⚠️ plantuml.com: status={r.status_code}")
        return None
    except Exception as e:
        print(f"   ⚠️ plantuml.com: excepción — {e}")
        return None


# ---------------------------------------------------------------------------
# API PÚBLICA: generate_kroki_visual
# ---------------------------------------------------------------------------

def generate_kroki_visual(text: str, color_theme: str = "azul elegante") -> Optional[BytesIO]:
    """
    Genera un esquema visual a partir de texto académico.

    Estrategia robusta (sin Napkin AI):
      1. Mermaid (GPT genera código) → mermaid.ink → kroki.io
      2. Si renderizado falla → simplificar Mermaid (GPT reintento) → mismos renderers
      3. PlantUML (GPT genera código) → plantuml.com → kroki.io

    Retorna BytesIO con PNG válido, o None si todo falla.
    """
    print(f"\n{'─'*60}")
    print(f"🎨 [Kroki] Generando esquema visual...")
    print(f"   Color: {color_theme}")

    # ── Intento 1: Mermaid normal ─────────────────────────────────────────
    print("   [1/3] Mermaid (normal)...")
    mermaid_code = _generate_mermaid_with_gpt(text, color_theme, simplified=False)
    if mermaid_code:
        result = _try_render_mermaid(mermaid_code)
        if result:
            print(f"{'─'*60}\n")
            return result

    # ── Intento 2: Mermaid simplificado (menos nodos, menos caracteres) ───
    print("   [2/3] Mermaid (simplificado)...")
    simple_code = _generate_mermaid_with_gpt(text, color_theme, simplified=True)
    if simple_code:
        result = _try_render_mermaid(simple_code)
        if result:
            print(f"{'─'*60}\n")
            return result

    # ── Intento 3: PlantUML ───────────────────────────────────────────────
    print("   [3/3] PlantUML...")
    plantuml_code = _generate_plantuml_with_gpt(text, color_theme)
    if plantuml_code:
        result = _render_plantuml(plantuml_code)
        if result:
            print(f"{'─'*60}\n")
            return result
        # PlantUML en kroki.io como último renderer
        print("   🔄 plantuml.com falló → intentando kroki.io (PlantUML)...")
        try:
            r = requests.post(
                "https://kroki.io/plantuml/png",
                data=plantuml_code.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=30,
            )
            if r.status_code == 200 and _is_valid_png(r.content):
                print("   ✅ kroki.io (PlantUML): OK")
                print(f"{'─'*60}\n")
                return BytesIO(r.content)
        except Exception as e:
            print(f"   ⚠️ kroki.io (PlantUML): excepción — {e}")

    print("   ❌ Todos los intentos Kroki fallaron. El documento continuará sin visual.")
    print(f"{'─'*60}\n")
    return None


# Mantener compatibilidad con imports existentes
def generate_plantuml_official_visual(text: str) -> Optional[BytesIO]:
    """Alias de compatibilidad. Usa generate_kroki_visual en su lugar."""
    return generate_kroki_visual(text)


# ---------------------------------------------------------------------------
# Generador de fórmulas matemáticas (sin cambios)
# ---------------------------------------------------------------------------

from urllib.parse import quote

def generate_math_visual(latex_equation: str) -> Optional[BytesIO]:
    """Genera una imagen PNG de una ecuación LaTeX usando CodeCogs."""
    if not latex_equation or not latex_equation.strip():
        return None

    print("🔢 Generando fórmula matemática visual...")

    equation = latex_equation.strip()
    equation = re.sub(r"^\$\$(.*?)\$\$$", r"\1", equation, flags=re.DOTALL)
    equation = re.sub(r"^\$(.*?)\$$",     r"\1", equation, flags=re.DOTALL)
    equation = equation.strip()

    encoded_eq = quote(f"\\dpi{{300}} \\bg_white \\Large \\color{{black}} {equation}")
    url = f"https://latex.codecogs.com/png.image?{encoded_eq}"

    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and _is_valid_png(r.content):
            print("✅ Fórmula matemática generada correctamente.")
            return BytesIO(r.content)
        print(f"❌ Error al generar fórmula matemática: {r.status_code}")
        return None
    except Exception as e:
        print(f"❌ Excepción generando fórmula matemática: {e}")
        return None
