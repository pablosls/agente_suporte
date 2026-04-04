import requests
import threading
import uuid
import time

# URL do endpoint Flask-API (mapeado para 5005 no host)
URL = "http://localhost:5005/chat"

def simulate_user(user_index):
    session_id = str(uuid.uuid4())
    payload = {
        "mensagem": f"Usuário {user_index}: Como devo limpar o filtro da geladeira?",
        "session_id": session_id,
        "user_id": f"user_sim_{user_index}"
    }
    
    print(f"🚀 [User {user_index}] Enviando pergunta com Session: {session_id}")
    try:
        start_time = time.time()
        response = requests.post(URL, json=payload)
        elapsed = round(time.time() - start_time, 2)
        
        if response.status_code == 200:
            print(f"✅ [User {user_index}] Sucesso! Resposta da API: {response.json().get('status')} em {elapsed}s")
        else:
            print(f"❌ [User {user_index}] Erro: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"💥 [User {user_index}] Falha na conexão: {e}")

def main():
    threads = []
    print(f"🏁 Iniciando simulação de 10 usuários simultâneos em {URL}...")
    
    for i in range(1, 11):
        t = threading.Thread(target=simulate_user, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
        
    print("\n🏁 Simulação concluída. Verifique os logs do 'agent_worker' para ver o processamento da fila.")

if __name__ == "__main__":
    main()
