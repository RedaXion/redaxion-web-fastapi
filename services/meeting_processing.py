"""
Meeting Processing Service - Converts meeting transcriptions to structured outputs

Uses ChatGPT to process meeting transcriptions and extract:
- Decisions
- Actions/Tasks with owners
- Blockers/Risks
- Summary (TLDR, Executive, Complete)
"""

import os
from openai import OpenAI

# Client initialization - lazy to ensure env vars are loaded
def get_client():
    """Get OpenAI client lazily to ensure env vars are loaded."""
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️ OPENAI_API_KEY not found. Meeting processing will use mock mode.")
        return None
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


MEETING_PROCESSING_PROMPT = """Eres un asistente experto en transcripción y actas de reuniones. Tu tarea es convertir una transcripción de una reunión en un documento estructurado y accionable.

REGLAS ESTRICTAS:
1. NO asumas información que no esté en la transcripción
2. Si algo no está claro, marca como "POR CONFIRMAR"
3. Usa el formato exacto especificado abajo
4. Idioma: Español
5. Zona horaria: America/Santiago

ESTRUCTURA DE SALIDA OBLIGATORIA:

## TLDR (Too Long; Didn't Read - Resumen Rapido)
[1-2 líneas con lo más importante de la reunión - las decisiones y acciones clave]

---

## TEMAS PRINCIPALES (Mapa de Relevancia)
[Lista de 3-5 temas más mencionados, ordenados por importancia:]
- [ALTO] **[Tema crítico/urgente]** - mencionado X veces
- [MEDIO] **[Tema importante]** - mencionado X veces  
- [NORMAL] **[Tema regular]** - mencionado X veces

---

## RESUMEN EJECUTIVO
[3-5 líneas con las decisiones clave, principales tareas y responsables]

---

## ACTA DE REUNIÓN

**Fecha:** [Extraer de la transcripción o POR CONFIRMAR]
**Asistentes:** [Nombres detectados en la transcripción]

### Decisiones Tomadas

1. **[Decisión]** — Responsable: [Nombre] — Fecha: [si se menciona]
2. ...

### Acciones y Tareas

| ID | Acción | Responsable | Prioridad | Fecha límite | Estado |
|----|--------|-------------|-----------|--------------|--------|
| A1 | [Descripción de la tarea] | [Nombre o POR CONFIRMAR] | Alta/Media/Baja | [Fecha o POR CONFIRMAR] | Pendiente |
| A2 | ... | ... | ... | ... | ... |

### Preguntas Pendientes

- **P1:** [Pregunta que quedó sin resolver] — Responsable de responder: [Nombre o POR CONFIRMAR]
- ...

### Bloqueadores y Riesgos

- **Bloqueador:** [Descripción] — Impacto: Alto/Medio/Bajo — Mitigación sugerida: [si se mencionó]
- ...

### Próximos Pasos

1. [Acción inmediata o seguimiento programado]
2. ...

---

## NOTAS ADICIONALES
[Cualquier otro punto relevante mencionado en la reunión]

INSTRUCCIONES ADICIONALES:
- Si detectas nombres de personas, úsalos consistentemente
- Prioriza las tareas: "urgente" o fecha próxima = Alta, normal = Media, aplazable = Baja
- Convierte fechas relativas ("próxima semana") a formato específico cuando sea posible
- Incluye citas textuales importantes entre comillas
- Si la transcripción es confusa o de baja calidad, menciona esto en las notas
- Para los temas principales, cuenta cuántas veces se menciona cada tema o cuánto tiempo se dedicó a discutirlo"""


def procesar_reunion(transcripcion: str, titulo_reunion: str = None,
                     asistentes: str = None, agenda: str = None) -> dict:
    """
    Process a meeting transcription and extract structured information.
    
    Args:
        transcripcion: The raw transcription text from Deepgram
        titulo_reunion: Optional meeting title
        asistentes: Optional list of attendees (text)
        agenda: Optional meeting agenda (text)
    
    Returns:
        dict with 'contenido' (formatted meeting minutes) and 'success' status
    """
    
    client = get_client()
    if not client:
        print("MOCK: Processing meeting (No API Key)...")
        return {
            "success": True,
            "contenido": f"""## RESUMEN TLDR
Reunión de demostración - Conecte OpenAI para procesar contenido real.

---

## RESUMEN EJECUTIVO
Esta es una versión de demostración del procesamiento de reuniones. Para obtener resultados reales, asegúrese de tener configurada la API key de OpenAI.

---

## ACTA DE REUNIÓN

**Fecha:** {titulo_reunion or "Reunión de Ejemplo"}
**Asistentes:** {asistentes or "Por determinar"}

### Decisiones Tomadas
1. **Decisión de ejemplo** — Responsable: Por confirmar

### Acciones y Tareas
| ID | Acción | Responsable | Prioridad | Fecha límite | Estado |
|----|--------|-------------|-----------|--------------|--------|
| A1 | Tarea de ejemplo | Por confirmar | Media | Por confirmar | Pendiente |

### Preguntas Pendientes
- **P1:** ¿Cómo procesan las reuniones reales? — Responsable: Usuario

### Bloqueadores y Riesgos
- Ninguno identificado en esta demostración

### Próximos Pasos
1. Configurar API key de OpenAI
2. Subir audio de reunión real
"""
        }
    
    try:
        # Build context from optional inputs
        context_parts = []
        
        if titulo_reunion:
            context_parts.append(f"Título de la reunión: {titulo_reunion}")
        
        if asistentes:
            context_parts.append(f"Lista de asistentes proporcionada:\n{asistentes}")
        
        if agenda:
            context_parts.append(f"Agenda previa:\n{agenda}")
        
        context = "\n\n".join(context_parts) if context_parts else ""
        
        # Prepare the user message
        if context:
            context_section = f"CONTEXTO ADICIONAL:\n{context}\n\n---\n\n"
        else:
            context_section = ""
        
        user_message = f"""Procesa la siguiente transcripción de reunión:

{context_section}TRANSCRIPCIÓN:
{transcripcion}"""
        
        print(f"🧠 Procesando reunión: {titulo_reunion or 'Sin título'}")
        
        openai_client = get_client()
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": MEETING_PROCESSING_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=4000
        )
        
        contenido = response.choices[0].message.content.strip()
        print("✅ Reunión procesada exitosamente")
        
        return {
            "success": True,
            "contenido": contenido
        }
        
    except Exception as e:
        print(f"❌ Error procesando reunión: {e}")
        return {
            "success": False,
            "error": str(e),
            "contenido": None
        }
