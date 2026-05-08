import fitz
import requests
import base64
import os

def get_mermaid_ink_image(mermaid_code):
    b64_code = base64.b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
    url = f"https://mermaid.ink/img/{b64_code}"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print(f"Error: {e}")
    return None

DIAGRAMS = [
    {
        "title": "Mecanismos de Tolerancia Inmunitaria",
        "content": "flowchart TD\n  A[Sistema Inmunitario] --> B{Reconocer Antígeno}\n  B -->|Propio| C[Tolerancia]\n  B -->|No Propio| D[Ataque/Destrucción]\n  C --> E[Evita Autoinmunidad]\n  D --> F[Elimina Invasores]\n  style C fill:#DCE5F0,stroke:#4F81BD\n  style E fill:#DAEFD3,stroke:#569F3B",
        "after_page": 0
    },
    {
        "title": "Categorías de Inmunopatologías",
        "content": "flowchart LR\n  A[Fallo en Equilibrio] --> B[Autoinmunidad]\n  A --> C[Inmunodeficiencia]\n  A --> D[Hipersensibilidad]\n  B --> B1[Ataque a lo propio]\n  C --> C1[Respuesta incapaz]\n  D --> D1[Respuesta exagerada]\n  style B fill:#FFBFBF,stroke:#C10905\n  style C fill:#E5E5E5,stroke:#7F7F7F\n  style D fill:#D094E6,stroke:#B553D9",
        "after_page": 0
    },
    {
        "title": "Tolerancia Central y Periférica",
        "content": "flowchart TD\n  A[Linfocitos T Inmaduros] --> B[Selección Central - Timo]\n  B -->|No Reactivos| C[Salida a Sangre]\n  B -->|Auto-Reactivos| D[Apoptosis/Muerte]\n  C --> E[Control Periférico]\n  E -->|Escape de Auto-Reactivos| F[Anergia o Tregs]\n  style B fill:#D8DFEF,stroke:#4A66AC\n  style D fill:#FFBFBF,stroke:#C10905",
        "after_page": 1
    },
    {
        "title": "Génesis del Cáncer y Tumorogénesis",
        "content": "flowchart LR\n  A[Agentes Etiológicos] --> B[Daño al ADN]\n  B --> C{Guardián del ADN}\n  C -->|Reparable| D[Célula Sana]\n  C -->|Irreparable| E[Apoptosis]\n  C -->|Falla Control| F[Tumorogénesis]\n  F --> G[Proliferación Descontrolada]\n  style E fill:#DAEFD3,stroke:#569F3B\n  style F fill:#FFBFBF,stroke:#C10905",
        "after_page": 5
    },
    {
        "title": "Diferenciación de Tumores",
        "content": "flowchart TD\n  A[Tumor] --> B{Arquitectura}\n  B -->|Ordenada/Encapsulada| C[Benigno]\n  B -->|Desordenada/Infiltrada| D[Maligno]\n  C --> E[Curación por Extirpación]\n  D --> F[Riesgo de Metástasis]\n  style C fill:#DAEFD3,stroke:#569F3B\n  style D fill:#FFBFBF,stroke:#C10905",
        "after_page": 5
    }
]

orig_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria.pdf"
new_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria_Final.pdf"

doc = fitz.open(orig_path)

# Para evitar líos con los índices que cambian, vamos de atrás hacia adelante
# O mejor, usamos una lista de pares (página_original, datos_imagen) y reconstruimos.
# Pero lo más fácil es: ordenar por 'after_page' descendente.
DIAGRAMS.sort(key=lambda x: x['after_page'], reverse=True)

for diag in DIAGRAMS:
    print(f"Insertando {diag['title']} después de página {diag['after_page']}...")
    img_data = get_mermaid_ink_image(diag['content'])
    if not img_data:
        continue
    
    # Insertar página después de 'after_page'
    # doc.insert_page(pno, ...) inserta en la posición pno.
    # Si queremos después de 0, insertamos en 1.
    target_pos = diag['after_page'] + 1
    page = doc.new_page(pno=target_pos, width=595, height=842)
    
    # Título
    page.insert_text((50, 80), diag['title'], fontsize=22, color=(0.29, 0.5, 0.74))
    
    # Imagen
    img_rect = fitz.Rect(50, 120, 545, 600)
    page.insert_image(img_rect, stream=img_data)
    
    # Footer
    page.insert_text((50, 780), "Visualización integrada por RedaXion Engine", fontsize=10, color=(0.5, 0.5, 0.5))

doc.save(new_path)
doc.close()
print(f"✅ PDF Final (Integrado) generado en: {new_path}")
