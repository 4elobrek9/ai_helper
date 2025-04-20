import requests
from bs4 import BeautifulSoup
import socket
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

# import requests
# from bs4 import BeautifulSoup
# import socket

# def get_weather_for_mytishchi():
# #     """Получаем погоду именно для Мытищ (Подмосковье)"""
# #     try:
# #         # Прямая ссылка на Мытищи с уточнением региона
# #         url = "https://yandex.ru/pogoda/10463"
# #         headers = {
# #             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
# #         }
        
# #         print(f"Запрашиваем погоду для Мытищ по адресу: {url}")
# #         response = requests.get(url, headers=headers)
        
# #         if response.status_code != 200:
# #             print(f"Ошибка запроса: {response.status_code}")
# #             return None

# #         soup = BeautifulSoup(response.text, 'html.parser')

# #         # Новый селектор для температуры (актуальный на 2023 год)
# #         temp = soup.find('span', class_='temp__value')
# #         if not temp:
# #             # Альтернативный селектор
# #             temp = soup.find('div', class_='fact__temp').find('span', class_='temp__value')
        
# #         if not temp:
# #             print("Не найдена температура на странице")
# #             return None
            
# #         temp_value = temp.text.strip()
# #         print(f"Текущая температура: {temp_value}")

# #         # Поиск описания погоды
# #         weather = soup.find('div', class_='link__condition')
# #         if not weather:
# #             weather = soup.find('div', class_='fact__condition')
        
# #         if not weather:
# #             print("Не найдено описание погоды")
# #             return None
            
# #         weather_text = weather.text.strip()
# #         print(f"Состояние погоды: {weather_text}")

# #         return {
# #             'city': 'Мытищи',
# #             'temp': temp_value,
# #             'weather': weather_text
# #         }
        
# #     except Exception as e:
# #         print(f"Ошибка при получении погоды: {str(e)}")
# #         return None

# # # Пример использования
# if __name__ == "__main__":
#     print("=== Получаем погоду для Мытищ ===")
#     weather = get_weather_for_mytishchi()
#     if weather:
#         print("\nТекущая погода в Мытищах:")
#         print(f"Температура: {weather['temp']}°C")
#         print(f"Состояние: {weather['weather']}")
#     else:
#         print("Не удалось получить данные о погоде")