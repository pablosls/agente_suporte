import time
import requests
import uuid

API_URL = "http://localhost:5005/chat"
GET_URL = "http://localhost:5005/getMessages"

questions = [
    {"q": "Quantos bips o alarme soa após a porta ficar aberta por um minuto?", "a": "Dois bips."},
    {"q": "Quantos bips o alarme soa após três minutos de porta aberta?", "a": "Quatro bips."},
    {"q": "O que acontece se a porta ficar aberta por cinco minutos?", "a": "O alarme bipará continuamente e o LED permanecerá aceso."},
    {"q": "Posso manusear o painel de controle com objetos rígidos?", "a": "Não, pois a superfície pode trincar ou riscar."},
    {"q": "Os ajustes no painel de controle podem ser feitos com a porta aberta?", "a": "Não, só podem ser realizados quando a porta do compartimento refrigerador estiver fechada."},
    {"q": "Qual o canal sugerido para buscar vídeos explicativos?", "a": "Canal Panasonic."},
    {"q": "Como visualizar mais informações sobre o uso do painel?", "a": "Acessar o QR Code acima do painel."},
    {"q": "A função SmartSense pode ser desabilitada?", "a": "A função é ligada e desligada com as temperaturas, geralmente operando automaticamente."},
    {"q": "Quanto tempo os indicadores do painel ficam acesos após ativação?", "a": "Permanecerão acesos após 30 segundos."},
    {"q": "Onde posso nivelar os pés do produto caso seja modelo 64?", "a": "Ajustar pela lateral ou removendo a capa de proteção."}
]

print("# Avaliação RAG com 35 Chunks Densos (1 por Imagem)\n")

for i, test in enumerate(questions):
    session_id = str(uuid.uuid4())
    print(f"## Pergunta {i+1}: {test['q']}")
    print(f"**Resposta Ideal Esperada:** {test['a']}")
    
    try:
        res = requests.post(API_URL, json={"mensagem": test["q"], "session_id": session_id})
        if res.status_code != 200:
            print(f"**Resposta do RAG:** ERRO - API falhou com status {res.status_code}\n")
            continue
            
        attempts = 0
        answered = False
        while attempts < 25:
            time.sleep(3)
            msg_res = requests.get(f"{GET_URL}?session_id={session_id}")
            if msg_res.status_code == 200:
                msgs = msg_res.json()
                if len(msgs) > 1 and msgs[-1]['sender'] == 'assistant':
                    print(f"**Resposta do RAG:** {msgs[-1]['text']}\n")
                    answered = True
                    break
            attempts += 1
            
        if not answered:
            print(f"**Resposta do RAG:** Timeout aguardando a API Flask e o Ollama responderem.\n")
    except Exception as e:
        print(f"**Resposta do RAG:** Erro de requisição na API local: {e}\n")
