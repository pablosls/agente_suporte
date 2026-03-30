import os
import json
import time
import requests
import redis
from sqlalchemy import asc
from models import SessionLocal, ChatMessage, DocumentChunk

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Wait until Redis is up
while True:
    try:
        r = redis.from_url(REDIS_URL)
        r.ping()
        break
    except redis.ConnectionError:
        print("Waiting for Redis...")
        time.sleep(2)

def get_history(session_id, db):
    msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(asc(ChatMessage.timestamp)).limit(10).all()
    history = ""
    for m in msgs:
        prefix = "Usuário" if m.sender == "user" else "Assistente"
        history += f"{prefix}: {m.text}\n"
    return history

def get_embedding(text):
    try:
        res = requests.post(f"{OLLAMA_HOST}/api/embeddings", json={
            "model": "nomic-embed-text",
            "prompt": text
        }, timeout=10)
        if res.status_code == 200:
            return res.json().get("embedding")
    except Exception as e:
        print(f"Error fetching embedding: {e}")
    return None

def fetch_context(embedding, db):
    try:
        docs = db.query(DocumentChunk).order_by(DocumentChunk.embedding.l2_distance(embedding)).limit(3).all()
        context = ""
        for idx, d in enumerate(docs):
            context += f"--- Documento {idx+1} ({d.source}) ---\n{d.text}\n"
        return context
    except Exception as e:
        print(f"Failed to fetch context: {e}")
        return ""

def save_chat_cache(session_id, db):
    try:
        # Busca todas as mensagens da sessão ordenadas
        msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(asc(ChatMessage.timestamp)).all()
        results = [
            {"sender": m.sender, "text": m.text, "timestamp": str(m.timestamp)} for m in msgs
        ]
        # Salva no Redis com TTL de 1 hora (3600s)
        cache_key = f"chat_cache:{session_id}"
        r.setex(cache_key, 3600, json.dumps(results))
        print(f"Cache updated for session {session_id} ({len(results)} messages)")
    except Exception as e:
        print(f"Failed to update cache: {e}")

def ask_ollama(history, context, question):
    system_prompt = (
        "Você é um assistente virtual especialista operando ESTRITAMENTE sob um sistema RAG de busca em manuais de geladeira.\n"
        "REGRA 1: Responda SOMENTE e 100% com base nas informações que estão no CONTEXTO DO MANUAL (RAG) abaixo.\n"
        "REGRA 2: Você NÃO DEVE fornecer nenhuma resposta ou conhecimento prévio que não esteja explicitamente escrito no documento da RAG.\n"
        "REGRA 3: Caso não encontre um documento relacionado ou a informação solicitada não esteja no CONTEXTO, você DEVE INFORMAR EXATAMENTE: 'Não encontrei a informação solicitada no manual'.\n\n"
        f"CONTEXTO DO MANUAL (RAG):\n{context}\n\n"
        f"HISTÓRICO RECENTE:\n{history}"
    )
    
    model_to_use = "gemma3:4b" 
    try:
        res = requests.post(f"{OLLAMA_HOST}/api/generate", json={
            "model": model_to_use,
            "prompt": f"Usuário pergunta: {question}\nResponda em português.",
            "system": system_prompt,
            "stream": False
        }, timeout=120)  # inference can be slow
        
        if res.status_code == 200:
            return res.json().get("response", "Erro ao processar.")
        print(f"Ollama returned {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Ollama request failed: {e}")
    return "Desculpe, o motor LLM está fora do ar no momento ou encontrei um erro de rede."

def process_queue():
    print("Agent Worker Started. Waiting for queue 'agent_queue'...")
    while True:
        try:
            task = r.brpop('agent_queue', timeout=5)
            if task:
                _, payload_str = task
                payload = json.loads(payload_str)
                session_id = payload['session_id']
                user_id = payload['user_id']
                question = payload['mensagem']
                
                print(f"Processing query for session {session_id}: {question[:30]}...")
                
                db = SessionLocal()
                try:
                    # Passo 4.2
                    history = get_history(session_id, db)
                    
                    # Passo 4.3
                    emb = get_embedding(question)
                    context = fetch_context(emb, db) if emb else "Contexto RAG nao localizado."
                    print(f"Context loaded: {len(context)} bytes")
                    
                    # Passo 4.4
                    answer_text = ask_ollama(history, context, question)
                    print(f"LLM generated {len(answer_text)} chars of text")
                    
                    # Passo 4.5
                    assistant_msg = ChatMessage(session_id=session_id, user_id=user_id, sender="assistant", text=answer_text)
                    db.add(assistant_msg)
                    db.commit()
                    print("Answer saved to DB.")
                    
                    # Atualiza o Cache no Redis para o endpoint da API ler rápido
                    save_chat_cache(session_id, db)
                except Exception as e:
                    print(f"Agent logic error: {e}")
                    db.rollback()
                finally:
                    db.close()
        except KeyboardInterrupt:
            break
        except Exception as queue_err:
            print(f"Queue error: {queue_err}")
            time.sleep(2)

if __name__ == '__main__':
    process_queue()
