import fitz

pdf_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria.pdf"
doc = fitz.open(pdf_path)

for page_num in range(len(doc)):
    page = doc[page_num]
    blocks = page.get_text("blocks")
    # blocks is a list of (x0, y0, x1, y1, "text", block_no, block_type)
    print(f"--- Página {page_num} ---")
    if blocks:
        last_block = blocks[-1]
        print(f"Último bloque en y1={last_block[3]} de un total de 842")
    else:
        print("Página vacía")

doc.close()
