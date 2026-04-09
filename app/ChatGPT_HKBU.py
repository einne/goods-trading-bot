import requests
import configparser
import os
import time

# A simple client for the ChatGPT REST API
class ChatGPT:
    def __init__(self, config):
        # Prefer environment variables for production secrets.
        api_key = os.getenv("CHATGPT_API_KEY") or config['CHATGPT']['API_KEY']
        base_url = os.getenv("CHATGPT_BASE_URL") or config['CHATGPT']['BASE_URL']
        model = os.getenv("CHATGPT_MODEL") or config['CHATGPT']['MODEL']
        api_ver = os.getenv("CHATGPT_API_VER") or config['CHATGPT']['API_VER']
        self.model = model

        # Construct the full REST endpoint URL for chat completions
        self.url = f'{base_url}/deployments/{model}/chat/completions?api-version={api_ver}'

        # Set HTTP headers required for authentication and JSON payload
        self.headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "api-key": api_key,
        }

        # Define the system prompt to guide the assistant’s behavior
        self.system_message = (
            'You are a helper! Your users are university students. '
            'Your replies should be conversational, informative, use simple words, and be straightforward.'
        )

    def submit_with_meta(self, user_message: str):
        
        # Build the conversation history: system + user message
        messages = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": user_message},
        ]

        # Prepare the request payload with generation parameters
        payload = {
            "messages": messages,
            "temperature": 1,     # randomness of output (higher = more creative)
            "max_tokens": 150,    # maximum length of the reply
            "top_p": 1,           # nucleus sampling parameter
            "stream": False       # disable streaming, wait for full reply
        }    

        # Send the request to the ChatGPT REST API
        start = time.perf_counter()
        response = requests.post(self.url, json=payload, headers=self.headers)
        latency_ms = int((time.perf_counter() - start) * 1000)

        # If successful, return the assistant’s reply text
        if response.status_code == 200:
            body = response.json()
            usage = body.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0) or 0
            completion_tokens = usage.get("completion_tokens", 0) or 0
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
            return {
                "text": body['choices'][0]['message']['content'],
                "latency_ms": latency_ms,
                "model": self.model,
                "usage": {
                    "prompt_tokens": int(prompt_tokens),
                    "completion_tokens": int(completion_tokens),
                    "total_tokens": int(total_tokens),
                },
            }
        else:
            # Otherwise return error details
            return {
                "text": "Error: " + response.text,
                "latency_ms": latency_ms,
                "model": self.model,
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }

    def submit(self, user_message: str):
        return self.submit_with_meta(user_message)["text"]
    

if __name__ == '__main__':
    # Load configuration from ini file
    config = configparser.ConfigParser()
    config.read('config.ini')    

    # Initialize ChatGPT client
    chatGPT = ChatGPT(config)

    # Simple REPL loop: read user input, send to ChatGPT, print reply
    while True:
        print('Input your query: ', end='')
        response = chatGPT.submit(input())

        print(response)
