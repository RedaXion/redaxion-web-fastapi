import os
import requests
from io import BytesIO
from typing import Optional
from openai import OpenAI
import re
from urllib.parse import quote

# We map typical color strings to their primary Hex background to theme the Mermaid graph.
# If a color is not found, we default to the blue variant.
COLOR_MAP = {
    "azul elegante": ("#4A66AC", "#D8DFEF"),
    "azul pastel": ("#4F81BD", "#DCE5F0"),
    "rojo elegante": ("#C10905", "#FFBFBF"),
    "rojo pastel": ("#E32E91", "#F9D4E8"),
    "gris elegante": ("#7F7F7F", "#E5E5E5"),
    "morado pastel": ("#B553D9", "#D094E6"),
    "verde pastel": ("#569F3B", "#DAEFD3")
}

def generate_kroki_visual(text: str, color_theme: str = "azul elegante") -> Optional[BytesIO]:
    """Generates a Mermaid diagram representing the text concepts via GPT-4o, rendered by Kroki."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY no configurada. Saltando Kroki.")
        return None
        
    client = OpenAI(api_key=api_key)
    
    # Try to map color
    theme_key = color_theme.strip().lower()
    primary_bg, secondary_bg = COLOR_MAP.get(theme_key, ("#4A66AC", "#D8DFEF"))
    
    prompt = f"""Convierte el siguiente texto explicativo en un diagrama de flujo en sintaxis Mermaid.js (flowchart).
REGLAS ESTRICTAS:
1. SOLO devuelve el código Mermaid puro, SIN bloques delimitadores de markdown (```).
2. Si el contenido describe un proceso lineal de más de 4 pasos, usa 'flowchart LR' (horizontal). Si es jerárquico o corto, usa 'flowchart TD' (vertical).
3. No uses comillas, paréntesis u otros caracteres especiales en los IDs de los nodos.
4. Aplica el siguiente estilo de colores a TODOS los nodos usando classDef:
   classDef default fill:{secondary_bg},stroke:{primary_bg},stroke-width:2px,color:#000000;

TEXTO A DIAGRAMAR:
{text}
"""
    print(f"🧠 [Kroki Fallback] Solicitando código Mermaid a GPT-4o...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=600
        )
        
        mermaid_code = response.choices[0].message.content.strip()
        # Clean up possible markdown code blocks
        if mermaid_code.startswith("```mermaid"):
            mermaid_code = mermaid_code.split("```mermaid")[1].split("```")[0].strip()
        elif mermaid_code.startswith("```"):
            mermaid_code = mermaid_code.split("```")[1].split("```")[0].strip()
            
        print(f"🎨 [Kroki Fallback] Renderizando imagen para el documento...")
        r = requests.post("https://kroki.io/mermaid/png", data=mermaid_code.encode('utf-8'), timeout=15)
        
        if r.status_code == 200:
            print("✅ [Kroki Fallback] Gráfico generado con éxito.")
            return BytesIO(r.content)
        else:
            print(f"❌ [Kroki Fallback] Error de Kroki: {r.status_code}")
            return None
    except Exception as e:
        print(f"❌ [Kroki Fallback] Excepción durante la generación: {e}")
        return None


def generate_math_visual(latex_equation: str) -> Optional[BytesIO]:
    """Generates a clean Math Equation PNG using CodeCogs API/Endpoint."""
    if not latex_equation or not latex_equation.strip():
        return None
        
    print(f"🔢 Generando fórmula matemática visual...")
    
    # Strip any possible markdown math wrappers just in case
    equation = latex_equation.strip()
    equation = re.sub(r'^\$\$(.*?)\$\$$', r'\1', equation, flags=re.DOTALL)
    equation = re.sub(r'^\$(.*?)\$$', r'\1', equation, flags=re.DOTALL)
    equation = equation.strip()
    
    # Configure CodeCogs URL: \dpi{300} \bg_white \Large \color{black}
    # Double escaping curly braces for f-string
    encoded_eq = quote(f"\\dpi{{300}} \\bg_white \\Large \\color{{black}} {equation}")
    url = f"https://latex.codecogs.com/png.image?{encoded_eq}"
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            # CodeCogs natively returns a nice cropped PNG for equations
            print("✅ Fórmula matemática generada correctamente.")
            return BytesIO(r.content)
        else:
            print(f"❌ Error al generar fórmula matemática: {r.status_code}")
            return None
    except Exception as e:
        print(f"❌ Excepción generando fórmula matemática: {e}")
        return None
