import fitz
import sys

pdf_path = "/Users/christopherrodriguez/Desktop/Tolerancia_Inmunitaria.pdf"
doc = fitz.open(pdf_path)
full_text = ""
for page in doc:
    full_text += page.get_text()
doc.close()

with open("extracted_text.txt", "w") as f:
    f.write(full_text)
print(f"Text extracted. Total length: {len(full_text)}")
