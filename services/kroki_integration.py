import os
import requests
from io import BytesIO
from typing import Optional
from openai import OpenAI
import re
from urllib.parse import quote
import zlib
import base64
import string

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
    
    prompt = f"""Convierte el siguiente texto explicativo en un diagrama de flujo en sintaxis Mermaid.js (flowchart).
REGLAS ESTRICTAS:
1. SOLO devuelve el código Mermaid puro, SIN bloques delimitadores de markdown (```).
2. Usa 'flowchart LR' (dirección horizontal de izquierda a derecha) OBLIGATORIAMENTE.
3. SE MINIMALISTA PERO COMPLETO: Extrae los 5 o 6 conceptos más importantes. Usa textos concisos (máximo 5 palabras por nodo) e incluye relaciones clave.
4. No uses comillas, paréntesis u otros caracteres especiales en los IDs de los nodos (usa IDs simples como A, B, C, etc.).
5. Si el texto del nodo (etiqueta) contiene caracteres especiales como acentos, comas o paréntesis, debes encerrarlo en comillas dobles obligatoriamente. Ejemplo: `A["Texto corto"]`.
6. El cliente ha solicitado que el diagrama use el color/tema: "{color_theme}". Genera un color hexadecimal primario (para los bordes) y un color secundario pastel (para el fondo) que representen este color.
7. Aplica el estilo de color generado a TODOS los nodos usando classDef. 
   Ejemplo: classDef default fill:#F9D4E8,stroke:#E32E91,stroke-width:2px,color:#000000;

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
            
        print(f"🎨 [Kroki Fallback] Renderizando imagen para el documento (usando mermaid.ink)...")
        
        import json
        state = {
            "code": mermaid_code,
            "mermaid": {"theme": "default"}
        }
        state_json = json.dumps(state)
        # mermaid.ink requiere base64 url-safe
        encoded_mermaid = base64.urlsafe_b64encode(state_json.encode('utf-8')).decode('utf-8')
        
        # Parámetros para mejor calidad y tamaño en el PDF
        url = f"https://mermaid.ink/img/{encoded_mermaid}?type=png&width=1200&scale=3"
        r = requests.get(url, timeout=50)
        
        if r.status_code == 200:
            print("✅ [Kroki Fallback] Gráfico generado con éxito en mermaid.ink.")
            return BytesIO(r.content)
        else:
            print(f"❌ [Kroki Fallback] Error de mermaid.ink: {r.status_code}")
            return None
    except Exception as e:
        print(f"❌ [Kroki Fallback] Excepción durante la generación: {e}")
        return None


def plantuml_encode(plantuml_text: str) -> str:
    """Compresses and encodes PlantUML text for use in a server URL."""
    utf8_text = plantuml_text.encode('utf-8')
    zlibbed_str = zlib.compress(utf8_text)[2:-4]
    plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
    base64_alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
    translator = bytes.maketrans(base64_alphabet.encode('utf-8'), plantuml_alphabet.encode('utf-8'))
    encoded = base64.b64encode(zlibbed_str).translate(translator)
    return encoded.decode('utf-8')


def generate_plantuml_official_visual(text: str) -> Optional[BytesIO]:
    """Generates a PlantUML diagram using the official server as a fallback."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY no configurada. Saltando PlantUML.")
        return None
        
    client = OpenAI(api_key=api_key)
    
    prompt = f"""Convierte el siguiente texto en un Diagrama de Actividades de PlantUML.
REGLAS ESTRICTAS:
1. SOLO devuelve el código PlantUML puro, SIN bloques delimitadores de markdown (```).
2. Empieza con @startuml y termina con @enduml.
3. Usa `skinparam shadowing false`, `skinparam dpi 300` y `left to right direction` justo después de @startuml.
4. Para dar color a CADA actividad, USA EXACTAMENTE ESTA SINTAXIS (el color va al final fuera de la actividad): `:Texto corto; <<#HexCode>>`
5. Usa una variedad de colores pastel (Verde: #DAEFD3, Rosado: #F9D4E8, Morado: #E8D4F9, Azul: #DCE5F0, Turquesa: #D4F9F5, Crema: #FDEBD0).
6. SE EXTREMADAMENTE MINIMALISTA: Extrae solo los 4 o 5 conceptos más importantes. Usa textos súper cortos (máximo 4 palabras por nodo).
7. Usa `stop` para finalizar el diagrama, NO uses `end`.

TEXTO A DIAGRAMAR:
{text}
"""
    print(f"🧠 [PlantUML Fallback] Solicitando código PlantUML a GPT-4o...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=600
        )
        
        plantuml_code = response.choices[0].message.content.strip()
        # Extract from @start to @end
        match = re.search(r'(@start\w+.*?@end\w+)', plantuml_code, re.DOTALL)
        if match:
            plantuml_code = match.group(1).strip()
            
        # Fix common GPT mistakes
        if plantuml_code.endswith("end"):
            plantuml_code = plantuml_code[:-3] + "stop"
            
        encoded = plantuml_encode(plantuml_code)
        url = f"http://www.plantuml.com/plantuml/png/{encoded}"
        
        print(f"🎨 [PlantUML Fallback] Descargando imagen desde el servidor oficial...")
        r = requests.get(url, timeout=30)
        
        if r.status_code == 200:
            print("✅ [PlantUML Fallback] Gráfico generado con éxito.")
            return BytesIO(r.content)
        else:
            print(f"❌ [PlantUML Fallback] Error del servidor PlantUML: {r.status_code}")
            return None
    except Exception as e:
        print(f"❌ [PlantUML Fallback] Excepción durante la generación: {e}")
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
