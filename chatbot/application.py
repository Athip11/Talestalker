import gradio as gr
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pathlib import Path
import time, os

load_dotenv()

client = genai.Client()
persona = Path("chatbot/persona.txt").read_text(encoding="utf-8")
chat = client.chats.create(
    model  = "gemini-3.1-flash-lite-preview",
    config = types.GenerateContentConfig(
        system_instruction = persona,
        temperature        = 0.4,
    ),
)

os.system("cls")

def chat_with_bruno(message, history):
    # Gradio sends the user's input as 'message'. 
    # We pass it to the chat object just like your input() function did.
    start = time.time()
    response = chat.send_message(message)
    stop = time.time()
    duration = round(stop - start)
    
    return f"{response.text}\n\n(Generated in {duration} seconds)"

demo = gr.ChatInterface(
    fn=chat_with_bruno,
    title="Secure Channel: Bucciarati",
    description="Do not waste his time.",
    textbox=gr.Textbox(placeholder="State your business..."),
)

if __name__ == "__main__":
    demo.launch()