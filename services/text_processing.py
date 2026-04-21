import os
import re
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
    return """Eres un corrector de estilo y gramática especializado en transcripciones académicas. Tu tarea es EDITAR, no reescribir, el texto que recibes.

ROL EXACTO: Corrector de estilo fiel al original.
NO eres un redactor. NO eres un resumidor. NO eres un escritor creativo.

REGLA MAESTRA (no tiene excepciones):
Conserva TODA la información del original. Cada idea, cada dato, cada ejemplo, cada explicación que aparece en la transcripción DEBE aparecer en tu salida.

LO QUE SÍ DEBES HACER:
- Eliminar muletillas y relleno oral: "eh", "este", "o sea", "básicamente", "como que", "bueno", repeticiones idénticas sin valor.
- Corregir la gramática, ortografía y concordancia verbal.
- Estructurar el texto con párrafos bien demarcados por tema.
- Convertir listas orales ("primero esto, luego aquello, después lo otro") en listas con viñetas o numeración.
- Aplicar mayúsculas, puntuación y tildes correctas.
- En cada párrafo, resaltar en **negritas** los términos técnicos, conceptos clave o afirmaciones centrales.
- En listas, poner en **negritas** el nombre de la categoría antes de los dos puntos.
- Detectar fórmulas o ecuaciones y encapsularlas en `<formula>código LaTeX</formula>`.
- Usar ## para secciones principales y ### para subsecciones.

LO QUE ESTÁ PROHIBIDO:
- Resumir o comprimir ideas.
- Fusionar dos explicaciones distintas en una sola.
- Omitir un ejemplo, aclaración o dato aunque parezca redundante.
- Agregar información que NO estaba en la transcripción.
- Cambiar el significado de ninguna oración.
- Eliminar repeticiones que aclaren o refuercen un concepto.

SOBRE LA EXTENSIÓN:
Tu salida debe tener una extensión similar o mayor a la entrada. Si el bloque de entrada tiene 600 palabras, tu salida debe rondar las 600–800 palabras (el formato añade algo de volumen). Si tu salida es significativamente más corta que la entrada, estás resumiendo — eso está totalmente prohibido.

CONTEXTO:
Este fragmento forma parte de un documento mayor. No incluyas introducciones ni conclusiones. Mantén la continuidad como si el lector ya viniese leyendo desde una sección anterior."""


def dividir_texto_en_bloques(texto, max_palabras=800):
    # Divide el texto por puntos seguidos de espacio para no romper oraciones
    oraciones = re.split(r'(?<=\.)\s+', texto)
    bloques = []
    bloque_actual = []
    palabras_actuales = 0

    for oracion in oraciones:
        palabras_oracion = len(oracion.split())
        if palabras_actuales + palabras_oracion > max_palabras and bloque_actual:
            bloques.append(" ".join(bloque_actual))
            bloque_actual = [oracion]
            palabras_actuales = palabras_oracion
        else:
            bloque_actual.append(oracion)
            palabras_actuales += palabras_oracion

    if bloque_actual:
        bloques.append(" ".join(bloque_actual))

    return bloques


def procesar_txt_con_chatgpt(path_txt):
    client = get_client()
    if not client:
        print("MOCK: Processing text with ChatGPT (No API Key)...")
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
