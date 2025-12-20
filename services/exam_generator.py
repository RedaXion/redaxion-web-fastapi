"""
Exam Generator Service - Creates exams/tests using ChatGPT

Generates formal academic tests with:
- Multiple choice questions (a, b, c, d)
- Development/essay questions
- Separate answer key with justifications
- EUNACOM mode for medical clinical exams
"""

import os
from openai import OpenAI

# Initialize client
client = None
if os.getenv("OPENAI_API_KEY"):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
else:
    print("Warning: OPENAI_API_KEY not found. Test generation will fail.")


def generar_nombre_prueba(asignatura: str, tema: str, nivel: str) -> str:
    """Generate a short exam name using AI (max 4 words)."""
    
    if not client:
        # Fallback for no API key
        return f"Prueba {asignatura}"
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Genera un nombre corto y profesional para un examen. Máximo 4 palabras. Solo responde con el nombre, sin explicación."},
                {"role": "user", "content": f"Asignatura: {asignatura}\nTema: {tema}\nNivel: {nivel}"}
            ],
            temperature=0.7,
            max_tokens=20
        )
        nombre = response.choices[0].message.content.strip()
        # Remove quotes if present
        nombre = nombre.strip('"\'')
        print(f"📝 Nombre de prueba generado: {nombre}")
        return nombre
    except Exception as e:
        print(f"⚠️ Error generando nombre: {e}")
        return f"Prueba {asignatura}"


def get_eunacom_prompt(tema: str, asignatura: str, preguntas_alternativa: int = 10, preguntas_desarrollo: int = 0) -> str:
    """Get the EUNACOM-style exam generation prompt."""
    
    return f"""Eres un generador de preguntas para el examen EUNACOM, orientado a evaluar competencias clínicas de un médico general en Chile.
Debes basarte exclusivamente en casos clínicos, siguiendo el formato, nivel de dificultad y estilo de las preguntas oficiales disponibles en:
https://www.eunacom.cl/contenidos/muestra.html

Debes respetar el Perfil de Conocimientos EUNACOM, especialmente el área de {asignatura}.

⚠️ CANTIDAD OBLIGATORIA:
- DEBES generar EXACTAMENTE {preguntas_alternativa} preguntas de alternativa (casos clínicos)
- DEBES generar EXACTAMENTE {preguntas_desarrollo} preguntas de desarrollo (si aplica)
- NO generes menos preguntas. Numera cada pregunta del 1 al {preguntas_alternativa}.

INSTRUCCIONES GENERALES

Cada pregunta debe tener su propio caso clínico, de 4 a 6 líneas, clínicamente realista.

Formato compacto sin espacios excesivos entre preguntas.

El nivel de dificultad debe oscilar entre 6/10 y 7/10.

Usar lenguaje médico habitual en atención primaria chilena.

No incluir respuestas ni explicaciones en el examen.

CONTENIDO CLÍNICO

Las preguntas deben abarcar patologías frecuentes del perfil EUNACOM en {asignatura}, relacionadas con el tema: {tema}.

CONSTRUCCIÓN DE LOS CASOS

Incluir distractores clínicos habituales que confundan el diagnóstico (edad, comorbilidades, fármacos, síntomas superpuestos).

Incorporar cuando corresponda:
- Valores de laboratorio (VSG, PCR, ANA, FR, anti-CCP, ácido úrico, hemograma, etc.)
- Descripciones imagenológicas (radiografía, RM, densitometría).

Evitar diagnósticos "demasiado obvios".

TIPO DE PREGUNTAS (UNA POR CASO)

Cada pregunta debe evaluar solo uno de los siguientes enfoques (distribuidos libremente):
- Diagnóstico más probable
- Tratamiento inicial
- Exámenes diagnósticos iniciales
- Examen confirmatorio
- Seguimiento en atención primaria
- Criterios de derivación a especialista

FORMATO DE RESPUESTA

## EXAMEN EUNACOM - {asignatura.upper()}

**Tema:** {tema}
**Nombre:** _______________________  **Fecha:** _______________

1. [Caso clínico 4-6 líneas]
   ¿Cuál es el diagnóstico/tratamiento/examen más probable?
a) [Opción]
b) [Opción]
c) [Opción]
d) [Opción]

2. [Siguiente caso clínico...]
a) [Opción]
b) [Opción]
c) [Opción]
d) [Opción]

[CONTINÚA HASTA LA PREGUNTA {preguntas_alternativa}]

===SOLUCIONARIO===

## SOLUCIONARIO EUNACOM

1. **Respuesta: [LETRA])** 
   **Diagnóstico:** [Nombre]
   **Justificación:** [Por qué es correcta, 2-3 líneas]

[CONTINÚA HASTA LA PREGUNTA {preguntas_alternativa}]

RESTRICCIONES IMPORTANTES

❌ No usar líneas horizontales (---)
❌ No usar espacios excesivos entre preguntas
❌ No usar notación LaTeX
❌ Usar símbolos Unicode: ² ³ ₂ etc."""


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

⚠️ CANTIDAD OBLIGATORIA DE PREGUNTAS:
- DEBES generar EXACTAMENTE {preguntas_alternativa} preguntas de alternativa (numeradas del 1 al {preguntas_alternativa})
- DEBES generar EXACTAMENTE {preguntas_desarrollo} preguntas de desarrollo (numeradas del 1 al {preguntas_desarrollo})
- NO generes menos preguntas. El usuario pagó por esta cantidad específica.

FORMATO COMPACTO Y EFICIENTE:
- NO uses líneas horizontales (---)
- NO dejes espacios excesivos entre preguntas
- Formato limpio y denso, optimizado para impresión
- Cada pregunta de alternativa ocupa máximo 5-6 líneas
- Las opciones a), b), c), d) van en líneas separadas pero sin espaciado extra

CONTENIDO:
- Tema: {tema}
- Asignatura: {asignatura}
- Nivel: {nivel}
- Dificultad: {dificultad}/10 ({nivel_dificultad})

ESTRUCTURA EXACTA:

## PRUEBA DE {asignatura.upper()}

**Tema:** {tema}
**Nombre:** _______________________  **Fecha:** _______________
**Puntaje:** _____ / [total]

## SECCIÓN I: ALTERNATIVAS ({preguntas_alternativa} preguntas, 1 punto c/u)

Instrucciones: Encierra en un círculo la alternativa correcta.

1. [Pregunta concisa]
a) [Opción]
b) [Opción]
c) [Opción]
d) [Opción]

2. [Siguiente pregunta]
a) [Opción]
b) [Opción]
c) [Opción]
d) [Opción]

[CONTINÚA HASTA LA PREGUNTA {preguntas_alternativa}]

## SECCIÓN II: DESARROLLO ({preguntas_desarrollo} preguntas)

Instrucciones: Responde de forma completa.

1. [Pregunta] (X puntos)

2. [Pregunta] (X puntos)

[CONTINÚA HASTA LA PREGUNTA {preguntas_desarrollo}]

===SOLUCIONARIO===

## SOLUCIONARIO - {asignatura.upper()}

## RESPUESTAS ALTERNATIVAS

1. **[LETRA])** [Justificación breve en 1-2 líneas]
2. **[LETRA])** [Justificación breve]
[hasta {preguntas_alternativa}]

## RESPUESTAS DESARROLLO

1. **Respuesta modelo:** [Respuesta concisa]
   **Criterios:** [Lista de criterios con puntaje]

[hasta {preguntas_desarrollo}]

REGLAS CRÍTICAS:
- ⚠️ GENERA LAS {preguntas_alternativa} PREGUNTAS DE ALTERNATIVA COMPLETAS - CUENTA CADA UNA
- ⚠️ GENERA LAS {preguntas_desarrollo} PREGUNTAS DE DESARROLLO COMPLETAS
- NO uses notación LaTeX. Usa símbolos Unicode: × ÷ ± ≤ ≥ ≠ ² ³ ₂
- El marcador ===SOLUCIONARIO=== es OBLIGATORIO
- Preguntas variadas que cubran diferentes aspectos del tema
- Cada pregunta numerada secuencialmente sin saltar números"""


def generar_prueba(tema: str, asignatura: str, nivel: str,
                   preguntas_alternativa: int, preguntas_desarrollo: int, 
                   dificultad: int = 7, eunacom: bool = False) -> dict:
    """
    Generate a formal test/exam using ChatGPT.
    
    Args:
        eunacom: If True, use EUNACOM medical exam format
    
    Returns:
        dict with 'examen', 'solucionario', 'nombre_prueba', and 'success' status
    """
    
    # Generate AI name for the exam
    nombre_prueba = generar_nombre_prueba(asignatura, tema, nivel)
    
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
            "solucionario": solucionario_mock,
            "nombre_prueba": nombre_prueba
        }
    
    try:
        # Select prompt based on EUNACOM mode
        if eunacom:
            system_prompt = get_eunacom_prompt(tema, asignatura, preguntas_alternativa, preguntas_desarrollo)
            print(f"🏥 Generando prueba EUNACOM: {asignatura} - {tema} ({preguntas_alternativa} preguntas)")
        else:
            system_prompt = get_exam_generation_prompt(
                tema, asignatura, nivel,
                preguntas_alternativa, preguntas_desarrollo, dificultad
            )
            print(f"🧠 Generando prueba: {asignatura} - {tema} (Dificultad: {dificultad}/10)")
            print(f"📋 PARÁMETROS RECIBIDOS: alternativas={preguntas_alternativa}, desarrollo={preguntas_desarrollo}")
        
        # Calculate tokens based on question count - more questions need more tokens
        # Estimate: ~150 tokens per alternativa question + answer, ~300 per desarrollo
        estimated_tokens = (preguntas_alternativa * 180) + (preguntas_desarrollo * 350) + 1000
        max_tokens_needed = min(max(estimated_tokens, 8000), 16000)  # Between 8k and 16k
        
        print(f"📊 Generando {preguntas_alternativa} alternativas + {preguntas_desarrollo} desarrollo (max_tokens: {max_tokens_needed})")
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""Genera una prueba COMPLETA sobre: {tema}

RECUERDA:
- EXACTAMENTE {preguntas_alternativa} preguntas de alternativa numeradas del 1 al {preguntas_alternativa}
- EXACTAMENTE {preguntas_desarrollo} preguntas de desarrollo numeradas del 1 al {preguntas_desarrollo}
- Usa el marcador ===SOLUCIONARIO=== para separar la prueba del solucionario
- NO uses líneas horizontales (---)
- Formato compacto sin espacios innecesarios"""}
            ],
            temperature=0.3,  # Lower temperature for more consistent output
            max_tokens=max_tokens_needed
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
            "solucionario": solucionario,
            "nombre_prueba": nombre_prueba
        }
        
    except Exception as e:
        print(f"❌ Error generando prueba: {e}")
        return {
            "success": False,
            "error": str(e),
            "examen": None,
            "solucionario": None,
            "nombre_prueba": nombre_prueba
        }
