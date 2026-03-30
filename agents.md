# 🤖 Especificação de Agentes e Serviços

Este documento detalha os componentes inteligentes e de suporte que compõem o ecossistema do Assistente de Geladeira RAG.

---

## 🧠 1. Agent Assistente (O Cérebro)

O **Agent Assistente** é o coração do sistema. Ele opera como um worker assíncrono que processa as dúvidas dos usuários.

- **Papel**: Orquestrar a recuperação de contexto e a geração de respostas.
- **Fluxo de Trabalho**:
    1. **Consumo**: Retira mensagens da `Redis Queue` (`agent_queue`).
    2. **Busca de Memória**: Consulta o Postgres para obter as últimas 10 mensagens da sessão.
    3. **Recuperação Vetorial (RAG)**:
        - Gera o embedding da pergunta usando `nomic-embed-text`.
        - Realiza busca por similaridade de L2 Distance na tabela `document_chunks`.
    4. **Inferência**: Envia o prompt blindado (System Prompt) para o `Ollama` com o modelo `gemma3:4b`.
    5. **Persistência**: Envia a resposta para o **Memory Service**.

- **Ferramentas**:
    - `Ollama API (gemma3:4b)`
    - `SQLAlchemy + PGVector`
    - `Redis (LPUSH/BRPOP)`

---

## 📥 2. Service Load RAG Documents (Agente de Ingestão)

Este é um agente de execução única (Job) ou periódica, responsável por transformar documentos brutos em conhecimento consultável.

- **Papel**: ETL (Extract, Transform, Load) de documentos técnicos.
- **Capacidades**:
    - **Leitura**: Processa PDFs usando processamento OCR de alta precisão.
    - **Chunking**: Divide o texto em blocos semânticos para otimizar a janela de contexto.
    - **Embedding**: Converte texto em vetores numéricos de 768 dimensões.
- **Ferramentas**:
    - `Docling (OCR)`
    - `Nomic Embeddings`
    - `PostgreSQL (PGVector)`

---

## 💾 3. Memory Service (Gestor de Estado)

Embora integrado logicamente à API e ao Agent, o **Memory Service** atua como o guardião da consistência da conversa.

- **Papel**: Garantir que o histórico esteja disponível de forma rápida e persistente.
- **Estratégia Híbrida**:
    - **Persistence Layer**: Salva cada mensagem na tabela `chat_messages` do Postgres para durabilidade.
    - **Cache Layer**: Mantém um `snapshot` JSON da conversa no Redis com TTL de 1 hora para servir o polling da API instantaneamente.
- **Ferramentas**:
    - `PostgreSQL`
    - `Redis (SETEX/GET)`

---

## 🔄 Interação entre Serviços

1. O **Usuário** interage com a **Flask API**.
2. A **API** delega a tarefa pesada para a **Redis Queue**.
3. O **Agent Assistente** resolve a lógica e "fala" com o **Memory Service**.
4. O **Memory Service** atualiza o **Redis Cache** e o **Postgres**.
5. A **API** lê do **Redis Cache** e responde ao **Usuário**.
