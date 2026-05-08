import os
import requests
import base64
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.units import inch
from io import BytesIO

def get_mermaid_ink_image(mermaid_code):
    b64_code = base64.b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
    url = f"https://mermaid.ink/img/{b64_code}"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return BytesIO(r.content)
    except Exception as e:
        print(f"Error: {e}")
    return None

def rebuild_full_pdf(text_file, output_path):
    with open(text_file, 'r') as f:
        full_text = f.read()

    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=60, leftMargin=60, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10.5, leading=13, spaceAfter=10, alignment=0)
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor("#2E5090"), spaceBefore=15, spaceAfter=8)

    elements = []
    
    visual_mappings = [
        ("La Tolerancia Inmunitaria", "flowchart TD\n  A[Antígeno] --> B{Propio?}\n  B -->|Sí| C[Tolerancia]\n  B -->|No| D[Ataque]\n  style C fill:#DCE5F0,stroke:#4F81BD", "Concepto de Tolerancia"),
        ("Patologías Relacionadas", "flowchart LR\n  A[Equilibrio] --> B[Autoinmunidad]\n  A --> C[Inmunodeficiencia]\n  A --> D[Hipersensibilidad]\n  style B fill:#FFBFBF,stroke:#C10905", "Inmunopatologías"),
        ("Mecanismos de la Tolerancia", "flowchart TD\n  A[Linfocito T] --> B{Reacciona?}\n  B -->|No| C[Sangre]\n  B -->|Sí| D[Apoptosis]\n  style C fill:#DAEFD3,stroke:#569F3B", "Selección de Linfocitos"),
        ("Tolerancia Central y Periférica", "flowchart TD\n  A[Central - Timo] --> B[Gen AIRE]\n  B --> C[Salida]\n  C --> D[Periférica - Tregs]\n  style B fill:#D8DFEF,stroke:#4A66AC", "Central vs Periférica"),
        ("Respuesta Alérgica", "flowchart LR\n  A[Genes Atópicos] --> B[Exposición]\n  B --> C[Reacción Alérgica]\n  style C fill:#D094E6,stroke:#B553D9", "Alergia y Genética"),
        ("tumorogénesis", "flowchart LR\n  A[Daño ADN] --> B{Falla Control}\n  B --> C[Tumorogénesis]\n  style C fill:#FFBFBF,stroke:#C10905", "Proceso Oncológico"),
        ("Tumores Malignos y Benignos", "flowchart TD\n  A[Tumor] --> B{Arquitectura}\n  B -->|Encapsulada| C[Benigno]\n  B -->|Infiltrante| D[Maligno]\n  style D fill:#FFBFBF,stroke:#C10905", "Diferenciación Tumoral")
    ]

    # Split by one or more newlines
    paragraphs = re.split(r'\n\s*\n', full_text)
    
    used_visuals = set()

    for p_text in paragraphs:
        p_text = p_text.strip()
        if not p_text: continue
        
        # Headers are usually short lines without terminal periods
        is_header = len(p_text) < 70 and not p_text.endswith('.') and any(kw in p_text for kw in ["Tolerancia", "Patología", "Mecanismo", "Tumor", "Respuesta", "Cáncer"])
        
        style = header_style if is_header else body_style
        elements.append(Paragraph(p_text.replace('\n', ' '), style))
        
        # Check for visual injection
        for kw, mermaid, title in visual_mappings:
            if title not in used_visuals and kw.lower() in p_text.lower():
                print(f"Inyectando visual: {title}...")
                img_data = get_mermaid_ink_image(mermaid)
                if img_data:
                    elements.append(Spacer(1, 0.1*inch))
                    # Aesthetic size
                    img = Image(img_data, width=2.4*inch, height=1.4*inch)
                    img.hAlign = 'CENTER'
                    elements.append(img)
                    elements.append(Paragraph(f"<i>Esquema: {title}</i>", ParagraphStyle('Fig', parent=styles['Italic'], fontSize=8, alignment=1)))
                    elements.append(Spacer(1, 0.1*inch))
                used_visuals.add(title)
                break

    doc.build(elements)
    print(f"✅ PDF Full Corregido generado en {output_path}")

rebuild_full_pdf("extracted_text.txt", "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria_Full_Final.pdf")
