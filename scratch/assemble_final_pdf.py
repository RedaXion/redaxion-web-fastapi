import fitz  # PyMuPDF
import os

DIAGRAMS = [
    {"title": "Mecanismos de Tolerancia Inmunitaria", "file": "diag1.png"},
    {"title": "Categorías de Inmunopatologías", "file": "diag2.png"},
    {"title": "Tolerancia Central y Periférica", "file": "diag3.png"},
    {"title": "Génesis del Cáncer y Tumorogénesis", "file": "diag4.png"},
    {"title": "Diferenciación de Tumores", "file": "diag5.png"}
]

orig_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria.pdf"
new_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria_Con_Esquemas.pdf"
scratch_dir = "/Users/christopherrodriguez/~:Code:RedaXionWeb/redaxion-web-fastapi/scratch"

if not os.path.exists(orig_path):
    print(f"Error: No se encontró el PDF en {orig_path}")
    exit(1)

doc = fitz.open(orig_path)

for diag in DIAGRAMS:
    img_path = os.path.join(scratch_dir, diag["file"])
    if not os.path.exists(img_path):
        print(f"⚠️ Saltando {diag['title']} porque no existe {img_path}")
        continue
    
    print(f"Añadiendo página para: {diag['title']}...")
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 80), diag['title'], fontsize=22, color=(0.29, 0.5, 0.74))
    
    # Insertar imagen
    # Nota: Las capturas de pantalla pueden ser grandes, fitz las ajusta al rect
    img_rect = fitz.Rect(50, 120, 545, 600)
    page.insert_image(img_rect, filename=img_path)
    
    page.insert_text((50, 780), "Generado manualmente por RedaXion Visual Engine (Browser Render)", fontsize=10, color=(0.5, 0.5, 0.5))

doc.save(new_path)
doc.close()
print(f"✅ PDF final generado en: {new_path}")
