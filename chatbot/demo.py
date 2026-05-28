from google import genai
from google.genai import types
from dotenv import load_dotenv
from pathlib import Path
import os
import time

load_dotenv()

# ⚙️ LLM Configuration ——————————————————————————————————————————

models = [
    ["gemini-3.1-flash-lite-preview", "gemini-3-flash-preview", "gemini-3.1-pro-preview"],  # Gemini 3.1
    ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]                         # Gemini 2.5
    ]

past_memory = []
if Path("chatbot/memory.txt").exists():
    saved_text = Path("chatbot/memory.txt").read_text(encoding="utf-8")
    past_memory = [
        types.Content(
            role="user", 
            parts=[types.Part.from_text(text=f"[SYSTEM RESTORE: Here is the summary of our past interactions:]\n\n{saved_text}")] 
        ),
        types.Content(
            role="model", 
            parts=[types.Part.from_text(text=f"Understood. I have reviewed my memories and am ready to continue as Bruno Bucciarati.")]
        )
    ]

persona = Path("chatbot/prompt/persona.txt").read_text(encoding="utf-8")
persona_config = types.GenerateContentConfig(
    system_instruction = persona,
    temperature        = 0.4,
)

summarizer = Path("chatbot/prompt/summarizer.txt").read_text(encoding="utf-8")
summarizer_config = types.GenerateContentConfig(
    system_instruction = summarizer,
    temperature        = 0.0,
)

client = genai.Client()
chat = client.chats.create(
    model   = "gemini-2.5-flash",
    config  = persona_config,
    history = past_memory,
)

def generate_response(message, config_type):
    start = time.time()
    response = chat.send_message(message, config = config_type)
    stop  = time.time()
    duration = round(stop - start)
    return response, duration
# ———————————————————————————————————————————————————————————————

os.system("cls")

# 📑 Conversation ———————————————————————————————————————————————

while True:
    message = input("You: ")

    try:
        # User hits the enter key for plot continuation
        if message.strip() == "": message = "[System: The user passes their turn. Advance the current scene, continue your dialogue, or describe what happens next.]"

        # User wants to save the conversation
        if message == "COMMIT":
            print("\n[System: Swapping persona to Summarizer AI...]")
            message = "Summarize our history."
            config  = summarizer_config
            response, duration = generate_response(message, summarizer_config)
            print(f"\n--- MEMORY SUMMARY ---\n{response.text}\n(Generated in {duration} seconds)\n----------------------\n")
            command = input("Overwrite existing file? (Y/N): ")
            if command == 'Y':
                Path("chatbot/memory.txt").write_text(response.text, encoding="utf-8")
                print("\nmemory.txt was successfully updated.")
            print()
            continue
        
        # General Conversation
        response, duration = generate_response(message, persona_config)
        print(f"Gemini: {response.text}\n(Generated in {duration} seconds)", end="\n\n")

    except Exception as e: print(f"Error: {e}", end="\n\n")

# ———————————————————————————————————————————————————————————————