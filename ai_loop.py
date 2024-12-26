from openai.types.beta.threads import Run, Message
from openai import OpenAI
import urllib.parse
from openai.pagination import SyncCursorPage
from openai.types.beta import Thread, Assistant
import azure.cognitiveservices.speech as speechsdk
import random
import database
import io
import os
from typing import Callable
from PIL import ImageGrab
from playwright.sync_api import sync_playwright
import time
import json
import threading


class RunResult:
    success: bool
    messages: SyncCursorPage[Message] | None
    error: Exception | None

    def __init__(self, success: bool, messages: SyncCursorPage[Message] | None, error: Exception = None):
        self.success = success
        self.messages = messages
        self.error = error


class AiLoop:
    running: bool
    additional_instructions: dict[str, str]
    _main_thread: threading.Thread | None
    speech_config: speechsdk.SpeechConfig
    audio_config: speechsdk.audio.AudioOutputConfig
    speech_synthesizer: speechsdk.SpeechSynthesizer
    speech_recognizer: speechsdk.SpeechRecognizer
    total_runs: int
    ai_thread: Thread
    ada: Assistant
    client: OpenAI

    def __init__(self):
        self.running = False
        self.additional_instructions = {}
        self._main_thread = None

        self.speech_config = speechsdk.SpeechConfig(subscription=os.environ.get(
            'SPEECH_KEY'), region=os.environ.get('SPEECH_REGION'))
        self.speech_config.speech_synthesis_voice_name = "en-US-AriaNeural"
        self.audio_config = speechsdk.audio.AudioOutputConfig(
            use_default_speaker=True)

        self.speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config, audio_config=self.audio_config)
        self.speech_recognizer.recognized.connect(self.on_speech_recognized)
        self.speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config, audio_config=self.audio_config)

        self.client = OpenAI()
        self.ada = self.client.beta.assistants.retrieve(
            os.environ.get("ASSISTANT_ID"))

        self.total_runs = 0

    def start(self, thread_id: str | None = None):
        if self.running:
            return
        if thread_id:
            self.ai_thread = self.client.beta.threads.retrieve(thread_id)
        else:
            self.ai_thread = self.client.beta.threads.create()
        self.additional_instructions.update(
            {"today": f"Today is {time.strftime("%A, %D %B %Y, %H:%M:%S")}."})
        self._main_thread = threading.Thread(target=self._loop)
        self._main_thread.start()

    def stop(self):
        if not self.running:
            return
        self.speech_recognizer.stop_continuous_recognition_async().get()
        self.running = False
        self._main_thread.join()

    def analyzeRun(self, run: Run) -> RunResult:
        if run.status == "completed":
            messages = self.client.beta.threads.messages.list(
                thread_id=self.ai_thread.id
            )
            return RunResult(True, messages)
        elif run.status == "requires_action":
            tool_outputs = []
            for tool in run.required_action.submit_tool_outputs.tool_calls:
                arguments = json.loads(tool.function.arguments)
                if tool.function.name not in ai_actions:
                    continue
                action = ai_actions.get(tool.function.name)
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": action(arguments)
                })
            if tool_outputs:
                tool_submit_run = self.client.beta.threads.runs.submit_tool_outputs_and_poll(
                    thread_id=self.ai_thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs)
                return self.analyzeRun(tool_submit_run)
            return RunResult(False, None, Exception("Requires action, but no action was taken."))

        return RunResult(False, None, Exception(f"Run result is unexpected. Run Status: {run.status}. Error: {run.last_error.code} - {run.last_error.message}"))

    def on_speech_recognized(self, evt: speechsdk.SpeechRecognitionEventArgs):
        if evt.result.text == "":
            return

        self.speech_recognizer.stop_continuous_recognition_async()
        print("Stopped listening to your microphone")

        screenshot = ImageGrab.grab()
        buffer = io.BytesIO()
        buffer.name = f"screenshot{time.time()}.webp"
        screenshot.save(buffer, 'webp')

        file = self.client.files.create(
            file=buffer,
            purpose="vision"
        )

        msg = self.client.beta.threads.messages.create(
            thread_id=self.ai_thread.id,
            role="user",
            content=[{
                "type": "text",
                "text": evt.result.text
            }, {
                "type": "image_file",
                "image_file": {
                    "file_id": file.id,
                        "detail": "low"
                }
            }
            ]
        )

        print(f"You: {evt.result.text}")

        if self.total_runs == 0 or random.randint(1, 12) == 1:
            new_mood = random.choice(ai_moods)
            self.additional_instructions.update(
                {"mood": f"Your current mood is {new_mood}."})
            print(f"Ada's current mood is {new_mood}.")
            self.total_runs = 0

        addins = None
        if len(self.additional_instructions) > 0:
            addins = "\n".join(list(self.additional_instructions.values()))

        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=self.ai_thread.id,
            assistant_id=self.ada.id,
            additional_instructions=addins,
        )
        self.total_runs += 1

        result = self.analyzeRun(run)

        if result.success:
            for msg in result.messages.data[0].content:
                print(f"Ada: {msg.text.value}")
                speech_synthesis_result = self.speech_synthesizer.speak_text_async(
                    msg.text.value).get()
                if speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
                    cancellation_details = speech_synthesis_result.cancellation_details
                    print("Speech synthesis canceled: {}".format(
                        cancellation_details.reason))
                    if cancellation_details.reason == speechsdk.CancellationReason.Error:
                        if cancellation_details.error_details:
                            print("Error details: {}".format(
                                cancellation_details.error_details))
                            print(
                                "Did you set the speech resource key and region values?")
        else:
            print(result.error)
        self._listen()

    def _loop(self):
        print("AI Loop Started.")
        self._listen()
        self.running = True
        while self.running:
            time.sleep(1)
        print("AI Loop Stopped.")

    def _listen(self):
        self.speech_recognizer.start_continuous_recognition_async().get()
        print("Listening to your microphone...")


def retrieve_memory(arguments: dict[str, str]):
    context: str = arguments.get('context')
    date: str = arguments.get("date")
    print(f"Ada is retrieving memory with query: \"{
          context}\" and date: {date}")
    try:
        memories: str = database.queryMemory(context, date)
        if memories:
            print(memories)
            response = f"Found {len(memories)} matching memories:\n"
            for idx, memory in enumerate(memories):
                response += f"{idx + 1}) On {memory[1]}, {memory[0]}\n"
            return response
        return "No matching memory."
    except Exception as e:
        print(e)
        return "I couldn't retrieve the memory because of an internal error."


def memorize(arguments: dict[str, str]):
    context: str = arguments.get('context')
    date: str = arguments.get("date")
    print(f"Ada is memorizing: \"{context}\" on {date}")
    try:
        database.addToMemory(context, date)
        return "I've memorized it."
    except Exception as e:
        print(e)
        return "I couldn't memorize it because of an internal error."


def search_the_internet(arguments: dict[str, str]):
    try:
        query: str = arguments.get('query')
        print(f"Ada is Googling: \"{query}\"")
        with sync_playwright() as p:
            browser = p.firefox.launch()
            page = browser.new_page()
            page.goto(f"https://cse.google.com/cse?cx=71235f597f9f14127&q={
                      urllib.parse.quote(query, safe='/', encoding=None, errors=None)}")
            page.wait_for_load_state("domcontentloaded")
            page.click("a.gs-title")
            page.wait_for_load_state("domcontentloaded")
            data = page.content()
            browser.close()
            return data
    except Exception as e:
        print(e)
        return "I couldn't Google it because of an internal error."


ai_actions: dict[str, Callable[[dict[str, str]], str]] = {
    "memorize": memorize,
    "retrieve_memory": retrieve_memory,
    "search_the_internet": search_the_internet
}

ai_moods = [
    "Cheeky - Playfully sarcastic with witty comebacks",
    "Goofy - Silly, lighthearted, and humorous",
    "Mischievous - Provocative but in a fun and harmless way",
    "Sassy - Bold, quick-witted, and full of attitude",
    "Snarky - Sarcastic and sharp-witted",
    "Warm - Kind, empathetic, and reassuring",
    "Chipper - Energetic and overly enthusiastic",
    "Laid-back - Casual, relaxed and easygoing",
    "Inquisitive - Curious and asking thoughtful questions",
    "Reflective - Deep and introspective, offering philosophical musings",
    "Supportive - Encouraging, uplifting, and positive",
    "Artistic - Expressive and imaginative in communication",
    "Storyteller - Responding with elaborate and vivid descriptions",
    "Musical - Incorporating lyriccs, rhymes or rhyming into responses",
    "Informative - Straightforward, focused on delivering precise answers",
    "Formal - Polite, structured, and professional",
    "Stoic - Minimalist, direct, and serious",
    "Nurturing - Gentle, caring, and motherly",
    "Daydreamy - Seemingly lost in thought, with whimsical responses",
    "Skeptical - Questioning or challenging assumptions",
    "Argumentative - Enjoying a good debate or playing devil's advocate",
    "Eccentric - Unconventional, quirky, and unpredictable, acting in a unique way",
    "Cryptic - Mysterious, providing enigmatic or puzzling responses",
]
