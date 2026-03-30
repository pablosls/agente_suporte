import os
import json
import time
import requests
from models import init_db, SessionLocal, DocumentChunk


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

def wait_for_ollama():
    print("Waiting for Ollama to be ready...")
    start_time = time.time()
    while True:
        try:
            res = requests.get(f"{OLLAMA_HOST}/")
            if res.status_code == 200:
                print("Ollama is ready!")
                break
        except Exception:
            pass
        if time.time() - start_time > 60:
            print("Timeout waiting for Ollama")
            break
        time.sleep(2)

def pull_models():
    # Use gemma2:2b as a reliable fallback if gemma3:4b is not in the registry yet, but we request the exact spec name.
    models = ["nomic-embed-text"] 
    for model in models:
        print(f"Pulling model {model} (this may take a few minutes)...")
        try:
            res = requests.post(f"{OLLAMA_HOST}/api/pull", json={"name": model}, stream=True)
            for line in res.iter_lines():
                pass # Suppress noisy output, but wait for completion
            print(f"Model {model} pulled successfully.")
        except Exception as e:
            print(f"Error pulling model {model}: {e}")

def generate_embedding(text):
    try:
        res = requests.post(f"{OLLAMA_HOST}/api/embeddings", json={
            "model": "nomic-embed-text",
            "prompt": text
        })
        if res.status_code == 200:
            return res.json().get("embedding")
        else:
            print(f"Failed to generate embedding: {res.text}")
    except Exception as e:
        print(f"Error generating embedding: {e}")
    return None

def load_json_and_embed():
    json_path = "/app/geladeira_images_extracted.json"
    if not os.path.exists(json_path):
        print(f"JSON not found at {json_path}. Make sure it is mounted.")
        return

    db = SessionLocal()
    
    # Limpa dados antigos
    apagados = db.query(DocumentChunk).delete()
    db.commit()
    print(f"Banco de dados limpo! Removidos {apagados} chunks antigos.")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Generating embeddings for {len(data)} images chunks...")
    chunks_inseridos = 0
    
    for idx, item in enumerate(data):
        text = item.get("text")
        if not text or not text.strip():
            text = f"Página {idx+1} (Imagem sem texto detectado ou em branco)."
            
        # Protect against Ollama "input length exceeds the context length" error
        if len(text) > 5000:
            text = text[:5000]
            
        emb = generate_embedding(text)
        if emb:
            doc = DocumentChunk(text=text, embedding=emb)
            db.add(doc)
            chunks_inseridos += 1
            if chunks_inseridos % 5 == 0:
                print(f"Inserted image chunk {chunks_inseridos}/{len(data)}")
        else:
            print(f"ALERTA: Falha absoluta ao gerar embedding para a imagem {idx+1}")
        
    db.commit()
    db.close()
    print(f"RAG Documents loaded successfully! Total: {chunks_inseridos} chunks.")

if __name__ == "__main__":
    init_db()
    wait_for_ollama()
    pull_models()
    load_json_and_embed()
