import os
import json
import time
import requests
import redis
from sqlalchemy import asc, text as sql_text
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

def fetch_context(embedding, question, db):
    try:
        # Consulta Híbrida usando Reciprocal Rank Fusion (RRF)
        # Combina busca semântica (pgvector) com busca por palavras-chave (FTS)
        hybrid_query = sql_text("""
            WITH semantic_search AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <-> :emb) as rank
                FROM document_chunks
                LIMIT 40
            ),
            keyword_search AS (
                SELECT id, ROW_NUMBER() OVER (
                    ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('portuguese', :query)) DESC
                ) as rank
                FROM document_chunks
                WHERE tsv @@ websearch_to_tsquery('portuguese', :query)
                LIMIT 40
            )
            SELECT dc.id, dc.text, dc.source, 
                   (0.5 * COALESCE(1.0 / (60 + s.rank), 0.0)) + (0.5 * COALESCE(1.0 / (60 + k.rank), 0.0)) as rrf_score
            FROM semantic_search s
            FULL OUTER JOIN keyword_search k ON s.id = k.id
            JOIN document_chunks dc ON dc.id = COALESCE(s.id, k.id)
            ORDER BY rrf_score DESC
            LIMIT 3;
        """)
        
        results = db.execute(hybrid_query, {"emb": str(embedding), "query": question}).fetchall()
        
        # Log retrieved sources
        sources_unique = list(set([res.source for res in results]))
        print(f"RAG Hybrid Retrieval: Found {len(results)} chunks from sources: {sources_unique}")
        
        context = ""
        sources = []
        scores = []
        for idx, res in enumerate(results):
            context += f"--- Documento {idx+1} ({res.source}) ---\n{res.text}\n"
            sources.append(res.source)
            scores.append(str(round(float(res.rrf_score), 4)))
        
        return context, ", ".join(sources), ", ".join(scores)
    except Exception as e:
        print(f"Failed to fetch context: {e}")
        return "", "", ""

def save_chat_cache(session_id, db):
    try:
        # Busca todas as mensagens da sessão ordenadas
        msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(asc(ChatMessage.timestamp)).all()
        results = [
            {
                "sender": m.sender, 
                "text": m.text, 
                "timestamp": str(m.timestamp),
                "response_time": m.response_time,
                "rag_ids": m.rag_ids,
                "rag_scores": m.rag_scores,
                "token_count": m.token_count
            } for m in msgs
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
        "REGRA 1: Responda SOMENTE informações que estão no CONTEXTO DO MANUAL (RAG) abaixo.\n"
        "REGRA 2: Você NÃO DEVE fornecer nenhuma resposta ou conhecimento prévio que não esteja explicitamente escrito no documento da RAG.\n"
        f"CONTEXTO DO MANUAL (RAG):\n{context}\n\n"
        f"HISTÓRICO RECENTE:\n{history}"
    )
    
    model_to_use = "gemma3:4b" 
    try:
        # Logging completo do prompt para o worker
        print("\n" + "="*50)
        print("--- LLM PROMPT ---")
        print(f"SYSTEM:\n{system_prompt}")
        print(f"USER: {question}")
        print("="*50 + "\n")
        
        res = requests.post(f"{OLLAMA_HOST}/api/generate", json={
            "model": model_to_use,
            "prompt": f"Usuário pergunta: {question}\nResponda em português.",
            "system": system_prompt,
            "stream": False
        }, timeout=120)  # inference can be slow
        
        if res.status_code == 200:
            data = res.json()
            answer = data.get("response", "Erro ao processar.")
            tokens = data.get("eval_count", 0)
            return answer, tokens
        print(f"Ollama returned {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Ollama request failed: {e}")
    return "Desculpe, o motor LLM está fora do ar no momento ou encontrei um erro de rede.", 0

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
                    context, rag_ids, rag_scores = fetch_context(emb, question, db) if emb else ("Contexto RAG nao localizado.", "", "")
                    print(f"Context loaded: {len(context)} bytes. IDs: {rag_ids}. Scores: {rag_scores}")
                    
                    # Passo 4.4
                    start_time = time.time()
                    answer_text, token_count = ask_ollama(history, context, question)
                    duration = round(time.time() - start_time, 2)
                    print(f"LLM generated {token_count} tokens in {duration}s")
                    
                    # Passo 4.5
                    assistant_msg = ChatMessage(
                        session_id=session_id, 
                        user_id=user_id, 
                        sender="assistant", 
                        text=answer_text,
                        response_time=duration,
                        rag_ids=rag_ids,
                        rag_scores=rag_scores,
                        token_count=token_count
                    )
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
