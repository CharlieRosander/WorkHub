from openai import OpenAI
import os
import dotenv
from typing_extensions import override
from openai import AssistantEventHandler

dotenv.load_dotenv()

openai_key = os.getenv("OPENAI_KEY")

client = OpenAI()
assistant_id = os.getenv("ASSISTANT_ID")


# def send_to_gpt(email_content):
# try:
#     thread = client.beta.threads.create()

#     message = client.beta.threads.messages.create(
#         thread_id=thread.id,
#         role="user",
#         content=email_content,
#     )

#             run = client.beta.threads.runs.create_and_poll(
#                 thread_id=thread.id, assistant_id=assistant_id
#             )

#             if run.status == "completed":
#                 messages = client.beta.threads.messages.list(thread_id=thread.id)
#                 # Assuming `messages` is the response you got
#                 for message in messages.data:
#                     if message.role == "assistant":
#                         # Här kommer vi åt texten som assistenten svarade med
#                         for content_block in message.content:
#                             if content_block.type == "text":
#                                 gpt_response = content_block.text.value
#                                 return gpt_response
#             else:
#                 print(run.status)

#         except Exception as e:
#             print(f"Error in GPT service: {e}")
#             return "Error: Unable to get a response from GPT"


# class EventHandler(AssistantEventHandler):
#     def __init__(self):
#         self._buffer = []

#     @override
#     def on_text_delta(self, delta, snapshot):
#         if delta.value:
#             self._buffer.append(delta.value)

#     def get_buffer(self):
#         return "".join(self._buffer)


def get_gpt_response(email_content):
    try:
        thread = client.beta.threads.create()

        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=email_content,
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant_id
        )

        if run.status == "completed":
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            # Assuming `messages` is the response you got
            for message in messages.data:
                if message.role == "assistant":
                    # Här kommer vi åt texten som assistenten svarade med
                    for content_block in message.content:
                        if content_block.type == "text":
                            gpt_response = content_block.text.value
                            print(gpt_response)
                            return gpt_response
        else:
            print(run.status)

    except Exception as e:
        print(f"Error in GPT service: {e}")
        return "Error: Unable to get a response from GPT"
