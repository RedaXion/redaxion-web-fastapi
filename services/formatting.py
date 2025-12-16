from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import re
import os

# MOCK: marca_agua module imports
# from marca_agua import preparar_logo, insertar_logo_encabezado_derecha
def preparar_logo():
    pass

def insertar_logo_encabezado_derecha(doc):
    pass

ESTILOS_COLOR = {
    "azul elegante": {
        "titulo": {"fondo": "4A66AC", "letra": "FFFFFF"},
        "subtitulo": {"fondo": "D8DFEF", "letra": "000000"},
        "texto": {"fondo": "FFFFFF", "letra": "000000"},
    },
    "azul pastel": {
        "titulo": {"fondo": "4F81BD", "letra": "FFFFFF"},
        "subtitulo": {"fondo": "DCE5F0", "letra": "000000"},
        "texto": {"fondo": "FFFFFF", "letra": "000000"},
    },
    "rojo elegante": {
        "titulo": {"fondo": "C10905", "letra": "FFFFFF"},
        "subtitulo": {"fondo": "FFBFBF", "letra": "000000"},
        "texto": {"fondo": "FFFFFF", "letra": "000000"},
    },
    "rojo pastel": {
        "titulo": {"fondo": "E32E91", "letra": "FFFFFF"},
        "subtitulo": {"fondo": "F9D4E8", "letra": "000000"},
        "texto": {"fondo": "FFFFFF", "letra": "000000"},
    },
    "gris elegante": {
        "titulo": {"fondo": "7F7F7F", "letra": "FFFFFF"},
        "subtitulo": {"fondo": "E5E5E5", "letra": "000000"},
        "texto": {"fondo": "FFFFFF", "letra": "000000"},
    },
    "morado pastel": {
        "titulo": {"fondo": "B553D9", "letra": "FFFFFF"},
        "subtitulo": {"fondo": "D094E6", "letra": "000000"},
        "texto": {"fondo": "FFFFFF", "letra": "000000"},
    },
    "verde pastel": {
        "titulo": {"fondo": "569F3B", "letra": "FFFFFF"},
        "subtitulo": {"fondo": "DAEFD3", "letra": "000000"},
        "texto": {"fondo": "FFFFFF", "letra": "000000"},
    }
}

# ---------------------------
# Helpers de tipografía Calibri
# ---------------------------
def _forzar_calibri_en_estilo(doc, font_name="Calibri", font_size=11):
    """Fija Calibri en el estilo Normal y en rFonts para evitar reemplazos."""
    if 'Normal' not in doc.styles:
        return
        
    style = doc.styles['Normal']
    font = style.font
    font.name = font_name
    font.size = Pt(font_size)
    
    # Ensure element exists
    if style.element is None: 
         return
         
    # Asegurar mapeos de fuentes en XML (clave para que Word no sustituya)
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    rFonts.set(qn('w:cs'), font_name)
    rFonts.set(qn('w:eastAsia'), font_name)

def _set_run_calibri(run, font_name="Calibri"):
    """Asegura Calibri en un run, incluyendo rFonts."""
    run.font.name = font_name
    # Proteger los cuatro mapas
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)
    rFonts.set(qn('w:cs'), font_name)
    rFonts.set(qn('w:eastAsia'), font_name)

def aplicar_estilo(parrafo, tipo_bloque, color, espaciado_extra=False):
    color_normalizado = color.strip().lower()
    if color_normalizado not in ESTILOS_COLOR:
        # print(f"⚠️ Color no reconocido: '{color}'. Usando 'azul elegante' por defecto.")
        color_normalizado = "azul elegante"

    estilos_por_color = ESTILOS_COLOR[color_normalizado]
    estilos = estilos_por_color.get(tipo_bloque, {})
    fondo = estilos.get("fondo", "FFFFFF")
    letra = estilos.get("letra", "000000")

    # Color de texto
    for run in parrafo.runs:
        run.font.color.rgb = RGBColor(
            int(letra[0:2], 16),
            int(letra[2:4], 16),
            int(letra[4:6], 16)
        )

    # Fondo del párrafo (títulos y subtítulos)
    if tipo_bloque in ["titulo", "subtitulo"]:
        p = parrafo._p
        pPr = p.get_or_add_pPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:fill'), fondo)
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), "auto")
        pPr.append(shd)

    # Espaciado adicional
    if espaciado_extra:
        parrafo.paragraph_format.space_after = Pt(10)

def agregar_texto_con_negrita(parrafo, texto):
    if not texto.strip():
        _set_run_calibri(parrafo.add_run(" "))
        return

    patron = r"\*\*(.*?)\*\*"
    cursor = 0
    for match in re.finditer(patron, texto):
        start, end = match.span()
        if start > cursor:
            r1 = parrafo.add_run(texto[cursor:start])
            _set_run_calibri(r1)
        run_negrita = parrafo.add_run(match.group(1))
        run_negrita.bold = True
        _set_run_calibri(run_negrita)
        cursor = end
    if cursor < len(texto):
        r2 = parrafo.add_run(texto[cursor:])
        _set_run_calibri(r2)

def configurar_columnas(doc, tipo):
    if tipo == "doble":
        try:
             section = doc.sections[-1]
             # Check if cols element exists, if not create logic might be more complex
             # For now trusting existing logic but wrapped in try/except
             cols = section._sectPr.xpath('./w:cols')
             if cols:
                 cols[0].set(qn('w:num'), '2')
                 cols[0].set(qn('w:space'), '720')
             else:
                 # TODO: Add logic to create columns xml if missing
                 pass
             section.left_margin = Inches(0.5)
             section.right_margin = Inches(0.5)
             section.top_margin = Inches(0.75)
             section.bottom_margin = Inches(0.75)
        except Exception as e:
            print(f"Warning: Failed to configure columns: {e}")


from services.image_generation import generate_image_from_text
from services.napkin_integration import generate_napkin_visual

def guardar_como_docx(texto, path_salida="/tmp/procesado.docx", color="azul oscuro", columnas="simple"):
    preparar_logo()
    doc = Document()
    _forzar_calibri_en_estilo(doc)
    insertar_logo_encabezado_derecha(doc)
    
    if columnas == "doble":
        configurar_columnas(doc, columnas)

    # Márgenes estrechos
    section = doc.sections[0]
    section.top_margin = Inches(0.5)
    section.bottom_margin = Inches(0.5)
    section.left_margin = Inches(0.5)
    section.right_margin = Inches(0.5)

    # Napkin AI Visual at start
    napkin_img = generate_napkin_visual(texto[:2000])
    if napkin_img:
        try:
            doc.add_picture(napkin_img, width=Inches(3) if columnas=="doble" else Inches(5))
            last_p = doc.paragraphs[-1] 
            last_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.add_paragraph("") # Spacing
        except Exception as e:
            print(f"Error inserting Napkin visual: {e}")

    texto_lineas = texto.split('\n')
    titulo_agregado = False
    
    word_count_since_last_image = 0
    current_topic = "Conceptos académicos generales" # Default topic
    
    for linea in texto_lineas:
        linea = linea.rstrip()
        if not linea.strip():
            continue

        linea_normalizada = linea.lstrip()
        word_count_since_last_image += len(linea_normalizada.split())
        
        # Track topics to save tokens (don't send full text to GPT)
        if linea_normalizada.startswith("## ") or linea_normalizada.startswith("# "):
            current_topic = linea_normalizada.replace("## ", "").replace("# ", "").strip()
        elif linea_normalizada.startswith("### "):
            current_topic = linea_normalizada.replace("### ", "").strip()

        # Check for image insertion point
        if word_count_since_last_image >= IMAGE_THRESHOLD:
             print(f"🖼️ Threshold reached. Topic: '{current_topic}'")
             # Optimization: Send ONLY the topic to the image generator, checking cost.
             img_stream = generate_image_from_text(current_topic)
             if img_stream:
                 try:
                     doc.add_picture(img_stream, width=Inches(3) if columnas=="doble" else Inches(5.5))
                     last_p = doc.paragraphs[-1] 
                     last_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                     doc.add_paragraph("")
                 except Exception as e:
                     print(f"Error inserting generated image: {e}")
             
             # Reset counters
             word_count_since_last_image = 0
             # accumulated_text_for_image = "" # No longer needed

        # 🔁 Tolerancia: tratar #### como ### para subtítulos mal formateados
        if linea_normalizada.startswith("#### "):
            linea_normalizada = linea_normalizada.replace("#### ", "### ")

        if linea_normalizada.startswith("### "):
            texto_subtitulo = linea_normalizada.replace("### ", "")
            p = doc.add_paragraph()
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = p.add_run(texto_subtitulo)
            run.font.size = Pt(12)
            run.font.bold = True
            _set_run_calibri(run)
            aplicar_estilo(p, "subtitulo", color)

        elif linea_normalizada.startswith("## ") or linea_normalizada.startswith("# "):
            texto_titulo = linea_normalizada.replace("## ", "").replace("# ", "")
            p = doc.add_paragraph()
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = p.add_run(texto_titulo)
            run.font.size = Pt(14)
            run.font.bold = True
            _set_run_calibri(run)
            aplicar_estilo(p, "titulo", color)
            if columnas == "doble" and not titulo_agregado:
                configurar_columnas(doc, columnas)
                titulo_agregado = True
        else:
            p = doc.add_paragraph()
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            agregar_texto_con_negrita(p, linea_normalizada)
            aplicar_estilo(p, "texto", color)

    doc.save(path_salida)
    return path_salida


def guardar_quiz_como_docx(texto_preguntas_y_respuestas, path_guardado="/tmp/quiz.docx", color="azul oscuro", columnas="simple"):
    preparar_logo()
    doc = Document()
    _forzar_calibri_en_estilo(doc)  # <<< Fuerza Calibri 11
    insertar_logo_encabezado_derecha(doc)

    # Márgenes estrechos
    section = doc.sections[0]
    section.top_margin = Inches(0.5)
    section.bottom_margin = Inches(0.5)
    section.left_margin = Inches(0.5)
    section.right_margin = Inches(0.5)

    if columnas == "doble":
        configurar_columnas(doc, columnas)

    # (Se mantiene tu seteo explícito del estilo Normal)
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)

    # Limpia encabezado "Respuestas" si viene duplicado
    texto_preguntas_y_respuestas = re.sub(
        r"(?i)^\s*\*{0,3}\s*respuestas\s*\*{0,3}[:：]?\s*$",
        "",
        texto_preguntas_y_respuestas,
        flags=re.MULTILINE
    )

    titulo = doc.add_heading("RedaQuiz", level=1)
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    aplicar_estilo(titulo, "titulo", color)
    doc.add_paragraph("")

    match = re.search(r"(respuesta 1:)", texto_preguntas_y_respuestas.lower())
    if not match:
        preguntas = texto_preguntas_y_respuestas.strip()
        respuestas = ""
    else:
        idx = match.start()
        preguntas = texto_preguntas_y_respuestas[:idx].strip()
        respuestas = texto_preguntas_y_respuestas[idx:].strip()

    bloques = re.split(r"\n(?=\d{1,2}\. )", preguntas)
    for bloque in bloques:
        lineas = bloque.strip().split("\n")
        if not lineas:
            continue

        encabezado = lineas[0].strip()
        if "preguntas de práctica" in encabezado.lower():
            p = doc.add_paragraph()
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = p.add_run("Preguntas de práctica")
            run.bold = True
            _set_run_calibri(run)
            run.font.size = Pt(13)
            aplicar_estilo(p, "subtitulo", color, espaciado_extra=True)
            p.paragraph_format.space_after = Pt(6)
        else:
            p = doc.add_paragraph()
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = p.add_run(encabezado)
            run.bold = True
            _set_run_calibri(run)
            run.font.size = Pt(12)
            aplicar_estilo(p, "subtitulo", color, espaciado_extra=True)

        for linea in lineas[1:]:
            linea = linea.strip()
            if not linea:
                continue
            # ❌ Antes: se removían **...**
            # ✅ Ahora: se mantienen para que agregar_texto_con_negrita aplique bold
            para = doc.add_paragraph()
            para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            agregar_texto_con_negrita(para, linea)
            aplicar_estilo(para, "texto", color)

    doc.add_page_break()

    if respuestas:
        p = doc.add_paragraph()
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        run = p.add_run("Respuestas")
        run.bold = True
        _set_run_calibri(run)
        run.font.size = Pt(14)
        aplicar_estilo(p, "titulo", color)

        for linea in respuestas.strip().split("\n"):
            linea = linea.strip()
            if re.match(r"^\s*respuestas\s*[:：]?\s*$", linea, flags=re.IGNORECASE):
                continue
            # ❌ Sin limpieza de **...**
            para = doc.add_paragraph()
            para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            agregar_texto_con_negrita(para, linea)
            aplicar_estilo(para, "texto", color)

    doc.save(path_guardado)
    return path_guardado

# --- Logic from convertidor_pdf.py ---

import subprocess

def convert_to_pdf(path_docx):
    """
    Convierte un archivo .docx a .pdf usando LibreOffice.
    Retorna la ruta al PDF generado o None si falló.
    """
    output_dir = os.path.dirname(path_docx)
    try:
        # Check if libreoffice is installed or use dummy
        # subprocess.run(["libreoffice", "--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Real conversion attempt
        subprocess.run([
            "libreoffice", "--headless", "--convert-to", "pdf", path_docx, "--outdir", output_dir
        ], check=True, capture_output=True)
        
        path_pdf = path_docx.replace(".docx", ".pdf")
        print(f"✅ PDF generado correctamente: {path_pdf}")
        return path_pdf
    except Exception as e:
        print(f"❌ Warning: Could not convert .docx to .pdf (LibreOffice missing?): {e}")
        return None
