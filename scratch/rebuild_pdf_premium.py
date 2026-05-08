import os
import requests
import base64
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
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

def create_premium_pdf(output_path, text_content):
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontSize=24, spaceAfter=20, textColor=colors.HexColor("#2E5090")
    )
    heading_style = ParagraphStyle(
        'HeadingStyle', parent=styles['Heading2'], fontSize=16, spaceBefore=15, spaceAfter=10, textColor=colors.HexColor("#4F81BD")
    )
    body_style = ParagraphStyle(
        'BodyStyle', parent=styles['Normal'], fontSize=11, leading=14, spaceAfter=10, alignment=0 # Justified
    )
    
    elements = []
    
    # Title
    elements.append(Paragraph("RedaXion: Tolerancia Inmunitaria y Oncología", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Split text into sections based on keywords found in analysis
    # For speed, I'll simulate the flow based on the content I read earlier.
    
    content = [
        ("La Tolerancia Inmunitaria", 
         "La tolerancia inmunitaria es la capacidad del sistema inmunitario para distinguir entre lo propio y lo no propio. "
         "Esto evita ataques a las células del cuerpo mientras se defienden de invasores externos.",
         "flowchart TD\n  A[Antígeno] --> B{Propio?}\n  B -->|Sí| C[Tolerancia]\n  B -->|No| D[Ataque]\n  style C fill:#DCE5F0,stroke:#4F81BD"),
        
        ("Patologías Relacionadas",
         "Cuando este equilibrio falla, surgen patologías como la autoinmunidad (ataque a lo propio), "
         "la inmunodeficiencia (falta de respuesta) o la hipersensibilidad (respuesta exagerada).",
         "flowchart LR\n  A[Fallo] --> B[Autoinmunidad]\n  A --> C[Inmunodeficiencia]\n  A --> D[Hipersensibilidad]\n  style B fill:#FFBFBF,stroke:#C10905"),
        
        ("Tolerancia Central y Periférica",
         "La tolerancia central ocurre en el timo, donde se eliminan linfocitos T autorreactivos. "
         "La periférica actúa en sangre mediante anergia o células T reguladoras.",
         "flowchart TD\n  A[Timo] --> B[Selección Central]\n  B --> C[Sangre]\n  C --> D[Control Periférico]\n  style B fill:#D8DFEF,stroke:#4A66AC"),
        
        ("Cáncer y Tumorogénesis",
         "El cáncer se origina por mutaciones no reparadas en el ADN. Los agentes etiológicos como radiación o químicos "
         "pueden superar los mecanismos de control celular y dar lugar a la proliferación descontrolada.",
         "flowchart LR\n  A[Daño ADN] --> B{Control?}\n  B -->|Falla| C[Tumorogénesis]\n  style C fill:#FFBFBF,stroke:#C10905"),
        
        ("Tipos de Tumores",
         "Los tumores benignos son encapsulados y ordenados, mientras que los malignos son infiltrantes y desordenados, "
         "con capacidad de metástasis.",
         "flowchart TD\n  A[Tumor] --> B{Maligno?}\n  B -->|No| C[Benigno]\n  B -->|Sí| D[Maligno]\n  style D fill:#FFBFBF,stroke:#C10905")
    ]
    
    for title, text, mermaid in content:
        elements.append(Paragraph(title, heading_style))
        elements.append(Paragraph(text, body_style))
        
        # Insert small image
        img_data = get_mermaid_ink_image(mermaid)
        if img_data:
            # We want it "pequeño" - let's say 2.5 inches wide
            img = Image(img_data, width=2.5*inch, height=1.5*inch)
            img.hAlign = 'CENTER'
            elements.append(img)
            elements.append(Spacer(1, 0.1*inch))

    # Build PDF
    doc.build(elements)
    print(f"✅ PDF Premium generado en {output_path}")

# Run
create_premium_pdf("/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria_Premium.pdf", "")
