# Packages
import os, sys
import requests
import urllib.parse as url_parse
from bs4 import BeautifulSoup
from groq import Groq

# --- CONFIGURAÇÕES ---
NEWS_API_KEY = os.environ.get('NEWS_API_KEY')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
URL_GREEN_API = os.environ.get('URL_GREEN_API')
CHAT_ID = os.environ.get('CHAT_ID')
BOT_API_KEY = os.environ.get('BOT_API_KEY')
ZAP_ID = os.environ.get('ZAP_ID')

# Arquivo com notícias já enviadas
ARQUIVO_HISTORICO = 'historico_noticias.txt'
LIMITE_HISTORICO = 50 # Mantém apenas as últimas 50 notícias no arquivo para controle de tamanho

# Inicializa o cliente do Groq
groq_client = Groq(api_key=GROQ_API_KEY)

## Funções
def carregar_historico():
    """Carrega a lista de URLs já enviadas anteriormente."""
    if not os.path.exists(ARQUIVO_HISTORICO):
        return set()
    with open(ARQUIVO_HISTORICO, 'r', encoding='utf-8') as f:
        return set(linha.strip() for linha in f if linha.strip())

def salvar_no_historico(url):
    """Adiciona uma nova URL ao arquivo de histórico e remove as mais antigas se passar do limite."""
    historico = list(carregar_historico())
    
    if url not in historico:
        historico.append(url)
        
    # Mantém apenas os últimos X registros para não acumular lixo
    if len(historico) > LIMITE_HISTORICO:
        historico = historico[-LIMITE_HISTORICO:]
        
    with open(ARQUIVO_HISTORICO, 'w', encoding='utf-8') as f:
        for item in historico:
            f.write(f"{item}\n")

def extrair_texto_url(url):
    """Baixa a página web e extrai o texto principal tratando erros."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        resposta = requests.get(url, headers=headers, timeout=8)
        if resposta.status_code != 200:
            return None
            
        soup = BeautifulSoup(resposta.text, 'html.parser')
        for elemento in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            elemento.decompose()
            
        texto = soup.get_text(separator=' ')
        linhas = [linha.strip() for list_linha in texto.splitlines() for line in list_linha.split("  ") if (linha := line.strip())]
        return " ".join(linhas)[:4000]
    except Exception:
        return None

def gerar_resumo_groq(texto_artigo, descricao_fallback):
    """Gera o resumo usando o modelo rápido llama3-8b-8192."""
    conteudo_para_ia = texto_artigo if texto_artigo else descricao_fallback
    if not conteudo_para_ia or len(conteudo_para_ia) < 30:
        return "Resumo indisponível devido a restrições de acesso ao site."
        
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "Você é um assistente focado em tecnologia. Seu trabalho é ler o texto enviado e extrair um resumo estrito de no máximo 2 linhas, focado no impacto prático ou na novidade da notícia. Responda obrigatoriamente em português brasileiro, de forma direta e sem preâmbulos."
                },
                {
                    "role": "user",
                    "content": f"Resuma a seguinte notícia:\n\n{conteudo_para_ia}"
                }
            ],
            model="openai/gpt-oss-20b",
            temperature=0.2,
            max_completion_tokens=1200
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Erro na API do Groq: {str(e)}")
        return "Erro ao processar resumo com IA."

def buscar_e_resumir_noticias():
    """Busca notícias, filtra duplicadas pelo histórico e monta o relatório."""
    fontes_confiaveis = "techcrunch.com,theverge.com,wired.com,technologyreview.com,bloomberg.com,reuters.com,arstechnica.com"

    url = (
        f"https://newsapi.org/v2/everything?"
        f"q=Artificial Intelligence OR AI OR IA&"
        f"domains={fontes_confiaveis}&"
        f"sortBy=relevance&"
        f"pageSize=15&"  # Buscamos 15 para garantir que, após filtrar as repetidas, ainda sobrem 5 novas
        f"apiKey={NEWS_API_KEY}"
    )
    headers = {"User-Agent": "MeuAppDeNoticias/1.0"}

    try:
        resposta = requests.get(url, headers=headers, timeout=10)
        dados = resposta.json()
    except Exception as e:
        print(f"❌ Erro ao conectar com a NewsAPI: {str(e)}")
        return None
        
    artigos = dados.get("articles", [])
    if not artigos:
        print("Nenhuma notícia encontrada.")
        return None
        
    # Carrega o histórico de links já enviados
    urls_enviadas = carregar_historico()

    mensagens = []
    mensagem = "*🤖 Resumo Inteligente de IA 🤖*\n\n"
    contagem_novas = 0
    
    for artigo in artigos:
        # Se já coletamos as 5 notícias inéditas do dia, encerra o loop
        if contagem_novas >= 5:
            break
            
        url_artigo = artigo.get("url")
        
        # --- SISTEMA DE FILTRO ---
        # Ignora se a URL já estiver no arquivo de histórico
        if url_artigo in urls_enviadas:
            continue
            
        titulo = artigo.get("title")
        descricao = artigo.get("description")
        fonte_nome = artigo.get("source", {}).get("name", "Fonte")
        
        contagem_novas += 1
        print(f"Processando nova notícia {contagem_novas}: {titulo[:40]}...")
        
        # Raspagem e resumo IA
        texto_completo = extrair_texto_url(url_artigo)
        resumo = gerar_resumo_groq(texto_completo, descricao)
        
        # Monta a mensagem
        mensagem += f"*{contagem_novas}. {titulo}*\n"
        mensagem += f"🏢 _Fonte: {fonte_nome}_\n"
        mensagem += f"📝 _{resumo}_\n"
        mensagem += f"🔗 {url_artigo}\n"

        mensagens.append(mensagem)
        mensagem = ''

        # Grava a URL no histórico para não repetir nas próximas execuções
        salvar_no_historico(url_artigo)
        
    # Se nenhuma notícia nova foi encontrada no lote
    if contagem_novas == 0:
        print("Sua lista está atualizada! Nenhuma notícia inédita nas últimas horas.")
        mensagens.append("*🤖 Resumo Inteligente de IA 🤖*\n\n Nenhuma notícia inédita no último dia!")
        return mensagens
        
    return mensagens

def enviar_whatsapp_green(conteudo):
    """Dispara a mensagem final para o WhatsApp."""
    if not conteudo:
        return

    for conteudo_i in conteudo:
        try:
            url = URL_GREEN_API

            payload = {
                "chatId": CHAT_ID, 
                "message": conteudo_i, 
                "typingTime": "1000", 
                "linkPreview": False
            }
            headers = {
            'Content-Type': 'application/json'
            }
            
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            print("🚀 Relatório enviado sem repetições!")
        except Exception as e:
            print(f"❌ Erro ao enviar mensagem: {str(e)}")

def enviar_whatsapp(conteudo):
    """Dispara a mensagem final para o WhatsApp."""
    if not conteudo:
        return
    for conteudo_i in conteudo:
        try:
            conteudo_parsed = url_parse.quote(conteudo_i)
            url = f"https://api.callmebot.com/whatsapp.php?phone={ZAP_ID}&text={conteudo_parsed}&apikey={BOT_API_KEY}"
            response = requests.post(url)
            response.raise_for_status()
            print("🚀 Relatório enviado sem repetições!")
        except Exception as e:
            print(f"❌ Erro ao enviar mensagem: {str(e)}")


if __name__ == "__main__":
    relatorio_noticias = buscar_e_resumir_noticias()
    enviar_whatsapp(relatorio_noticias)