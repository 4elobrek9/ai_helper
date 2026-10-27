import requests
import logging

logger = logging.getLogger("lumi.weather")


def get_weather(city=None):
    """Get current weather from Open-Meteo for a named or IP-derived city."""
    try:
        city = city.strip() if isinstance(city, str) else ""
        if not city:
            location_response = requests.get(
                "https://ipinfo.io/json",
                timeout=(2, 3),
            )
            location_response.raise_for_status()
            location = location_response.json()
            if not isinstance(location, dict):
                raise RuntimeError("IP-сервис вернул некорректный ответ.")
            city_value = location.get("city")
            city = city_value.strip() if isinstance(city_value, str) else ""
            if not city:
                raise RuntimeError("IP-сервис не вернул город.")

        geocoding_response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": city,
                "count": 1,
                "language": "ru",
                "format": "json",
            },
            timeout=(2, 3),
        )
        geocoding_response.raise_for_status()
        geocoding_data = geocoding_response.json()
        if not isinstance(geocoding_data, dict):
            raise RuntimeError("Open-Meteo вернул некорректный ответ геокодирования.")
        locations = geocoding_data.get("results") or []
        if not locations:
            raise RuntimeError(f"Город «{city}» не найден в Open-Meteo.")

        result = locations[0]
        if not isinstance(result, dict):
            raise RuntimeError("Open-Meteo вернул некорректные координаты города.")
        latitude = result.get("latitude")
        longitude = result.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(
            longitude, (int, float)
        ):
            raise RuntimeError("Open-Meteo вернул некорректные координаты города.")
        weather_response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=(2, 4),
        )
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        current = (
            weather_data.get("current")
            if isinstance(weather_data, dict)
            else None
        )
        if (
            not isinstance(current, dict)
            or not isinstance(current.get("temperature_2m"), (int, float))
        ):
            raise RuntimeError("Open-Meteo не вернул текущую погоду.")

        weather_code = current.get("weather_code")
        conditions = {
            0: "ясно",
            1: "преимущественно ясно",
            2: "переменная облачность",
            3: "пасмурно",
            45: "туман",
            48: "изморозь",
            51: "лёгкая морось",
            53: "морось",
            55: "сильная морось",
            61: "небольшой дождь",
            63: "дождь",
            65: "сильный дождь",
            71: "небольшой снег",
            73: "снег",
            75: "сильный снег",
            80: "ливень",
            81: "сильный ливень",
            82: "очень сильный ливень",
            95: "гроза",
            96: "гроза с градом",
            99: "сильная гроза с градом",
        }
        return {
            "city": result.get("name") or city,
            "temp": current["temperature_2m"],
            "weather": conditions.get(weather_code, "погодные условия неизвестны"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
        }
    except RuntimeError as error:
        logger.error("Не удалось определить погоду: %s", error)
        raise
    except (requests.RequestException, KeyError, TypeError, ValueError) as error:
        logger.exception("Не удалось получить погоду")
        raise RuntimeError(f"Не удалось получить погоду: {error}") from error

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