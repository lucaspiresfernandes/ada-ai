from dotenv import load_dotenv
import logging
from pynput import keyboard
from ai_loop import AiLoop
import json

logging.basicConfig(
    format="[%(asctime)s] [%(filename)s:%(lineno)d] %(message)s", level=logging.INFO)
load_dotenv()

keys_pressed = set()
loop = AiLoop()


def on_key_press(key):
    if key not in keys_pressed:
        keys_pressed.add(key)
        if key == keyboard.Key.f4:
            loop.stop()
            print("Exiting...")
            return False


def on_key_release(key):
    if key in keys_pressed:
        keys_pressed.remove(key)


def main():
    settings = {"thread_id": None}
    with open("settings.json", "a+") as file:
        try:
            settings = json.load(file)
        except json.JSONDecodeError:
            pass

    loop.start(settings.get("thread_id"))

    if loop.ai_thread.id != settings.get("thread_id"):
        with open("settings.json", "w") as file:
            json.dump({"thread_id": loop.ai_thread.id}, file)

    with keyboard.Listener(
            on_press=on_key_press,
            on_release=on_key_release) as listener:
        listener.join()


main()
