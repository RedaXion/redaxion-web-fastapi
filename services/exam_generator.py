"""
Exam Generator Service - Creates exams/tests using ChatGPT

Generates formal academic tests with:
- Multiple choice questions (a, b, c, d)
- Development/essay questions
- Answer key
"""

import os
from openai import OpenAI

# Initialize client
client = None
if os.getenv("OPENAI_API_KEY"):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
else:
    print("Warning: OPENAI_API_KEY not found. Test generation will fail.")


def get_exam_generation_prompt(tema: str, asignatura: str, nivel: str, 
                                preguntas_alternativa: int, preguntas_desarrollo: int, 
                                dificultad: int) -> str:
    """Generate the system prompt for test creation."""
    
    dificultad_desc = {
        1: "muy fácil, para principiantes absolutos",
        2: "fácil, conceptos básicos",
        3: "fácil-moderado",
        4: "moderado, requiere comprensión básica",
        5: "moderado, nivel estándar de evaluación",
        6: "moderado-difícil",
        7: "difícil, requiere comprensión profunda",
        8: "difícil, preguntas de análisis",
        9: "muy difícil, nivel avanzado",
        10: "extremadamente difícil, nivel experto"
    }
    
    nivel_dificultad = dificultad_desc.get(dificultad, "moderado")
    
    return f"""Eres un profesor experto en {asignatura} creando una prueba formal para nivel {nivel}.

INSTRUCCIONES ESTRICTAS:

1. FORMATO DE SALIDA:
   - Usa SOLO texto plano con encabezados marcados con ##
   - Usa **texto** para negritas en palabras clave
   - NO uses tablas, NO uses formato Markdown complejo
   - El formato debe ser limpio y formal, como una prueba impresa

2. CONTENIDO:
   - Tema: {tema}
   - Asignatura: {asignatura}
   - Nivel: {nivel}
   - Dificultad: {dificultad}/10 ({nivel_dificultad})

3. ESTRUCTURA OBLIGATORIA:

## PRUEBA DE {asignatura.upper()}

**Tema:** {tema}
**Nombre del estudiante:** _______________________
**Fecha:** _______________________
**Puntaje:** _____ / [puntaje total]

---

## SECCIÓN I: PREGUNTAS DE ALTERNATIVA ({preguntas_alternativa} preguntas)

Instrucciones: Encierra en un círculo la alternativa correcta.

1. [Pregunta clara y precisa]
   a) [Opción]
   b) [Opción]
   c) [Opción]
   d) [Opción]

[Continuar numerando...]

---

## SECCIÓN II: PREGUNTAS DE DESARROLLO ({preguntas_desarrollo} preguntas)

Instrucciones: Responde de forma completa y fundamentada.

1. [Pregunta que requiere análisis o explicación] (X puntos)

[Continuar numerando...]

---

## PAUTA DE RESPUESTAS

**Sección I - Alternativas:**
1. [letra correcta] - [breve justificación]
2. [letra correcta] - [breve justificación]
...

**Sección II - Desarrollo:**
1. [Respuesta modelo o criterios de evaluación]
...

4. REGLAS:
   - Las preguntas de alternativa deben tener UNA sola respuesta correcta
   - Los distractores (opciones incorrectas) deben ser plausibles
   - Las preguntas de desarrollo deben requerir análisis, no solo memorización
   - Incluye el puntaje de cada pregunta de desarrollo
   - La dificultad {dificultad}/10 debe reflejarse en la complejidad de las preguntas

5. CALIDAD:
   - Preguntas claras sin ambigüedades
   - Contenido académicamente preciso
   - Vocabulario apropiado para el nivel {nivel}
   - Balance entre diferentes aspectos del tema"""


def generar_prueba(tema: str, asignatura: str, nivel: str,
                   preguntas_alternativa: int, preguntas_desarrollo: int, 
                   dificultad: int = 7) -> dict:
    """
    Generate a formal test/exam using ChatGPT.
    
    Args:
        tema: The topic/content the test should cover
        asignatura: Subject type (e.g., Historia, Matemáticas)
        nivel: Educational level (e.g., 4to Medio, Universidad)
        preguntas_alternativa: Number of multiple choice questions
        preguntas_desarrollo: Number of development/essay questions
        dificultad: Difficulty level 1-10 (default 7)
    
    Returns:
        dict with 'contenido' (full test content) and 'success' status
    """
    
    if not client:
        print("MOCK: Generating test (No API Key)...")
        return {
            "success": True,
            "contenido": f"""## PRUEBA DE {asignatura.upper()}

**Tema:** {tema}
**Nombre del estudiante:** _______________________
**Fecha:** _______________________
**Puntaje:** _____ / 100

---

## SECCIÓN I: PREGUNTAS DE ALTERNATIVA

[Esta es una prueba de demostración - Conecte OpenAI para generar contenido real]

1. Pregunta de ejemplo sobre {tema}
   a) Opción A
   b) Opción B
   c) Opción C
   d) Opción D

---

## SECCIÓN II: PREGUNTAS DE DESARROLLO

1. Explique los conceptos principales de {tema}. (20 puntos)

---

## PAUTA DE RESPUESTAS

**Sección I:** 1. c)
**Sección II:** [Respuesta modelo]
"""
        }
    
    try:
        system_prompt = get_exam_generation_prompt(
            tema, asignatura, nivel,
            preguntas_alternativa, preguntas_desarrollo, dificultad
        )
        
        print(f"🧠 Generando prueba: {asignatura} - {tema} (Dificultad: {dificultad}/10)")
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Genera una prueba completa sobre: {tema}"}
            ],
            temperature=0.4,
            max_tokens=4000
        )
        
        contenido = response.choices[0].message.content.strip()
        print("✅ Prueba generada exitosamente")
        
        return {
            "success": True,
            "contenido": contenido
        }
        
    except Exception as e:
        print(f"❌ Error generando prueba: {e}")
        return {
            "success": False,
            "error": str(e),
            "contenido": None
        }
