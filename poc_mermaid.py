import os
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

texto_fuente = """Estructura de la Placenta
La placenta se asemeja a un disco y se divide en dos caras:
- Cara materna: Esta cara está orientada hacia la madre.
- Cara fetal: Esta cara está orientada hacia el feto.
La cara fetal se caracteriza por su conexión con los vasos de menor calibre, que son cruciales para el intercambio de
nutrientes, metabolitos y desechos. Este intercambio es vital para el desarrollo del feto."""

prompt = f"""Genera estrictamente el código Mermaid ('flowchart TD') para este texto.
REGLAS:
- No agregues comillas markdown (```) alrededor, SOLO devuelve la sintaxis pura de Mermaid.
- Usa colores suaves e institucionales (azules/pasteles) agregando comandos 'style'.
- Los nodos deben tener textos limpios y fáciles de leer.

TEXTO:
{texto_fuente}
"""

print("🧠 Solicitando Mermaid Code a OpenAI...")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.2
)

mermaid_code = response.choices[0].message.content.strip()
if mermaid_code.startswith("```mermaid"):
    mermaid_code = mermaid_code.split("```mermaid")[1].split("```")[0].strip()
elif mermaid_code.startswith("```"):
    mermaid_code = mermaid_code.split("```")[1].split("```")[0].strip()

print("📝 Mermaid Code Generado:\n", mermaid_code)

print("🎨 Renderizando imagen usando Kroki.io...")
# Kroki acepta peticiones POST con el texto plano de Mermaid
r = requests.post("https://kroki.io/mermaid/png", data=mermaid_code.encode('utf-8'))

if r.status_code == 200:
    desktop_path = os.path.expanduser("~/Desktop/Estructura_Placenta.png")
    with open(desktop_path, "wb") as f:
        f.write(r.content)
    print(f"✅ ¡Esquema generado y guardado en: {desktop_path}!")
else:
    print("❌ Error renderizando en Kroki:", r.text)

