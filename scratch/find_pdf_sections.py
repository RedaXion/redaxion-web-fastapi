import fitz

pdf_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria.pdf"
doc = fitz.open(pdf_path)

SEARCH_TERMS = [
    "La Tolerancia Inmunitaria",
    "Patologías Relacionadas con la Tolerancia",
    "Mecanismos de la Tolerancia",
    "Tolerancia Central y Periférica", # Might need to check exact wording
    "Diferenciación entre Tumores Malignos y Benignos"
]

results = {}
for term in SEARCH_TERMS:
    for page_num in range(len(doc)):
        page = doc[page_num]
        text_instances = page.search_for(term)
        if text_instances:
            results[term] = page_num
            break

print(results)
doc.close()
