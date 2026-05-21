import uuid
import requests
import json
import random
import io
import threading
import queue
import os
from flask import Flask, request, jsonify
from time import sleep
from PIL import Image
import numpy as np
import cv2
from ultralytics import YOLO
from concurrent.futures import ThreadPoolExecutor

try:
    from . import base64ToImage
except ImportError:
    import base64ToImage

# Configurações principais
MODEL_POOL_SIZE = 8  # Ajuste este número conforme a capacidade do seu hardware
CACHE_SIZE = 5    # Número de captchas para manter em cache

app = Flask(__name__)

HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'pt-BR,pt;q=0.9',
    'origin': 'https://app.axieinfinity.com',
    'referer': 'https://app.axieinfinity.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
}

APP_KEY = '5a0eb357-db13-4911-a810-c1914c17bc6f'

# Pool de modelos para processamento concorrente
class ModelPool:
    def __init__(self, model_path, pool_size):
        self.pool = queue.Queue()
        
        print(f"[⏳] Carregando pool de {pool_size} modelos YOLO...")
        for i in range(pool_size):
            model = YOLO(model_path)
            self.pool.put(model)
            print(f"[✓] Modelo {i+1}/{pool_size} carregado")
        
        print(f"[✓] Pool de modelos YOLO carregado com sucesso ({pool_size} instâncias)")
        self.pool_size = pool_size
    
    def get_model(self):
        return self.pool.get()
    
    def release_model(self, model):
        self.pool.put(model)

# Instanciação do pool de modelos
model_pool = ModelPool("./model/best.pt", MODEL_POOL_SIZE)

# Sistema de cache de captchas resolvidos
captcha_cache = queue.Queue(maxsize=CACHE_SIZE)
cache_lock = threading.Lock()

# Solver utilizando o pool de modelos
class RotatingCaptchaSolver:
    def solve(self, image_pil):
        model = model_pool.get_model()
        result = None
        
        try:
            image_pil = image_pil.crop(image_pil.getbbox())
            if image_pil.mode != 'RGB':
                image_pil = image_pil.convert('RGB')

            for angle in range(0, 360, 30):
                rotated = image_pil.rotate(-angle, expand=True).crop(image_pil.getbbox())
                image_cv = cv2.cvtColor(np.array(rotated), cv2.COLOR_RGB2BGR)

                try:
                    results = model.track(image_cv, persist=False, verbose=False)
                    if results and results[0].boxes:
                        print(f"[✓] Ângulo correto detectado: {angle}°")
                        result = angle
                        break
                except Exception as e:
                    print(f"[!] Erro ao processar rotação {angle}°: {e}")
        finally:
            model_pool.release_model(model)
            
        return result

solver = RotatingCaptchaSolver()

def load_proxies():
    if not os.path.exists('./proxies.txt'):
        return []

    with open('./proxies.txt') as file:
        return [line.strip() for line in file if line.strip()]


def build_proxy_config(proxy):
    return {
        "http": proxy,
        "https": proxy,
    }


def request_with_proxies(method, url, **kwargs):
    local_proxies = load_proxies()
    random.shuffle(local_proxies)

    if not local_proxies:
        print("[→] Nenhum proxy encontrado em proxies.txt. Fazendo requisição sem proxy.")
        response = requests.request(method, url, timeout=10, **kwargs)
        response.raise_for_status()
        return response

    last_error = None
    for proxy in local_proxies:
        proxy_cfg = build_proxy_config(proxy)
        try:
            response = requests.request(method, url, proxies=proxy_cfg, timeout=10, **kwargs)
            response.raise_for_status()
            return response
        except Exception as e:
            last_error = e
            print(f"[!] Proxy falhou {proxy}: {e}")
            sleep(1)
    
    raise Exception(f"Todas as proxies falharam. Último erro: {last_error}")


def getCaptcha(_proxy=None):
    response = request_with_proxies(
        "POST",
        'https://x.skymavis.com/captcha-srv/check',
        headers=HEADERS,
        json={'app_key': APP_KEY}
    )
    data = response.json()
    img = base64ToImage.convert(data['image'])
    return data['id'], img


def submit_cached_captcha(captcha_id, result, _proxy=None):
    submit_data = {
        'app_key': APP_KEY,
        'id': captcha_id,
        'result': result
    }

    response = request_with_proxies(
        "POST",
        'https://x.skymavis.com/captcha-srv/submit',
        headers=HEADERS,
        json=submit_data
    )

    print(f"[✓] Captcha do cache enviado: ID {captcha_id}, Resultado: {result}")
    return response.json()


def cache_worker(worker_id):
    print(f"[✓] Thread de cache #{worker_id} iniciada")
    while True:
        with cache_lock:
            cache_size = captcha_cache.qsize()
            if cache_size >= CACHE_SIZE:
                should_wait = True
            else:
                should_wait = False

        if should_wait:
            print(f"[✓] Thread #{worker_id}: Cache cheio ({cache_size}/{CACHE_SIZE}), aguardando...")
            sleep(5)
            continue

        try:
            captcha_id, img = getCaptcha(None)
            print(f"[→] Thread #{worker_id}: Processando Captcha ID: {captcha_id}")

            angle = solver.solve(img)

            if angle is not None:
                clicks = angle // 30
                result = 0 if angle == 0 else 330 - ((clicks - 1) * 30)

                captcha_cache.put({
                    'id': captcha_id,
                    'angle': angle,
                    'result': result,
                    'proxy': None
                })

                with cache_lock:
                    cache_size = captcha_cache.qsize()

                print(f"[+] Thread #{worker_id}: Adicionado ao cache ({cache_size}/{CACHE_SIZE}) - Ângulo {angle}°, Resultado: {result}")
            else:
                print(f"[x] Thread #{worker_id}: Nenhum ângulo retornou resultado.")

        except Exception as e:
            print(f"[!] Thread #{worker_id}: Erro geral: {e}")
            sleep(2)
        
        sleep(0.5)

def solve_with_proxies():
    request_thread_id = threading.get_ident()
    print(f"[→] Iniciando solução em thread ID: {request_thread_id}")

    try:
        captcha_id, img = getCaptcha(None)
        print(f"[→] Captcha ID: {captcha_id} (Thread: {request_thread_id})")

        angle = solver.solve(img)

        if angle is not None:
            clicks = angle // 30
            result = 0 if angle == 0 else 330 - ((clicks - 1) * 30)

            submit_data = {
                'app_key': APP_KEY,
                'id': captcha_id,
                'result': result
            }

            response = request_with_proxies(
                "POST",
                'https://x.skymavis.com/captcha-srv/submit',
                headers=HEADERS,
                json=submit_data
            )

            print(f"[✓] Thread {request_thread_id}: Captcha resolvido: Ângulo {angle}°, Resultado enviado: {result}")
            return response.json()

        else:
            print(f"[x] Thread {request_thread_id}: Nenhum ângulo retornou resultado.")
            raise Exception("Solver não conseguiu detectar o ângulo")

    except Exception as e:
        raise Exception(f"Thread {request_thread_id} falhou: {e}")


executor = ThreadPoolExecutor(max_workers=MODEL_POOL_SIZE * 2)
jobs = {}

@app.route('/submit', methods=['GET'])
def submit():
    job_id = str(uuid.uuid4())
    
    if not captcha_cache.empty():
        cached_captcha = captcha_cache.get()
        with cache_lock:
            cache_size = captcha_cache.qsize()
        print(f"[→] Usando captcha do cache ({cache_size}/{CACHE_SIZE} restantes)")
        future = executor.submit(
            submit_cached_captcha, 
            cached_captcha['id'], 
            cached_captcha['result'], 
            cached_captcha['proxy']
        )
    else:
        print(f"[!] Cache vazio, resolvendo captcha sob demanda")
        future = executor.submit(solve_with_proxies)
    
    jobs[job_id] = future
    return jsonify({'request_id': job_id})

@app.route('/result/<job_id>', methods=['GET'])
def result(job_id):
    future = jobs.get(job_id)
    if not future:
        return jsonify({'status': 'not_found'}), 404
    if not future.done():
        return jsonify({'status': 'processing'})
    try:
        data = future.result()
        jobs.pop(job_id, None)
        return jsonify({'status': 'ready', 'data': data})
    except Exception as e:
        jobs.pop(job_id, None)
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/cache/status', methods=['GET'])
def cache_status():
    with cache_lock:
        cache_size = captcha_cache.qsize()
    return jsonify({
        'cache_size': cache_size,
        'cache_max_size': CACHE_SIZE,
        'cache_percentage': (cache_size / CACHE_SIZE) * 100
    })

def start_cache_workers():
    cache_threads = []
    for i in range(MODEL_POOL_SIZE):
        thread = threading.Thread(target=cache_worker, args=(i+1,), daemon=True)
        thread.start()
        cache_threads.append(thread)
    
    print(f"[✓] {MODEL_POOL_SIZE} threads de cache iniciadas (tamanho máximo: {CACHE_SIZE} captchas)")
    return cache_threads


def run_server(host='0.0.0.0', port=6000, threaded=True):
    start_cache_workers()
    app.run(host=host, port=port, threaded=threaded)


if __name__ == '__main__':
    run_server()
