import os
import requests
from io import BytesIO
from openai import OpenAI

# Initialize OpenAI client for keyword extraction
client = None
if os.getenv("OPENAI_API_KEY"):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

def get_image_search_query(context_text: str) -> str:
    """
    Uses GPT-4o to extract a good search query for a stock photo website
    based on the provided text context.
    """
    if not client:
        return "abstract academic background"

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a picture editor. I will give you a Section Title from a medical/academic book. Convert it into a simple 2-3 word English search query for a stock photo. Output ONLY the query."},
                {"role": "user", "content": f"Title: {context_text}"}
            ],
            temperature=0.3,
            max_tokens=20
        )
        query = response.choices[0].message.content.strip()
        # Remove quotes if present
        query = query.replace('"', '').replace("'", "")
        print(f"🔍 Query de imagen generada: '{query}'")
        return query
    except Exception as e:
        print(f"Error fetching image query: {e}")
        return "medicine academic"

def generate_image_from_text(context_text: str) -> BytesIO:
    """
    1. Generates a search query from text using ChatGPT.
    2. Searches Unsplash for a high-quality image.
    3. Falls back to generic queries if original fails.
    4. Returns the image as BytesIO.
    """
    if not UNSPLASH_ACCESS_KEY:
        print("Warning: No UNSPLASH_ACCESS_KEY. Skipping image search.")
        return None

    # Get primary query from GPT
    primary_query = get_image_search_query(context_text)
    
    # Fallback queries if primary fails
    fallback_queries = [
        primary_query,
        "education learning",
        "university students",
        "academic books",
        "medical science",
        "classroom teaching"
    ]
    
    url = "https://api.unsplash.com/search/photos"
    headers = {
        "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"
    }

    for query in fallback_queries:
        try:
            print(f"🖼️ Buscando imagen en Unsplash: {query}...")
            params = {
                "query": query,
                "per_page": 1,
                "orientation": "landscape",
                "order_by": "relevant"
            }
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data["results"]:
                # Get the 'regular' size url
                image_url = data["results"][0]["urls"]["regular"]
                
                # Download the image
                img_response = requests.get(image_url)
                img_response.raise_for_status()
                
                print(f"✅ Imagen descargada exitosamente para: {query}")
                return BytesIO(img_response.content)
            else:
                print(f"⚠️ No se encontraron imágenes para: {query}")
                continue  # Try next fallback
                
        except Exception as e:
            print(f"❌ Error searching image for '{query}': {e}")
            continue  # Try next fallback
    
    print("⚠️ Ninguna query encontró imágenes. Continuando sin imagen.")
    return None
