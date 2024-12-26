import os
import openai
from openai.types.beta import Assistant, Thread
import json


class Ada:
    client: openai.OpenAI
    assistant: Assistant
    thread: Thread

    def __init__(self):
        self.client = openai.OpenAI()
        self.assistant = self.client.beta.assistants.retrieve(
            os.environ.get("ASSISTANT_ID"))
        with open('settings.json', 'w+') as file:
            try:
                settings = json.load(file)
                if settings.thread_id:
                    self.thread = self.client.beta.threads.retrieve(
                        settings.thread_id)
                else:
                    self.thread = self.client.beta.threads.create()
                    settings.thread_id = self.thread.id
                    json.dump(settings, file)
            except Exception:
                self.thread = self.client.beta.threads.create()
                settings = {"thread_id": self.thread.id}
                json.dump(settings, file)
