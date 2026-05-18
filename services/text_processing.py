import os
import re
import time
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
import anthropic

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
- Usar ## para el título principal del documento. Este título debe ser **amigable, empático y muy atractivo**.
- Usar ### para los subtítulos de las secciones de forma MODERADA. Úsalos solo para dividir el texto en secciones lógicas grandes (cuando cambie el tema principal). No pongas subtítulos para cada párrafo o idea pequeña. Busca un equilibrio natural que facilite la lectura sin fragmentar demasiado el texto.
- Sé fiel al flujo del discurso del exponente, pero estructúralo de forma que sea fluido y fácil de estudiar, evitando el exceso de divisiones.

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
    """
    Divide el texto en bloques de ≤max_palabras para enviar a GPT.

    Estrategia en cascada:
    1. Divide por punto (.) seguido de espacio — respeta oraciones.
    2. Si algún fragmento resultante supera max_palabras (p. ej. Deepgram
       devolvió texto casi sin puntuación), lo re-divide por otros
       delimitadores: ';', ',', salto de línea.
    3. Si aún así el fragmento es demasiado largo, lo corta por palabras
       de forma forzada como último recurso.

    Esto garantiza que NUNCA se envíe un bloque gigante a GPT, lo cual
    causaría timeout o respuesta truncada (el error de "1 sola página").
    """
    total_palabras = len(texto.split())
    print(f"📐 [chunking] Texto total: {total_palabras} palabras")

    # --- Paso 1: División por punto ---
    fragmentos_crudos = re.split(r'(?<=\.)\s+', texto)

    # --- Paso 2 y 3: Sub-dividir fragmentos que sigan siendo muy grandes ---
    oraciones = []
    for frag in fragmentos_crudos:
        if len(frag.split()) <= max_palabras:
            oraciones.append(frag)
        else:
            # Intentar con ';' y ','
            sub_frags = re.split(r'(?<=[;,])\s+', frag)
            for sf in sub_frags:
                if len(sf.split()) <= max_palabras:
                    oraciones.append(sf)
                else:
                    # Corte forzado por palabras (último recurso)
                    palabras = sf.split()
                    for i in range(0, len(palabras), max_palabras):
                        oraciones.append(" ".join(palabras[i:i + max_palabras]))

    print(f"📐 [chunking] Fragmentos base: {len(oraciones)}")

    # --- Agregar fragmentos en bloques de ≤max_palabras ---
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

    print(f"📐 [chunking] Bloques finales: {len(bloques)} (máx. {max_palabras} palabras c/u)")
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
        palabras_bloque = len(bloque.split())
        print(f"🧠 Procesando bloque {i+1}/{len(bloques)} ({palabras_bloque} palabras)...")

        intentos = 0
        exito = False
        while intentos < 3 and not exito:
            try:
                if intentos < 2:
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": bloque}
                        ],
                        temperature=0.3,
                        timeout=120  # Timeout explícito: 2 min por bloque
                    )
                    contenido = response.choices[0].message.content.strip()
                else:
                    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
                    if not anthropic_key:
                        raise ValueError("No hay ANTHROPIC_API_KEY para fallback")
                    print(f"   🔄 Usando Anthropic Claude (fallback) para bloque {i+1}...")
                    anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
                    response = anthropic_client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=2048,
                        temperature=0.3,
                        system=system_prompt,
                        messages=[
                            {"role": "user", "content": bloque}
                        ],
                        timeout=120
                    )
                    contenido = response.content[0].text.strip()

                if not contenido:
                    raise ValueError("API devolvió respuesta vacía")
                texto_procesado += contenido + "\n\n"
                exito = True
                print(f"   ✅ Bloque {i+1} procesado: {len(contenido.split())} palabras salida")
            except Exception as e:
                intentos += 1
                print(f"   ⚠️ Error en bloque {i+1}, intento {intentos}: {e}")
                time.sleep(5)

        if not exito:
            print(f"   ❌ Fallo definitivo en bloque {i+1} — se incluye texto original como fallback")
            # Incluir el texto original en lugar de un mensaje de error vacío
            texto_procesado += bloque + "\n\n"

    return texto_procesado.strip()
