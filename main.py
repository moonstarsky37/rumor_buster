from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, PostbackEvent, MemberJoinedEvent
import requests
import os
import traceback
from openai import OpenAI
import configparser

# 配置读取
config = configparser.ConfigParser()
config.read('config.ini')

CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ASSISTANT_ID_MAIN = os.getenv('ASSISTANT_ID')

app = Flask(__name__)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)
assistant_main = client.beta.assistants.retrieve(assistant_id=ASSISTANT_ID_MAIN)
thread = client.beta.threads.create()

TERMINAL_STATES = ["expired", "completed", "failed", "incomplete", "cancelled"]

def display_loading_animation(user_id, loading_seconds=20):
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    data = {
        "chatId": user_id,
        "loadingSeconds": loading_seconds
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        print(f"Error displaying loading animation: {response.status_code} - {response.text}")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    user_id = event.source.user_id

    display_loading_animation(user_id)

    message = client.beta.threads.messages.create(thread_id=thread.id, role="user", content=user_message)
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant_main.id,
        truncation_strategy={"type": "last_messages", "last_messages": 10},
    )
    retrieved_run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
    
    assistant_response = ""
    if retrieved_run.status in TERMINAL_STATES:
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        assistant_response = messages.data[0].content[0].text.value

    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=assistant_response))
    except:
        print(traceback.format_exc())
        line_bot_api.reply_message(event.reply_token, TextSendMessage('你所使用的OPENAI API key額度可能已經超過，請於後台Log內確認錯誤訊息'))

@handler.add(PostbackEvent)
def handle_postback(event):
    print(event.postback.data)

@handler.add(MemberJoinedEvent)
def welcome(event):
    uid = event.joined.members[0].user_id
    gid = event.source.group_id
    profile = line_bot_api.get_group_member_profile(gid, uid)
    name = profile.display_name
    message = TextSendMessage(text=f'{name}歡迎加入')
    line_bot_api.reply_message(event.reply_token, message)

if __name__ == "__main__":
    port = 5000
    app.run(host='0.0.0.0', port=port)
