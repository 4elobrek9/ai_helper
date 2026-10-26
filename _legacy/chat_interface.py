import mistral_api
import json
import os

MEMORY_FILE = 'memory.json'
HARDMEMORY_FILE = 'hardmemory.json'

if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, 'w') as f:
        json.dump([], f)

if not os.path.exists(HARDMEMORY_FILE):
    with open(HARDMEMORY_FILE, 'w') as f:
        json.dump([], f)

def save_to_memory(message, role):
    with open(MEMORY_FILE, 'r') as f:
        memory = json.load(f)
    memory.append({'role': role, 'content': message})
    with open(MEMORY_FILE, 'w') as f:
        json.dump(memory, f)

def load_memory():
    with open(MEMORY_FILE, 'r') as f:
        return json.load(f)

def save_to_hardmemory(message):
    with open(HARDMEMORY_FILE, 'r') as f:
        hardmemory = json.load(f)
    hardmemory.append(message)
    with open(HARDMEMORY_FILE, 'w') as f:
        json.dump(hardmemory, f)

def summarize_hardmemory():
    with open(MEMORY_FILE, 'r') as f:
        memory = json.load(f)
    important_info = [msg for msg in memory if any(keyword in msg['content'].lower() for keyword in ['important', 'age', 'height', 'character', 'external parameters'])]


    with open(HARDMEMORY_FILE, 'w') as f:
        json.dump(important_info, f)

def main():
    print("Welcome to the Mistral Chat Interface!")
    print("Type 'exit' to quit the chat.")

    while True:
        user_input = input("You: ")
        try:
            if user_input.lower() == 'exit':
                summarize_hardmemory()
                break
        except KeyboardInterrupt:
            summarize_hardmemory()
            break




        save_to_memory(user_input, 'user')
        memory = load_memory()
        response = mistral_api.chat_with_mistral(user_input, memory)
        print(f"Mistral: {response['choices'][0]['message']['content']}")

        save_to_memory(response['choices'][0]['message']['content'], 'assistant')



if __name__ == '__main__':
    main()
