from openai import OpenAI
import os
import dotenv

dotenv.load_dotenv()

openai_key = os.getenv("OPENAI_KEY")

client = OpenAI()


# MIght have to change this to reflect change in assistant id structure?
def send_gpt_prompt(email_content, assistant_id):
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
            for message in messages.data:
                if message.role == "assistant":
                    for content_block in message.content:
                        if content_block.type == "text":
                            gpt_response = content_block.text.value
                            print(gpt_response)
                            return gpt_response  # This only returns the "text" from the response, not the full response, ex. for debugging purposes
        else:
            print(run.status)

    except Exception as e:
        print(f"Error in GPT service: {e}")
        return "Error: Unable to get a response from GPT"
