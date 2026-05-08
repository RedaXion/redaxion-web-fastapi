import requests
import zlib
import base64
import os
import fitz  # PyMuPDF
from io import BytesIO

# Configuración de Kroki
KROKI_URL = "https://kroki.io/mermaid/png"

DIAGRAMS = [
    {
        "title": "Mecanismos de Tolerancia Inmunitaria",
        "content": "flowchart TD\n  A[Sistema Inmunitario] --> B{Reconocer Antígeno}\n  B -->|Propio| C[Tolerancia]\n  B -->|No Propio| D[Ataque/Destrucción]\n  C --> E[Evita Autoinmunidad]\n  D --> F[Elimina Invasores]\n  style C fill:#DCE5F0,stroke:#4F81BD\n  style E fill:#DAEFD3,stroke:#569F3B"
    },
    {
        "title": "Categorías de Inmunopatologías",
        "content": "flowchart LR\n  A[Fallo en Equilibrio] --> B[Autoinmunidad]\n  A --> C[Inmunodeficiencia]\n  A --> D[Hipersensibilidad]\n  B --> B1[Ataque a lo propio]\n  C --> C1[Respuesta incapaz]\n  D --> D1[Respuesta exagerada]\n  style B fill:#FFBFBF,stroke:#C10905\n  style C fill:#E5E5E5,stroke:#7F7F7F\n  style D fill:#D094E6,stroke:#B553D9"
    },
    {
        "title": "Tolerancia Central y Periférica",
        "content": "flowchart TD\n  A[Linfocitos T Inmaduros] --> B[Selección Central - Timo]\n  B -->|No Reactivos| C[Salida a Sangre]\n  B -->|Auto-Reactivos| D[Apoptosis/Muerte]\n  C --> E[Control Periférico]\n  E -->|Escape de Auto-Reactivos| F[Anergia o Tregs]\n  style B fill:#D8DFEF,stroke:#4A66AC\n  style D fill:#FFBFBF,stroke:#C10905"
    },
    {
        "title": "Génesis del Cáncer y Tumorogénesis",
        "content": "flowchart LR\n  A[Agentes Etiológicos] --> B[Daño al ADN]\n  B --> C{Guardián del ADN}\n  C -->|Reparable| D[Célula Sana]\n  C -->|Irreparable| E[Apoptosis]\n  C -->|Falla Control| F[Tumorogénesis]\n  F --> G[Proliferación Descontrolada]\n  style E fill:#DAEFD3,stroke:#569F3B\n  style F fill:#FFBFBF,stroke:#C10905"
    },
    {
        "title": "Diferenciación de Tumores",
        "content": "flowchart TD\n  A[Tumor] --> B{Arquitectura}\n  B -->|Ordenada/Encapsulada| C[Benigno]\n  B -->|Desordenada/Infiltrada| D[Maligno]\n  C --> E[Curación por Extirpación]\n  D --> F[Riesgo de Metástasis]\n  style C fill:#DAEFD3,stroke:#569F3B\n  style D fill:#FFBFBF,stroke:#C10905"
    }
]

def get_kroki_image(mermaid_code):
    try:
        r = requests.post(KROKI_URL, data=mermaid_code.encode('utf-8'), timeout=30)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print(f"Error Kroki: {e}")
    return None

# Cargar PDF original
orig_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria.pdf"
new_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria_Full_Visuals.pdf"

doc = fitz.open(orig_path)

# Para cada diagrama, crear una nueva página
for diag in DIAGRAMS:
    print(f"Generando: {diag['title']}...")
    img_data = get_kroki_image(diag['content'])
    if not img_data:
        continue
    
    # Crear nueva página A4
    page = doc.new_page(width=595, height=842) # A4
    
    # Insertar Título
    page.insert_text((50, 80), diag['title'], fontsize=22, color=(0.29, 0.5, 0.74)) # Azul pastel
    
    # Insertar Imagen (centrada)
    # Convertir bytes a imagen fitz
    img_rect = fitz.Rect(50, 120, 545, 600)
    page.insert_image(img_rect, stream=img_data)
    
    # Footer
    page.insert_text((50, 780), "Generado por RedaXion Visual Engine", fontsize=10, color=(0.5, 0.5, 0.5))

# Guardar
doc.save(new_path)
doc.close()
print(f"✅ PDF guardado exitosamente en: {new_path}")
