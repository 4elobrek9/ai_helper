import requests

API_KEY = '***'
API_URL = 'https://api.mistral.ai/v1/chat/completions'

def chat_with_mistral(prompt, memory=None):

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }
    messages = [{'role': 'user', 'content': prompt}]
    if memory:
        messages = memory + messages
    data = {
        'model': 'mistral-large-2411',
        'messages': messages,
        'max_tokens': 150,
        'temperature': 0.7
    }

    response = requests.post(API_URL, headers=headers, json=data)
    return response.json()

if __name__ == '__main__':
    prompt = "Hello, how are you?"
    response = chat_with_mistral(prompt)
    print(response)
