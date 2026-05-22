# captcha-solver

> **Aviso:** Este projeto tem finalidade exclusivamente educacional, demonstrando técnicas de visão computacional aplicadas ao reconhecimento de padrões em imagens.

Microsserviço que resolve captchas de rotação de imagem da Sky Mavis utilizando visão computacional com YOLO. Expõe uma API REST para resolução assíncrona, com pré-cache e suporte a rotação de proxies.

## Treinamento do Modelo YOLO

O modelo `best.pt` foi treinado para detectar a orientação correta do captcha. O processo de criação do dataset seguiu estas etapas:

O captcha é uma imagem de um Axie rotacionada aleatoriamente; a orientação correta é quando o Axie está em pé:

![Captcha do Axie](axie.png)

1. **Coleta das imagens** — para conseguir as imagens para treinar o modelo fiz um script simples que faz requisições para `https://x.skymavis.com/captcha-srv/check`, extrai o base64 da resposta, converte para `.png` e salva. Foram coletados aproximadamente **200 captchas**.

2. **Geração das rotações** — cada captcha original é rotacionado 12 vezes (0°, 30°, 60°, ..., 330°), gerando 12 variações por captcha. Apenas uma delas está na orientação correta (imagem direita, sem rotação).

3. **Rotulagem** — as imagens foram anotadas manualmente no [makesense.ai](https://www.makesense.ai/), marcando com bounding box apenas as imagens que estavam na orientação correta. As demais 11 rotações de cada captcha permanecem sem anotação (fundo/negativo).

4. **Treinamento** — com o dataset rotulado, o YOLO foi treinado para identificar em qual dos 12 ângulos o objeto está presente. Durante a inferência, o solver testa cada ângulo e aquele onde o modelo encontra um objeto é considerado o correto.

## Arquitetura

```
GET /submit         →  solicita solução de captcha → { request_id }
GET /result/<id>    →  consulta resultado           → { status, data }
GET /cache/status   →  status do cache              → { cache_size, ... }
POST /add-captcha   →  alimenta cache externamente  → { status, cache_size }
```

## Requisitos

- Python 3.10+
- `model/best.pt` (pesos do YOLO)

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
python main.py
# Servidor inicia em http://0.0.0.0:6000
```

### API

```bash
curl http://localhost:6000/submit
# → { "request_id": "abc-123" }

curl http://localhost:6000/result/abc-123
# → { "status": "ready", "data": { ... } }

curl http://localhost:6000/cache/status
# → { "cache_size": 3, "cache_max_size": 5, "cache_percentage": 60.0 }

curl -X POST http://localhost:6000/add-captcha \
  -H "Content-Type: application/json" \
  -d '{"id": "abc-123", "result": 90}'
# → { "status": "ok", "cache_size": 4, "cache_max_size": 5 }
```

### Proxies

Caso queira utilizar proxies adicione uma URL de proxy por linha no arquivo `proxies.txt`:

```
http://user:pass@proxy1:8080
http://user:pass@proxy2:8080
```

## Estrutura do Projeto

```
captcha-solver/
├── main.py                      # Ponto de entrada
├── requirements.txt             # Dependências
├── proxies.txt                  # Lista de proxies (opcional)
├── model/
│   └── best.pt                  # Pesos do modelo YOLO
└── utils/
    ├── captchaSkyMavis.py       # Servidor Flask, pool de modelos, cache, solver
    └── base64ToImage.py         # Conversor Base64 → PIL Image
```

## Funcionamento

1. Obtém a imagem do captcha de `x.skymavis.com/captcha-srv/check`
2. Recorta a bounding box e rotaciona a imagem em incrementos de 30° (0°–330°)
3. Executa detecção YOLO em cada rotação — o ângulo onde um objeto é detectado é a orientação correta
4. Converte o ângulo para o formato esperado pela API e envia para `/captcha-srv/submit`

O endpoint `/add-captcha` permite que máquinas externas alimentem o cache com captchas já resolvidos (enviando `id` e `result`). Dessa forma a API se torna escalável: instâncias auxiliares podem resolver captchas de forma independente e enviar os resultados para a instância central.

## Configuração

Todas as constantes estão em `utils/captchaSkyMavis.py`:

| Constante | Padrão | Descrição |
|---|---|---|
| `MODEL_POOL_SIZE` | 8 | Instâncias YOLO concorrentes |
| `CACHE_SIZE` | 5 | Máx. de captchas pré-resolvidos em cache |
| `CACHE_TIMEOUT` | 30 | Validade de cada captcha no cache (segundos) |
| `APP_KEY` | `5a0eb357-...` | Chave da API Sky Mavis |
