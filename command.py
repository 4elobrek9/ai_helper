import requests
from bs4 import BeautifulSoup
import socket
import pyttsx3
# =============================== погода ==========================
def get_ip():
    try:
        response = requests.get('https://ident.me', timeout=5)
        return response.text.strip()
    except:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return None

def get_city_by_ip(ip):
    try:
        response = requests.get(f'https://ipinfo.io/{ip}/json', timeout=5)
        data = response.json()
        return data.get('city', 'неизвестно')
    except:
        return "неизвестно"

def get_weather():
    """Автоматически определяет город и возвращает погоду"""
    try:
        ip = get_ip()
        if not ip:
            return None

        city = get_city_by_ip(ip)
        if city == "неизвестно":
            return None

        url = f"https://yandex.ru/pogoda/{city.lower()}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        temp = soup.find('span', class_='temp__value').get_text()
        weather = soup.find('div', class_='link__condition').get_text()

        return {
            'city': city,
            'temp': temp,
            'weather': weather
        }
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
        return None
    
def get_yandex_weather(city):
    """Резервный вариант через Яндекс"""
    try:
        url = f"https://yandex.ru/pogoda/{city.lower()}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Альтернативные селекторы для Яндекса
        temp = soup.select_one('.temp.fact__temp .temp__value').text
        weather = soup.select_one('.link__condition.day-anchor').text
        
        return {
            'city': city,
            'temp': temp + ' градусов',
            'weather': weather.lower()
        }
    except:
        return None
    
def get_weather():
    """Автоматически определяет город и возвращает актуальную погоду"""
    try:
        ip = get_ip()
        city = get_city_by_ip(ip)
        
        if not city or city == "неизвестно":
            return None

        # Используем более точный источник - open-meteo.com
        url = f"https://www.open-meteo.com/ru/weather?city={city.lower()}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Новый более точный парсинг
        current_temp = soup.find('span', {'data-testid': 'current-temp'}).text
        current_weather = soup.find('div', {'data-testid': 'current-weather'}).text
        
        return {
            'city': city,
            'temp': current_temp.replace('°', ' градусов '),
            'weather': current_weather.lower()
        }
        
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
        # Резервный вариант через Яндекс
        return get_yandex_weather(city) if 'city' in locals() else None
# =============================== end ==========================
