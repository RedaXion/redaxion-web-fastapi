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

# Client initialization moved to functions to ensure env vars are loaded
def get_client():
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️ OPENAI_API_KEY not found. Using Mock mode.")
        return None
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generar_nombre_prueba(asignatura: str, tema: str, nivel: str) -> str:
    """Generate a short exam name using AI (max 4 words)."""
    
    client = get_client()
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
    
    # Build desarrollo section if needed
    desarrollo_section = ""
    desarrollo_solucionario = ""
    if preguntas_desarrollo > 0:
        desarrollo_section = f"""

## SECCIÓN II: DESARROLLO ({preguntas_desarrollo} preguntas)

Instrucciones: Responde de forma completa y fundamentada.

1. [Pregunta de análisis clínico que requiera razonamiento] (10 pts)
2. [Pregunta sobre diagnóstico diferencial o manejo] (10 pts)
[...hasta la pregunta {preguntas_desarrollo}]
"""
        desarrollo_solucionario = f"""

**DESARROLLO:**
1. [Respuesta modelo completa con criterios de evaluación]
2. [Respuesta modelo]
[...hasta la pregunta {preguntas_desarrollo}]"""
    
    return f"""Eres un generador de preguntas para el examen EUNACOM, orientado a evaluar competencias clínicas de un médico general en Chile.
Debes basarte exclusivamente en casos clínicos, siguiendo el formato, nivel de dificultad y estilo de las preguntas oficiales disponibles en:
https://www.eunacom.cl/contenidos/muestra.html

Debes respetar el Perfil de Conocimientos EUNACOM, especialmente el área de {asignatura}.

⚠️ CANTIDAD OBLIGATORIA:
- DEBES generar EXACTAMENTE {preguntas_alternativa} preguntas de alternativa (casos clínicos)
- DEBES generar EXACTAMENTE {preguntas_desarrollo} preguntas de desarrollo
- NO generes menos preguntas. Numera cada sección por separado.

INSTRUCCIONES GENERALES

Cada pregunta de alternativa debe tener su propio caso clínico, de 4 a 6 líneas, clínicamente realista.

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

## SECCIÓN I: ALTERNATIVAS ({preguntas_alternativa} preguntas)

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
{desarrollo_section}
===SOLUCIONARIO===

## SOLUCIONARIO EUNACOM

**ALTERNATIVAS:**
1. **[LETRA])** [Diagnóstico + justificación breve]
2. **[LETRA])** [Justificación]
[...hasta la pregunta {preguntas_alternativa}]{desarrollo_solucionario}

RESTRICCIONES IMPORTANTES

❌ No usar líneas horizontales (---)
❌ No usar espacios excesivos entre preguntas
✅ Instrucción matemática mandatoria: Si requieres incluir ecuaciones clínicas o fórmulas (ej. clearance, Parkland), DEBES encapsular el código LaTeX dentro de la etiqueta `<formula>`. Ejemplo: `<formula> E = mc^2 </formula>`."""


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

⚠️ CANTIDAD OBLIGATORIA:
- {preguntas_alternativa} preguntas de alternativa (numeradas 1 a {preguntas_alternativa})
- {preguntas_desarrollo} preguntas de desarrollo (numeradas 1 a {preguntas_desarrollo})
- El solucionario DEBE tener las {preguntas_alternativa} respuestas de alternativa

FORMATO COMPACTO:
- NO usar líneas horizontales (---)
- NO espacios excesivos
- Preguntas concisas de 2-3 líneas máximo

CONTENIDO: {tema} | {asignatura} | {nivel} | Dificultad {dificultad}/10

ESTRUCTURA:

## PRUEBA DE {asignatura.upper()}

**Tema:** {tema}
**Nombre:** _______  **Fecha:** _______  **Puntaje:** ___ / {preguntas_alternativa + preguntas_desarrollo * 5}

## I. ALTERNATIVAS ({preguntas_alternativa} pts)

1. [Pregunta breve]
a) [Opción]
b) [Opción]
c) [Opción]
d) [Opción]

2. [Pregunta]
a) [Opción]
b) [Opción]
c) [Opción]
d) [Opción]

[...hasta {preguntas_alternativa}]

## II. DESARROLLO ({preguntas_desarrollo} preguntas)

1. [Pregunta] ({5} pts)
2. [Pregunta] ({5} pts)
[...hasta {preguntas_desarrollo}]

===SOLUCIONARIO===

## SOLUCIONARIO

**ALTERNATIVAS:**
1. **C)** [Justificación breve y sustantiva, no tautológica, máximo 1 línea]
2. **A)** [Por qué A es correcta - razón concreta]
3. **B)** [Explicación breve del concepto clave]
...
{preguntas_alternativa}. **D)** [Justificación]

**DESARROLLO:**
1. [Respuesta modelo en 2-3 líneas]
2. [Respuesta modelo en 2-3 líneas]
[...hasta {preguntas_desarrollo}]

⚠️ CRÍTICO:
- Las {preguntas_alternativa} preguntas de alternativa DEBEN tener su respuesta en el solucionario
- Cada respuesta tiene formato: "N. **LETRA)** [justificación de 1 línea]"
- La justificación debe explicar POR QUÉ es correcta (no "es C porque C es la respuesta")
- TODAS las {preguntas_alternativa} respuestas deben aparecer, sin omisiones
- Instrucción matemática mandatoria: Si requieres escribir fórmulas o ecuaciones complejas/medianas, DEBES encapsular su código LaTeX puro dentro de la etiqueta `<formula>`. Ejemplo: `<formula> x^2 + y^2 = r^2 </formula>`. No uses código inline básico."""


def generar_prueba(tema: str, asignatura: str, nivel: str,
                   preguntas_alternativa: int, preguntas_desarrollo: int, 
                   dificultad: int = 7, eunacom: bool = False,
                   context_material: str = None) -> dict:
    """
    Generate a formal test/exam using ChatGPT.
    
    Args:
        eunacom: If True, use EUNACOM medical exam format
        context_material: Optional extracted text from uploaded documents
    
    Returns:
        dict with 'examen', 'solucionario', 'nombre_prueba', and 'success' status
    """
    
    # Generate AI name for the exam
    nombre_prueba = generar_nombre_prueba(asignatura, tema, nivel)
    
    client = get_client()
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
        
        # Calculate tokens - need enough for questions + solucionario with brief justifications
        # ~100 tokens per question, ~40 tokens per answer with justification
        estimated_tokens = (preguntas_alternativa * 140) + (preguntas_desarrollo * 450) + 2500
        max_tokens_needed = min(max(estimated_tokens, 12000), 16000)  # Between 12k and 16k
        
        print(f"📊 Generando {preguntas_alternativa} alternativas + {preguntas_desarrollo} desarrollo (max_tokens: {max_tokens_needed})")
        
        # Build context message if provided
        context_section = ""
        if context_material and len(context_material) > 100:
            # Truncate if too long for context window
            max_context = 40000
            if len(context_material) > max_context:
                context_material = context_material[:max_context] + "\n[... contenido truncado ...]"
            context_section = f"""\n\nMATERIAL DE REFERENCIA (usa esto como base para las preguntas):
{context_material}
\n¡IMPORTANTE! Basa las preguntas ESPECÍFICAMENTE en el material proporcionado arriba."""
            print(f"📚 Usando {len(context_material)} caracteres de material de contexto")
        
        # Build user message
        user_message = f"""Genera una prueba sobre: {tema}

OBLIGATORIO:
- {preguntas_alternativa} preguntas de alternativa (numeradas 1 a {preguntas_alternativa})
- {preguntas_desarrollo} preguntas de desarrollo
- Solucionario con las {preguntas_alternativa} respuestas, cada una con justificación breve (1 línea)
- Formato: "1. **C)** Porque [razón concreta]"
- ===SOLUCIONARIO=== como separador
- NO justificaciones tautológicas como "es C porque es correcta"
- Formato compacto, sin líneas horizontales{context_section}"""
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
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
