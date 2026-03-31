import os
import json
import redis
import uuid
from flask import Flask, request, jsonify, render_template
from models import SessionLocal, ChatMessage

app = Flask(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    if not data or 'mensagem' not in data:
        return jsonify({"error": "mensagem is required"}), 400
    
    session_id = data.get('session_id') or str(uuid.uuid4())
    user_id = data.get('user_id', 'usr_default')
    
    # Save user message directly to memory so UI can see it immediately
    db = SessionLocal()
    user_msg = ChatMessage(session_id=session_id, user_id=user_id, sender="user", text=data['mensagem'])
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)
    db.close()

    # Invalidate cache for session
    try:
        r.delete(f"chat_cache:{session_id}")
    except Exception as e:
        print(f"Error invalidating cache: {e}")

    # Enqueue work for the agent
    job_payload = {
        "session_id": session_id,
        "user_id": user_id,
        "mensagem": data['mensagem'],
        "timestamp": str(user_msg.timestamp)
    }
    r.lpush('agent_queue', json.dumps(job_payload))

    return jsonify({"status": "queued", "session_id": session_id})

@app.route('/getMessages', methods=['GET'])
def get_messages():
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify([])

    # 1. Tentar ler do Cache no Redis (Muito mais rápido)
    cache_key = f"chat_cache:{session_id}"
    try:
        cached_data = r.get(cache_key)
        if cached_data:
            print(f"Cache HIT for session {session_id}")
            return jsonify(json.loads(cached_data))
    except Exception as e:
        print(f"Redis cache read error: {e}")

    # 2. Se não estiver no cache, busca no Postgres (Fallback)
    print(f"Cache MISS for session {session_id}. Querying Postgres...")
    db = SessionLocal()
    msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.timestamp).all()
    results = [
        {"sender": m.sender, "text": m.text, "timestamp": str(m.timestamp)} for m in msgs
    ]
    db.close()

    # 3. Popula o cache para a próxima chamada
    try:
        if results:
            r.setex(cache_key, 3600, json.dumps(results))
    except Exception as e:
        print(f"Redis cache write error: {e}")
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
