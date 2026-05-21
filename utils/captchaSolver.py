import os
import cv2
import numpy as np
from ultralytics import YOLO

model = YOLO("./model/best.pt")

def rotacionar_imagem(imagem, graus_por_rotacao=30, num_variacoes=12):
    imagem_original = imagem.crop(imagem.getbbox())
    if imagem_original.mode == 'RGBA':
        imagem_original = imagem_original.convert('RGB')
    imagem_original.save('./captcha/axie_0.jpg')
    for i in range(1, num_variacoes + 1):
        imagem_rotacionada = imagem.rotate(-graus_por_rotacao * i, expand=True)
        imagem_rotacionada = imagem_rotacionada.crop(imagem_rotacionada.getbbox())
        if imagem_rotacionada.mode == 'RGBA':
            imagem_rotacionada = imagem_rotacionada.convert('RGB')
        imagem_rotacionada.save(f'./captcha/axie_{i * graus_por_rotacao}.jpg')

def solveCaptcha(pasta_imagens, confianca_minima=0.5):
    melhor_arquivo = None
    melhor_confianca = 0

    for nome_arquivo in os.listdir(pasta_imagens):
        caminho_imagem = os.path.join(pasta_imagens, nome_arquivo)
        if not caminho_imagem.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue 

        img = cv2.imread(caminho_imagem)
        if img is None:
            continue

        try:
            results = model.predict(img, verbose=False)

            for result in results:
                if result.boxes is None or len(result.boxes) == 0:
                    continue

                confiancas = result.boxes.conf.cpu().numpy()
                maior_confianca = float(confiancas.max())

                if maior_confianca > melhor_confianca:
                    melhor_confianca = maior_confianca
                    melhor_arquivo = nome_arquivo

        except Exception as e:
            print(f"Erro ao processar {nome_arquivo}: {e}")

    if melhor_confianca >= confianca_minima:
        return melhor_arquivo

    return None

if __name__ == '__main__':
    pasta = "./captcha"  
    response = solveCaptcha(pasta)

    if response:
        response = int(response.split('_')[1].replace('.jpg', ''))
        rotacao_correta = response % 360
        cliques = rotacao_correta // 30
        if response == 0:
            valor_api = 0
        else:
            valor_api = 330 - ((cliques - 1) * 30)
        print(valor_api)
        print(f"A imagem correta é: {response}")
    else:
        print("Nenhuma imagem atendeu aos critérios.")
