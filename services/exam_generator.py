"""
Exam Generator Service - Creates exams/tests using ChatGPT

Generates formal academic tests with:
- Multiple choice questions (a, b, c, d)
- Development/essay questions
- Separate answer key with justifications
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

3. ESTRUCTURA - DEBES GENERAR DOS SECCIONES SEPARADAS CON EL MARCADOR ===SOLUCIONARIO===:

PRIMERA PARTE (PRUEBA PARA EL ESTUDIANTE):

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

[Dejar espacio para respuesta]

[Continuar numerando...]

===SOLUCIONARIO===

SEGUNDA PARTE (SOLUCIONARIO PARA EL PROFESOR):

## SOLUCIONARIO - {asignatura.upper()}

**Tema:** {tema}

---

## SECCIÓN I: RESPUESTAS DE ALTERNATIVA

1. **Respuesta correcta: [LETRA])**
   **Justificación:** [Explicación detallada de por qué esta es la respuesta correcta y por qué las otras opciones son incorrectas. Mínimo 2-3 líneas.]

2. **Respuesta correcta: [LETRA])**
   **Justificación:** [Explicación detallada...]

[Continuar con todas las preguntas...]

---

## SECCIÓN II: RESPUESTAS DE DESARROLLO

1. **Respuesta modelo:**
   [Respuesta completa y detallada que serviría como ejemplo de respuesta perfecta]
   
   **Criterios de evaluación:**
   - [Criterio 1]: [X puntos]
   - [Criterio 2]: [X puntos]
   - [Criterio 3]: [X puntos]

[Continuar con todas las preguntas...]

4. REGLAS IMPORTANTES:
   - Las preguntas de alternativa deben tener UNA sola respuesta correcta
   - Los distractores (opciones incorrectas) deben ser plausibles
   - CADA respuesta de alternativa DEBE tener una justificación detallada
   - La dificultad {dificultad}/10 debe reflejarse en las preguntas
   - El marcador ===SOLUCIONARIO=== es OBLIGATORIO para separar las dos partes"""


def generar_prueba(tema: str, asignatura: str, nivel: str,
                   preguntas_alternativa: int, preguntas_desarrollo: int, 
                   dificultad: int = 7) -> dict:
    """
    Generate a formal test/exam using ChatGPT.
    
    Returns:
        dict with 'examen' (test for student), 'solucionario' (answer key), and 'success' status
    """
    
    if not client:
        print("MOCK: Generating test (No API Key)...")
        examen_mock = f"""## PRUEBA DE {asignatura.upper()}

**Tema:** {tema}
**Nombre del estudiante:** _______________________
**Fecha:** _______________________
**Puntaje:** _____ / 100

---

## SECCIÓN I: PREGUNTAS DE ALTERNATIVA

1. Pregunta de ejemplo sobre {tema}
   a) Opción A
   b) Opción B
   c) Opción C
   d) Opción D

---

## SECCIÓN II: PREGUNTAS DE DESARROLLO

1. Explique los conceptos principales de {tema}. (20 puntos)
"""
        solucionario_mock = f"""## SOLUCIONARIO - {asignatura.upper()}

**Tema:** {tema}

---

## SECCIÓN I: RESPUESTAS DE ALTERNATIVA

1. **Respuesta correcta: C)**
   **Justificación:** Esta es una demostración. Conecte OpenAI para generar contenido real con justificaciones detalladas.

---

## SECCIÓN II: RESPUESTAS DE DESARROLLO

1. **Respuesta modelo:**
   Respuesta de demostración para {tema}.
   
   **Criterios de evaluación:**
   - Comprensión del tema: 10 puntos
   - Desarrollo de ideas: 10 puntos
"""
        return {
            "success": True,
            "examen": examen_mock,
            "solucionario": solucionario_mock
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
                {"role": "user", "content": f"Genera una prueba completa sobre: {tema}. Recuerda usar el marcador ===SOLUCIONARIO=== para separar la prueba del solucionario."}
            ],
            temperature=0.4,
            max_tokens=6000
        )
        
        contenido_completo = response.choices[0].message.content.strip()
        print("✅ Prueba generada exitosamente")
        
        # Split into exam and answer key
        if "===SOLUCIONARIO===" in contenido_completo:
            partes = contenido_completo.split("===SOLUCIONARIO===")
            examen = partes[0].strip()
            solucionario = partes[1].strip() if len(partes) > 1 else ""
        else:
            # Fallback: try to split at "SOLUCIONARIO" or "PAUTA"
            if "## SOLUCIONARIO" in contenido_completo:
                idx = contenido_completo.find("## SOLUCIONARIO")
                examen = contenido_completo[:idx].strip()
                solucionario = contenido_completo[idx:].strip()
            elif "## PAUTA" in contenido_completo:
                idx = contenido_completo.find("## PAUTA")
                examen = contenido_completo[:idx].strip()
                solucionario = contenido_completo[idx:].strip()
            else:
                # Last resort: return everything as exam
                examen = contenido_completo
                solucionario = "## SOLUCIONARIO\n\n[No se pudo separar el solucionario automáticamente]"
        
        return {
            "success": True,
            "examen": examen,
            "solucionario": solucionario
        }
        
    except Exception as e:
        print(f"❌ Error generando prueba: {e}")
        return {
            "success": False,
            "error": str(e),
            "examen": None,
            "solucionario": None
        }
