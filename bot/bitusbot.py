#!/usr/bin/env python3
from __future__ import unicode_literals

import logging
import os
import os.path as op
import config
import commands as cmd
import glob


import youtube_dl
from datetime import datetime, timedelta
from sclib.asyncio import SoundcloudAPI, Track

from sqlalchemy import (create_engine, inspect, func, Column, Integer, String,
                        DateTime, Float, and_)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from telethon import Button
from telethon import TelegramClient, events
# from telethon.tl.functions.messages import SetTypingRequest
# from telethon.tl.types import SendMessageUploadDocumentAction


# Enable logging
logging.basicConfig(
    filename='bot.log',
    filemode='a+',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)

logger = logging.getLogger(__name__)

TOKEN = config.BOT_TOKEN
NAME = TOKEN.split(':')[0]
bot = TelegramClient(NAME, config.API_ID, config.API_HASH)


# =================================  DB =================================

app_dir = op.realpath(os.path.dirname(__file__))
database_path = op.join(app_dir, config.DATABASE_FILE)
Base = declarative_base()


class DB:
    def __init__(self):
        self.engine = create_engine('sqlite:///' + database_path, echo=True)
        self.conn = self.engine.connect()
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.build_sample_db()

    def execute(self, command):
        return self.conn.execute(command)

    def exec(self, obj):
        self.session.add(obj)
        self.session.commit()

    def add(self, obj):
        self.exec(obj)

    def build_sample_db(self):
        # check table exists
        if not inspect(self.engine).get_table_names():
            Base = declarative_base()
            Base.metadata.create_all(bind=self.engine, tables=(
                User.__table__,
                Order.__table__,
                Invoice.__table__,
                Operation.__table__))


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    date = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, nullable=True)
    exp_date = Column(DateTime(), nullable=True)

    def __str__(self):
        return "{}, {}".format(self.user_id, self.username)

    def __repr__(self):
        return "{}: {}".format(self.id, self.__str__())


class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    date = Column(DateTime(timezone=True), server_default=func.now())
    link = Column(String)
    source = Column(String)
    filesize = Column(Integer)


class Invoice(Base):
    __tablename__ = 'invoices'

    id = Column(Integer, primary_key=True)
    label = Column(String)
    user_id = Column(Integer)
    price = (Float)


class Operation(Base):
    __tablename__ = 'operations'

    operation_id = Column(Integer, primary_key=True)
    invoice_label = Column(String)
    date = Column(DateTime)


# =================================  DB =================================
# ==============================  Commands ==============================


class Text:
    m_start = 'Enter Youtube or Soundcloud link here'


async def get_resource_data(url):
    ydl_opts = {
        'format': 'mp4',
        'outtmpl': 'res/%(id)s.%(ext)s',
    }
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as ex:
        raise Exception(ex)


async def download_file(url, out_format):
    if out_format == 'mp4':
        ydl_opts = {
            'format': 'mp4',
            'outtmpl': 'res/%(id)s.%(ext)s',
        }
    elif out_format == 'mp3':
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'res/%(id)s.%(ext)s',
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
            i = ydl.extract_info(url, download=True)
            return i
    except Exception as ex:
        print(f'{ex}')


def is_user_exists(user_id: int) -> bool:
    return db.session.query(User.user_id).filter_by(user_id=user_id).scalar()


def is_able_to_download(user_id: int, filesize: int = 0) -> bool:
    """
    user able to download if:
    - less then 2 resources last 24 hours
    - filesize less then 200 mb
    """

    if cmd.is_admin(user_id):
        return True
    elif cmd.is_friend(user_id):
        return True

    # filesize managing

    try:
        if filesize > config.QUOTA_SIZE:
            return False
    except TypeError:
        return False

    # quontity managing

    last_day = datetime.now() - timedelta(hours=24)
    recent_num = db.session.query(Order) \
        .filter(
            and_(
                Order.date.between(last_day, datetime.now()),
                Order.user_id == user_id)) \
        .count()

    return False if recent_num >= config.QUOTA_NUM else True


def clear_resources():
    files = glob.glob('res/*')
    for f in files:
        os.remove(f)

# ==============================  Bot ==============================


@bot.on(events.NewMessage(pattern='/start'))
async def start(event):

    if not is_user_exists(event.chat.id):
        db.add(
            User(
                user_id=event.chat.id,
                username=event.chat.username,
                first_name=event.chat.first_name,
                last_name=event.chat.last_name))

    await bot.send_message(
        event.chat_id,
        Text.m_start
    )


@bot.on(events.NewMessage(incoming=True, pattern=r'^https://soundcloud.com/'))
async def soundcloud_link_handler(event):
    api = SoundcloudAPI()
    track = await api.resolve(event.raw_text)

    assert type(track) is Track

    filename = f'{track.artist} - {track.title}.mp3'

    with open(filename, 'wb+') as fp:
        await track.write_mp3_to(fp)

    async with bot.action(event.chat, 'document') as action:
        await bot.send_file(
            event.chat,
            filename,
            progress_callback=action.progress)
        logger.info(f'file has been sent: {filename}')
        os.remove(filename)


@bot.on(events.NewMessage(incoming=True, pattern=r'http.*'))
async def link_handler(event):
    async with bot.conversation(event.chat_id) as conv:

        msg_searching = await conv.send_message('Searching...')
        logger.info(f'search for: {event.message.raw_text}')

        meta = await get_resource_data(event.message.raw_text)

        await bot.delete_messages(event.chat_id, msg_searching.id)

        if not is_able_to_download(event.chat_id, meta.get('filesize', 0)):
            await conv.send_message("You're out of download qouta")
            conv.cancel()
            return False

        msg_prew = await bot.send_file(
            event.chat_id,
            meta['thumbnail'].split('?')[0]
        )

        msg_suggesting = await bot.send_message(
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
            try:
                logger.info(f'response: {response.data}')
                await bot.delete_messages(event.chat_id, msg_prew.id)
                await bot.delete_messages(event.chat_id, msg_suggesting.id)

                status_msg = await conv.send_message(
                    'Downloading...',
                    silent=True)
                out_format = response.data.decode("utf-8")
                resource = await download_file(meta['webpage_url'], out_format)
                try:
                    status_msg = await bot.edit_message(
                        status_msg, 'Uploading...')
                except Exception:
                    pass
                file_path = glob.glob(f'res/{resource["id"]}.*')[0]
                async with bot.action(event.chat, 'document') as action:
                    await bot.send_file(
                        event.chat,
                        file_path,
                        caption=meta['title'],
                        progress_callback=action.progress)
                    logger.info(f'file has been sent: {file_path}')
                    db.add(Order(
                        user_id=event.chat.id,
                        link=resource.get('webpage_url'),
                        source=resource.get('extractor'),
                        filesize=os.path.getsize(file_path)
                    ))
                    await bot.delete_messages(event.chat_id, status_msg.id)
                    os.remove(file_path)
                    logger.info(f'file has been removed: {file_path}')
            except Exception as ex:
                logger.warning(f'{ex}')
                await conv.send_message('ERROR.\nSorry. Something went wrong')
        elif b'back' in response.data:
            logger.info('back button clicked')
            await bot.delete_messages(event.chat_id, msg_prew.id)
            await bot.delete_messages(event.chat_id, msg_suggesting.id)
            await conv.send_message(
                Text.m_start)
            conv.cancel()


@bot.on(events.NewMessage(pattern='/getlogs'))
async def get_logs_handler(event):
    logger.info(f'{event.chat_id}: get_logs_handler')
    try:
        if cmd.is_admin(event.chat_id):
            f = open('bot.log', 'rb')
            await bot.send_file(
                event.chat_id,
                f
            )
    except Exception as ex:
        logger.warning(ex, exc_info=True)


@bot.on(events.NewMessage(pattern='/getdb'))
async def get_db_handler(event):
    logger.info(f'{event.chat_id}: get_logs_handler')
    try:
        if cmd.is_admin(event.chat_id):
            f = open(database_path, 'rb')
            await bot.send_file(
                event.chat_id,
                f
            )
    except Exception as ex:
        logger.warning(ex, exc_info=True)


@bot.on(events.NewMessage(pattern='/clear'))
async def clear_hadler(event):
    logger.info(f'{event.chat_id}: clear_handler')
    try:
        if cmd.is_admin(event.chat_id):
            clear_resources()
    except Exception as ex:
        logger.warning(ex, exc_info=True)


# ==============================  Bot ==============================


if __name__ == '__main__':
    db = DB()
    bot.start(bot_token=TOKEN)
    bot.run_until_disconnected()
