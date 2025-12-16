# generar_quiz.py

import os
from openai import OpenAI
import docx
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Initialize responsibly
client = None
if os.getenv("OPENAI_API_KEY"):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extraer_texto_docx(path_docx):
    if not os.path.exists(path_docx):
        return ""
    doc = docx.Document(path_docx)
    texto = ""
    for para in doc.paragraphs:
        texto += para.text + "\n"
    return texto

def generar_quiz_desde_docx(path_docx):
    if not client:
        return "Pregunta 1: MOCK PREGUNTA (No API Key)\nA) Op1\nB) Op2\n\nRespuesta 1: A..."

    texto_base = extraer_texto_docx(path_docx)
    
    # Safety truncation to match token limits if text is massive?
    # For now utilizing raw text.
    if len(texto_base) > 100000:
        texto_base = texto_base[:100000]

    prompt = f"""
A partir del siguiente texto, genera 14 preguntas de práctica para reforzar el aprendizaje. Cada pregunta debe tener 5 alternativas (A–E), con solo una correcta. Alta complejidad, en caso de ser temas de medicina, que las preguntas sean tipo EUNACOM, máxima complejidad.

No muestres las respuestas inmediatamente. Deja al menos 15 líneas en blanco antes de la sección de respuestas.

Luego incluye la sección de respuestas en este formato:

Respuesta 1: B. Justificación breve…
Respuesta 2: C. Justificación breve…
…

El objetivo es evaluar comprensión profunda, discriminación conceptual, razonamiento lógico y aplicación práctica, con dificultad 8–9 de 10.

Escribe todo en español.

TEXTO:
{texto_base}
""".strip()

    try:
        print("📚 Enviando documento a GPT para generar preguntas...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Eres un experto en redacción de exámenes para estudiantes de medicina. Genera preguntas con base en el contenido dado."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print("❌ Error al generar RedaQuiz:", e)
        return "[ERROR al generar preguntas]"

# guardar_quiz_como_docx REMOVED - It was duplicated in formatting.py
