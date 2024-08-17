import os
import time
import json
import requests
import base64
from flask import Flask, render_template, request, jsonify
import random
import datetime
import openai
import pygame
from gtts import gTTS
from pydub import AudioSegment
import threading  # Добавляем импорт threading

# Установка API ключей
openai.api_key = "*****"
KANDINSKY_API_KEY = "*****"
KANDINSKY_SECRET_KEY = "*****"

app = Flask(__name__)

# Путь к папке с музыкой
MUSIC_PATH = "/static/Playlist - D_D - 169625 --- Jamendo - MP3"


# Инициализация микшера pygame
pygame.mixer.init()
pygame.mixer.set_num_channels(2)  # Устанавливаем 2 канала: один для музыки, другой для озвучки

current_playlist = []  # Переменная для хранения текущего плейлиста
current_track_index = 0  # Индекс текущего трека

# Функция для переключения музыки в зависимости от события
def switch_music(event_type):
    global current_playlist, current_track_index
    music_map = {
        "battle": [
            "battle_theme_1.mp3",
            "battle_theme_2.mp3",
        ],
        "explore": [
            "explore_theme_1.mp3",
            "explore_theme_2.mp3",
        ],
        "dialogue": [
            "dialogue_theme_1.mp3",
            "dialogue_theme_2.mp3",
        ],
        "event": [
            "event_theme_1.mp3",
            "event_theme_2.mp3",
        ],
        "default": ["default_theme.mp3"]
    }

    if event_type in music_map:
        current_playlist = [os.path.join(MUSIC_PATH, track) for track in music_map[event_type]]
        current_track_index = 0
        play_music(current_playlist[current_track_index])
    else:
        music_file = os.path.join(MUSIC_PATH, "default_theme.mp3")
        play_music(music_file)

# Функция для воспроизведения музыки
def play_music(file_path, volume=0.5):
    try:
        if not os.path.exists(file_path):
            print(f"Music file not found: {file_path}")
            return

        pygame.mixer.music.load(file_path)
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play(-1)  # Зацикливаем трек
        print(f"Playing music: {file_path}")

        # Устанавливаем обработчик завершения трека
        pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)
    except pygame.error as e:
        print(f"Failed to play music: {e}")

# Функция для обработки завершения трека и перехода к следующему
def handle_music_end():
    global current_track_index, current_playlist

    current_track_index += 1
    if current_track_index >= len(current_playlist):
        current_track_index = 0  # Зацикливаем плейлист

    play_music(current_playlist[current_track_index])

# Главная функция для обработки событий Pygame
def main_loop():
    while True:
        for event in pygame.event.get():
            if event.type == pygame.USEREVENT + 1:  # Если трек закончился
                handle_music_end()

# Функция для озвучки текста и сохранения его в файл
def voice_response(text_response):
    try:
        tts = gTTS(text=text_response, lang='ru')
        file_path = "static/output.mp3"
        tts.save(file_path)

        # Ускоряем аудио
        sped_up_file_path = "static/output_fast.mp3"
        speed_up_audio(file_path, sped_up_file_path, speed=1.2)

        voice_channel = pygame.mixer.Channel(1)
        voice_channel.set_volume(1.0)
        sound = pygame.mixer.Sound(sped_up_file_path)
        voice_channel.play(sound)

        while voice_channel.get_busy():
            pass  # Ждем, пока озвучка не завершится

        os.remove(sped_up_file_path)  # Удаляем ускоренный файл после проигрывания
    except Exception as e:
        print(f"Failed to generate voice response: {e}")

# Функция для ускорения аудио
def speed_up_audio(file_path, output_path, speed=2):
    try:
        sound = AudioSegment.from_file(file_path)
        sped_up_sound = sound.speedup(playback_speed=speed)
        sped_up_sound.export(output_path, format="mp3")
    except Exception as e:
        print(f"Failed to speed up audio: {e}")

def roll_dice(sides=20):
    return random.randint(1, sides)

# Функция для обработки выбора действия
@app.route('/choose_action', methods=['POST'])
def choose_action():
    data = request.json
    action = data.get('action')
    character_data = data.get('character_data')

    # Добавляем историю игры для сохранения контекста
    game_history = data.get('game_history', "")

    # Бросаем кубик для определения исхода действия
    dice_result = roll_dice()

    # Формируем новый запрос к GPT с учетом выбранного действия и результата кубика
    gpt_prompt = (
        f"{game_history}\n\nВы выбрали действие: {action}. Выпал результат кубика: {dice_result}. "
        "Описывай, что происходит дальше, учитывая этот результат. Подготовь 4 новых варианта действий, каждый из которых включает "
        "одно из следующих ключевых слов: открыть, исследовать, войти, попробовать, напасть, убежать."
    )

    gpt_response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты ведущий в игре Dungeons & Dragons."},
            {"role": "user", "content": gpt_prompt}
        ]
    )

    new_scene_description = gpt_response['choices'][0]['message']['content'].strip()

    # Генерация новых действий на основе текста
    new_actions = extract_actions_from_gpt(new_scene_description)

    # Генерация изображения для новой сцены
    image_prompt = trim_prompt(new_scene_description, 80)
    new_image_url = generate_kandinsky_image(image_prompt)

    # Обновляем историю игры
    updated_game_history = f"{game_history}\n\n{new_scene_description}"

    # Возвращаем новую сцену и изображение, а также новые действия и обновленную историю
    return jsonify({
        'image_url': new_image_url,
        'scene_text': new_scene_description,
        'actions': new_actions,
        'game_history': updated_game_history,
        'dice_result': dice_result  # Можно также вернуть результат кубика
    })

def extract_actions_from_gpt(gpt_response):
    actions = []
    lines = gpt_response.split('\n')
    for line in lines:
        if any(keyword in line.lower() for keyword in ["открыть", "исследовать", "войти", "попробовать", "напасть", "убежать"]):
            actions.append(line.strip())
    return actions[:4]  # Возвращаем только 4 действия

# Добавляем маршрут для озвучки текста
@app.route('/speak', methods=['POST'])
def speak():
    text = request.json.get('text', '')
    voice_response(text)
    return jsonify({'status': 'ok'})

# Функция для обрезки текста до 100 слов
def trim_prompt(prompt, max_words=100):
    words = prompt.split()
    if len(words) > max_words:
        return ' '.join(words[:max_words])
    return prompt

# Маршрут для установки громкости музыки
@app.route('/set_volume', methods=['POST'])
def set_volume():
    data = request.json
    volume = data.get('volume', 0.5)
    pygame.mixer.music.set_volume(volume)
    return jsonify({'status': 'ok'})

# Маршрут для установки громкости озвучки
@app.route('/set_voice_volume', methods=['POST'])
def set_voice_volume():
    data = request.json
    volume = data.get('volume', 0.5)
    voice_channel = pygame.mixer.Channel(1)
    voice_channel.set_volume(volume)
    return jsonify({'status': 'ok'})

# Маршрут для включения/выключения музыки
@app.route('/toggle_music', methods=['POST'])
def toggle_music():
    data = request.json
    play = data.get('play', True)
    if play:
        pygame.mixer.music.unpause()
    else:
        pygame.mixer.music.pause()
    return jsonify({'status': 'ok'})

# Маршрут для включения/выключения озвучки
@app.route('/toggle_voice', methods=['POST'])
def toggle_voice():
    data = request.json
    enable = data.get('enable', True)
    voice_channel = pygame.mixer.Channel(1)
    if enable:
        voice_channel.unpause()
    else:
        voice_channel.pause()
    return jsonify({'status': 'ok'})

# Главная страница
@app.route('/')
def index():
    switch_music("default")
    return render_template('index.html')

# Обработка начала приключения
@app.route('/start', methods=['POST'])
def start():
    try:
        # Запрос к GPT для получения сюжета и вариантов действий
        gpt_prompt = gpt_prompt = (
    "Ты ведущий в игре Dungeons & Dragons. Игрок оказался в захватывающей ситуации. "
    "Описывай атмосферу и погружай игрока в мир приключений, используя живописные детали. "
    "В конце сцены предложи игроку четыре действия, каждый из которых включает одно из следующих ключевых слов: "
    "открыть, исследовать, войти, попробовать, напасть или убежать. "
    "Варианты действий должны быть логически связаны с текущей сценой и не должны быть нумерованы. "
    "Игрок может выбрать любое из них, и история продолжится на основе его выбора."
)

        gpt_response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты ведущий в игре Dungeons & Dragons."},
                {"role": "user", "content": gpt_prompt}
            ]
        )

        scene_description = gpt_response['choices'][0]['message']['content'].strip()

        # Генерация действий на основе ответа GPT
        actions = extract_actions_from_gpt(scene_description)

        # Ограничение длины промта до 80 слов
        image_prompt = trim_prompt(scene_description, 80)

        # Генерация изображения с помощью Kandinsky на основе описания сцены
        image_url = generate_kandinsky_image(image_prompt)

        # Возвращаем результат в JavaScript для обновления фона, текста и создания кнопок действий
        if image_url:
            return jsonify({'image_url': image_url, 'scene_text': scene_description, 'actions': actions})
        else:
            return jsonify({'error': 'Failed to generate image'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_model_id():
    try:
        url = "https://api-key.fusionbrain.ai/key/api/v1/models"
        headers = {
            'X-Key': f'Key {KANDINSKY_API_KEY}',
            'X-Secret': f'Secret {KANDINSKY_SECRET_KEY}',
        }
        response = requests.get(url, headers=headers)
        response_json = response.json()

        if response.status_code == 200 and len(response_json) > 0:
            model_id = response_json[0]['id']  # Используем ID первой модели в списке
            print(f"Model ID retrieved: {model_id}")
            return model_id
        else:
            print(f"Failed to retrieve models: {response.status_code} {response.text}")
            return None

    except Exception as e:
        print(f"Exception during model retrieval: {e}")
        return None

# Функция для генерации изображения с помощью Kandinsky
def generate_kandinsky_image(prompt):
    model_id = get_model_id()  # Получаем ID модели
    if not model_id:
        print("No model ID found, aborting image generation.")
        return None

    try:
        url = "https://api-key.fusionbrain.ai/key/api/v1/text2image/run"
        headers = {
            'X-Key': f'Key {KANDINSKY_API_KEY}',
            'X-Secret': f'Secret {KANDINSKY_SECRET_KEY}',
        }
        params = {
            "type": "GENERATE",
            "numImages": 1,
            "width": 1024,
            "height": 1024,
            "generateParams": {
                "query": prompt
            }
        }

        data = {
            'model_id': (None, str(model_id)),  # Приведение ID модели к строке
            'params': (None, json.dumps(params), 'application/json')
        }

        response = requests.post(url, headers=headers, files=data)
        response_json = response.json()

        if response.status_code == 201 and response_json['status'] == 'INITIAL':
            uuid = response_json['uuid']
            print(f"Image generation started with UUID: {uuid}")
            return check_kandinsky_status(uuid)
        else:
            print(f"Failed to generate image: {response.status_code} {response.text}")
            return None

    except Exception as e:
        print(f"Exception during image generation: {e}")
        return None

def check_kandinsky_status(uuid):
    try:
        url = f"https://api-key.fusionbrain.ai/key/api/v1/text2image/status/{uuid}"
        headers = {
            'X-Key': f'Key {KANDINSKY_API_KEY}',
            'X-Secret': f'Secret {KANDINSKY_SECRET_KEY}',
        }

        for _ in range(10):  # Попробуем несколько раз запросить статус генерации
            response = requests.get(url, headers=headers)
            response_json = response.json()

            if response_json['status'] == 'DONE':
                image_data = response_json['images'][0]
                image_path = os.path.join("static/img", f"kandinsky_{uuid}.png")
                with open(image_path, "wb") as image_file:
                    image_file.write(base64.b64decode(image_data))
                return f"/static/img/kandinsky_{uuid}.png"

            elif response_json['status'] == 'FAIL':
                print("Image generation failed")
                return None

            print("Waiting for image generation to complete...")
            time.sleep(5)  # Подождем 5 секунд перед повторным запросом

        print("Timeout waiting for image generation")
        return None

    except Exception as e:
        print(f"Exception during image status check: {e}")
        return None


if __name__ == '__main__':
    # Запуск основного цикла Pygame в отдельном потоке
    pygame_thread = threading.Thread(target=main_loop)
    pygame_thread.start()

    # Запуск Flask-приложения в главном потоке
    app.run(debug=True)
