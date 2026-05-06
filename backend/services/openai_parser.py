import json
import logging
import os
import requests

SYSTEM_PROMPT = 'You are a task extraction assistant. Extract tasks from the user message and return ONLY a valid JSON array. No markdown, no explanation, no preamble. Format: [{"name":"string","duration_minutes":integer,"location_name":"string or null"}]. If duration is not mentioned, estimate a reasonable default.'

def parse_tasks(text: str) -> list[dict]:
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return [{'name': text.strip()[:80] or 'New task', 'duration_minutes': 60, 'location_name': None}]
    try:
        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': 'gpt-4o', 'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': text}], 'temperature': 0},
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        data = json.loads(content)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logging.exception('OpenAI parser fallback used: %s', exc)
        return [{'name': text.strip()[:80] or 'New task', 'duration_minutes': 60, 'location_name': None}]
