import json
import os
import asyncio

conversation_history = {}

async def load_conversation_history():
    global conversation_history
    if os.path.exists('resources/jsons/conversation_history.json'):
        conversation_history = await asyncio.to_thread(lambda: json.load(open('resources/jsons/conversation_history.json', 'r')))
        print(f"Loaded conversation history for {len(conversation_history)} users.")

async def save_conversation_history(conversation_history):
    await asyncio.to_thread(lambda: json.dump(conversation_history, open('resources/jsons/conversation_history.json', 'w')))
    print("Conversation saved")
