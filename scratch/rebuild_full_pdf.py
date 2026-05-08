import os
import requests
import base64
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

    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10, leading=12, spaceAfter=8)
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor("#2E5090"), spaceBefore=12, spaceAfter=6)

    elements = []
    
    # Mapping of keywords to mermaid diagrams
    visual_mappings = [
        ("Mecanismos de la Tolerancia", "flowchart TD\n  A[Antígeno] --> B{Propio?}\n  B -->|Sí| C[Tolerancia]\n  B -->|No| D[Ataque]\n  style C fill:#DCE5F0,stroke:#4F81BD", "Concepto de Tolerancia"),
        ("Patologías Relacionadas", "flowchart LR\n  A[Fallo] --> B[Autoinmunidad]\n  A --> C[Inmunodeficiencia]\n  A --> D[Hipersensibilidad]\n  style B fill:#FFBFBF,stroke:#C10905", "Inmunopatologías"),
        ("Tolerancia Central y Periférica", "flowchart TD\n  A[Timo] --> B[Selección Central]\n  B --> C[Sangre]\n  C --> D[Control Periférico]\n  style B fill:#D8DFEF,stroke:#4A66AC", "Mecanismos de Selección"),
        ("tumorogénesis", "flowchart LR\n  A[Daño ADN] --> B{Falla Control}\n  B --> C[Tumorogénesis]\n  style C fill:#FFBFBF,stroke:#C10905", "Proceso Oncológico"),
        ("Tumores Malignos y Benignos", "flowchart TD\n  A[Tumor] --> B{Arquitectura}\n  B -->|Encapsulada| C[Benigno]\n  B -->|Infiltrante| D[Maligno]\n  style D fill:#FFBFBF,stroke:#C10905", "Diferenciación Tumoral")
    ]

    # Split into paragraphs
    paragraphs = full_text.split('\n\n')
    
    for p_text in paragraphs:
        p_text = p_text.strip()
        if not p_text: continue
        
        # Check if it looks like a header (short, capital letters or specific words)
        is_header = len(p_text) < 60 and any(kw in p_text for kw in ["Tolerancia", "Patología", "Mecanismo", "Tumor", "Radioterapia"])
        
        style = header_style if is_header else body_style
        elements.append(Paragraph(p_text.replace('\n', ' '), style))
        
        # Check for visual injection
        for kw, mermaid, title in visual_mappings:
            if kw.lower() in p_text.lower():
                print(f"Inyectando visual: {title}...")
                img_data = get_mermaid_ink_image(mermaid)
                if img_data:
                    elements.append(Spacer(1, 0.1*inch))
                    # Smaller image: 2 inch width
                    img = Image(img_data, width=2.0*inch, height=1.2*inch)
                    img.hAlign = 'CENTER'
                    elements.append(img)
                    elements.append(Paragraph(f"<i>Figura: {title}</i>", ParagraphStyle('Fig', parent=styles['Italic'], fontSize=8, alignment=1)))
                    elements.append(Spacer(1, 0.1*inch))
                # Remove to avoid duplicate injection if same keyword appears
                visual_mappings.remove((kw, mermaid, title))
                break

    doc.build(elements)
    print(f"✅ PDF Full Integrado generado en {output_path}")

rebuild_full_pdf("extracted_text.txt", "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria_Full_Corregido.pdf")
