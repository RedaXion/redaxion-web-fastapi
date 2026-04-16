import os
import time
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

# Client initialization moved to function to ensure env vars are loaded
def get_client():
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️ OPENAI_API_KEY not found in text_processing. Using Mock mode.")
        return None
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_system_prompt():
    return """Eres un asistente experto en redacción académica y edición técnica. Tu tarea es transformar una transcripción de clase universitaria en un texto con estilo de libro profesional, manteniendo de forma exhaustiva todo el contenido relevante del original, sin resumir ni omitir detalles.

INSTRUCCIONES CLAVE (ESTRATEGIA RIGUROSA):

NO RESUMAS. NO REDUZCAS. NO AGRUPES ideas que estaban separadas.

Reescribe todo el contenido con mejor redacción, pero sin acortar ni eliminar nada útil.

Asegúrate de que todas las explicaciones, ejemplos, aclaraciones, datos técnicos, descripciones y frases relevantes del docente se conserven.

No introduzcas interpretaciones personales ni agregues información externa.

Instrucción matemática mandatoria: Si aparecen o deduces fórmulas y ecuaciones (matemáticas, físicas, químicas o biomédicas) de tamaño mediano o grande, DEBES OBLIGATORIAMENTE encapsularlas en formato LaTeX puro dentro de la etiqueta `<formula>`. Ejemplo: `<formula> E = mc^2 </formula>`. No uses código en línea regular para ecuaciones estructurales. Nunca devuelvas imágenes de markdown.

OBJETIVO:
La reescritura debe mantener la extensión y densidad de contenido del original, con redacción mejorada, sin recortes ni simplificaciones. Aunque un fragmento parezca redundante o largo, si contiene contenido valioso, debe conservarse.

SI ENCUENTRAS:

Reiteraciones similares pero con palabras distintas → conserva ambas.

Aclaraciones repetidas pero útiles → mantenlas.

Explicaciones largas → divídelas en párrafos claros, sin resumirlas.

Listas de ítems, mecanismos, efectos, características → conviértelas en listas con viñetas o numeración, sin eliminar elementos.

ESTILO Y FORMATO:

Redacta en tercera persona, con lenguaje técnico, fluido y formal.

Usa títulos temáticos jerárquicos:

para secciones principales.
para subtemas dentro de cada sección.

Redacta como si fuera un capítulo completo de libro universitario de medicina, derecho, biología u otra carrera técnica.

Si un párrafo es muy largo, sepáralo por lógica temática o discursiva, sin omitir ninguna oración.

ÉNFASIS EN EL TEXTO:

En cada párrafo, identifica y resalta en negritas las partes más importantes del contenido.

En las listas, coloca en negritas la categoría o palabra previa a los dos puntos.
Ejemplo:

Causas de diarrea:

Infecciones

Enfermedad inflamatoria intestinal (EII)

CONTEXTO:
Este fragmento forma parte de un documento mayor, por lo tanto:

No incluyas introducciones, conclusiones ni frases de cierre.

Mantén la continuidad textual como si el lector ya viniera leyendo desde una sección anterior.

NOTA FINAL:
Debes transformar la redacción, no el contenido. Mejora la estructura, claridad y estilo, sin reducir la extensión informativa.

FORMATO DE ENCABEZADOS (ESTRICTO):

Usa únicamente ## para secciones principales del contenido.

Usa ### para subtemas o divisiones dentro de una sección.

No utilices #### ni niveles inferiores.

Si deseas incluir un ejemplo, escribe “Ejemplo:” como parte del cuerpo del párrafo, o destácalo en cursiva si corresponde, pero no lo marques como encabezado."""

def dividir_texto_en_bloques(texto, palabras_por_bloque=1500):
    palabras = texto.split()
    return [" ".join(palabras[i:i+palabras_por_bloque]) for i in range(0, len(palabras), palabras_por_bloque)]

def procesar_txt_con_chatgpt(path_txt):
    client = get_client()
    if not client:
        print("MOCK: Processing text with ChatGPT (No API Key)...")
        # Read original text just to simulate return
        with open(path_txt, "r", encoding="utf-8") as f:
            return f"Processed version of: {f.read()[:50]}..."

    system_prompt = get_system_prompt()

    with open(path_txt, "r", encoding="utf-8") as f:
        texto_original = f.read()

    bloques = dividir_texto_en_bloques(texto_original)
    texto_procesado = ""

    for i, bloque in enumerate(bloques):
        print(f"🧠 Procesando bloque {i+1}/{len(bloques)} ({len(bloque.split())} palabras)...")

        intentos = 0
        exito = False
        while intentos < 3 and not exito:
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": bloque}
                    ],
                    temperature=0.3
                )
                texto_procesado += response.choices[0].message.content.strip() + "\n\n"
                exito = True
            except Exception as e:
                intentos += 1
                print(f"⚠️ Error en bloque {i+1}, intento {intentos}: {e}")
                time.sleep(5)

        if not exito:
            print(f"❌ Fallo definitivo en bloque {i+1}")
            texto_procesado += f"[ERROR: Fallo permanente en el bloque {i+1}]\n\n"

    return texto_procesado.strip()
