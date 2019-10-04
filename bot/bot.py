#!/usr/bin/env python3
from __future__ import unicode_literals

import asyncio
import logging
import os
import config

# from pytube import YouTube


import youtube_dl

from telethon import Button
from telethon import TelegramClient, events
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageUploadDocumentAction


# Enable logging
logging.basicConfig(
    filename='bot.log',
    filemode='a+',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING)

logger = logging.getLogger(__name__)

TOKEN = config.BOT_TOKEN
NAME = TOKEN.split(':')[0]
bot = TelegramClient(NAME, config.API_ID, config.API_HASH)

# ==============================  Commands ==============================


@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    pass


@bot.on(events.NewMessage(incoming=True, pattern=r'^http'))
async def link_handler(event):
    async with bot.conversation(event.chat_id) as conv:

        await conv.send_message(
            'Searching...'
        )
    
        # =====  1  =====
        # vid = YouTube()
        # title = vid.streams.first().download('uploads/')

        # =====  2  =====

        meta = get_resource_data(event.message.raw_text)

        await bot.send_file(
            event.chat_id,
            meta['thumbnail']
        )

        select_format = await bot.send_message(
                            event.chat_id,
                            meta['title'],
                            buttons=[
                                [Button.inline('MP4', b'mp4'),
                                Button.inline('MP3', b'mp3')],
                                [Button.inline('Back', b'back')]
                            ]
                        )

        response = await conv.wait_event(events.CallbackQuery)

        if response.data in b'mp3 mp4':
            await conv.send_message('Downloading...')
            out_format = response.data.decode("utf-8") 
            res = download_file(meta['webpage_url'], out_format)
            async with bot.action(event.chat, 'document') as action:
                await bot.send_file(
                    event.chat,
                    res,
                    progress_callback=action.progress)
        elif b'back' in response.data:
            await conv.send_message(
                'Enter link')
            conv.cancel()

def get_resource_data(url):
    ydl_opts = {
        'format': 'mp4'
    }
    info = dict()
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            i = ydl.extract_info(
                url,
                download=False
                )
            return i
    except Exception as ex:
        print(f'{ex}')


def download_file(url, out_format):
    if out_format == 'mp4':
        ydl_opts = {
            'format': 'mp4'
        }
    elif out_format == 'mp3':
        ydl_opts = {
            'format': 'bestaudio/best',
            # 'outtmpl': outtmpl,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            },
                {'key': 'FFmpegMetadata'},
            ],
        }
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            i = ydl.extract_info(url)
            filename = f"{i['title']}-{i['id']}.{out_format}"
            return filename
    except Exception as ex:
        print(f'{ex}')


# ==============================  Commands ==============================

bot.start(bot_token=TOKEN)
bot.run_until_disconnected()
