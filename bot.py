import asyncio
import datetime
import hashlib
import json
import logging
import os
import traceback

import disnake
from disnake.ext import commands

from config import *
from utils import *

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)

intents = disnake.Intents.default()
intents.message_content = True
command_sync_flags = commands.CommandSyncFlags.all()

bot = commands.Bot(
    command_prefix="!",
    command_sync_flags=command_sync_flags,
    intents=intents,
    test_guilds=[RUN_GUILD, TEST_GUILD],
    activity=disnake.Activity(
        name=f"ffmpeg & ffprobe", type=disnake.ActivityType.playing
    ),
)

_original_edit_original_response = disnake.Interaction.edit_original_response


async def _patched_edit_original_response(*args, **kwargs):
    retries = 3
    for i in range(retries):
        try:
            return await _original_edit_original_response(*args, **kwargs)
        except Exception as e:
            logging.error(
                f"Error in edit_original_response (attempt {i+1}/{retries}): {e}"
            )
            if i < retries - 1:
                await asyncio.sleep(2 ** (i + 1))
        finally:
            if len(args) > 1 and isinstance(args[1], str):
                content = args[1]
                logging.info(f"edit_original_response: {content}")


disnake.Interaction.edit_original_response = _patched_edit_original_response


async def collect_messages(hours: int = 72) -> dict[str, list[dict[str, str]]]:
    today = datetime.datetime.now()
    ago = today - datetime.timedelta(hours=hours)
    guild = bot.get_guild(RUN_GUILD)
    res: dict[str, list[dict[str, str]]] = {}
    if not guild:
        logging.error("Guild not found")
        return res
    for category in guild.categories:
        if category.name != CATEGORY:
            continue
        for channel in category.text_channels:
            messages = await channel.history(after=ago).flatten()
            items = []
            for msg in messages:
                url = extract_url_with_prefix(msg.content, "https://outplayed.tv")
                if not url:
                    continue
                if any(reaction.emoji in DENY_EMOJIS for reaction in msg.reactions):
                    continue
                items.append({msg.author.display_name: msg.content})
            res[channel.name] = items
    return res


async def fetch_one_year_msg() -> None:
    today = datetime.datetime.now()
    res: dict[str, dict[str, dict[str, str]]] = {}
    msg_count = 0
    for i in range(365, -1, -1):
        after = today - datetime.timedelta(hours=24 * (i + 1))
        before = today - datetime.timedelta(hours=24 * i)
        guild = bot.get_guild(RUN_GUILD)
        if not guild:
            logging.error("Guild not found")
            return
        for category in guild.categories:
            if category.name != CATEGORY:
                continue
            for channel in category.text_channels:
                if channel.name not in res:
                    res[channel.name] = {}
                messages = await channel.history(after=after, before=before).flatten()
                for msg in messages:
                    url = extract_url_with_prefix(msg.content, "https://outplayed.tv")
                    if not url:
                        continue
                    if any(reaction.emoji in DENY_EMOJIS for reaction in msg.reactions):
                        continue
                    if msg.author.display_name not in res[channel.name]:
                        res[channel.name][msg.author.display_name] = {}
                    res[channel.name][msg.author.display_name][
                        msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    ] = msg.content
                    msg_count += 1
    json.dump(
        res,
        open(os.path.join(OUTPUT_TEXT_PATH, f"all.json"), "w"),
        ensure_ascii=False,
        indent=4,
    )


async def create_and_upload_final_video(
    inter: disnake.ApplicationCommandInteraction,
    texts: list[str],
    fns: list[str],
    output_fn: str,
    title: str = "",
    force_process: bool = False,
) -> None:
    if len(texts) == 0:
        await inter.edit_original_response("no messages found for videos")
        return ""
    if title == "":
        title = output_fn
    await inter.edit_original_response(f"processing {len(texts)} videos...")
    video_durations = []
    for i, (text, fn) in enumerate(zip(texts, fns)):
        await inter.edit_original_response(f"processing videos... {i+1}/{len(texts)}")
        if (
            not os.path.exists(os.path.join(OUTPUT_VIDEO_PATH, "tmp", fn))
            or force_process
        ):
            await asyncio.to_thread(process_video, fn, text)
        video_durations.append(
            await asyncio.to_thread(get_media_duration, os.path.join(VIDEO_PATH, fn))
        )
    logging.info(f"total video duration: {sum(video_durations)}")
    await inter.edit_original_response("merging audios...")
    audio_path = await asyncio.to_thread(
        merge_audios,
        os.path.join(OUTPUT_AUDIO_PATH, "tmp", f"{output_fn}.m4a"),
        sum(video_durations),
    )
    await inter.edit_original_response("merging videos with bgm...")
    video_path = await asyncio.to_thread(
        merge_videos_with_bgm,
        fns,
        os.path.join(OUTPUT_VIDEO_PATH, f"{output_fn}.mp4"),
        audio_path,
    )
    image_path = await asyncio.to_thread(
        create_cover_image,
        os.path.join(VIDEO_PATH, fns[0]),
        os.path.join(OUTPUT_IMAGE_PATH, f"{output_fn}.png"),
    )
    duration = await asyncio.to_thread(get_media_duration, video_path)

    def format_seconds(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours == 0:
            if minutes == 0:
                return f"{secs:02d}s"
            return f"{minutes:02d}:{secs:02d}"
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    await inter.edit_original_response(
        f"uploading the final video ({format_seconds(duration)}) with title {title}..."
    )
    channel = bot.get_channel(inter.channel_id) or await bot.fetch_channel(
        inter.channel_id
    )
    logging.info(f"Uploading video {video_path} with title {title}")

    async def youtube_worker():
        msg = "Error uploading video to YouTube. No url returned."
        logging.info(
            f'running youtube.upload_video("{video_path}", "{image_path}", "{title}")'
        )
        try:
            msg = await asyncio.to_thread(
                youtube.upload_video, video_path, image_path, title
            )
            if msg == "":
                raise Exception("Upload failed, no URL returned.")
        except Exception as e:
            logging.error(f"Error uploading video: {e}")
            msg = "Error uploading video to YouTube. Please check the logs."
        if inter.is_expired():
            await channel.send(msg)
        else:
            await inter.edit_original_response(msg)

    async def bilibili_worker():
        msg = "Error uploading video to Bilibili. No url returned."
        logging.info(
            f'running bilibili.upload_video("{video_path}", "{image_path}", "{title}")'
        )
        try:
            msg = await asyncio.to_thread(
                bilibili.upload_video, video_path, image_path, title
            )
            if msg == "":
                raise Exception("Upload failed, no URL returned.")
        except Exception as e:
            logging.error(f"Error uploading video: {e}")
            msg = "Error uploading video to Bilibili. Please check the logs."
        await channel.send(msg)

    await asyncio.gather(youtube_worker(), bilibili_worker())


@bot.event
async def on_ready():
    logging.info(f"We have logged in as {bot.user}")


@bot.event
async def on_slash_command_error(
    inter: disnake.ApplicationCommandInteraction,
    exception: commands.CommandError,
):
    logging.error(
        f"An exception occurred: {exception}"
        + "\n".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
    )
    await inter.edit_original_response(f"{exception}! Please contact the developer!")


@bot.slash_command(
    description="Excavate a video from old messages within a time range."
)
async def excavate(
    inter: disnake.ApplicationCommandInteraction,
    minute_start: int = 0,
    duration: int = 10,
    title: str = "",
) -> None:
    logging.info(
        f"@{inter.user.display_name} /excavate minute_start:{minute_start} duration:{duration} title:{title}"
    )
    await inter.response.defer()
    if not os.path.exists(os.path.join(OUTPUT_TEXT_PATH, "all.json")):
        await inter.edit_original_response("fetching 1 year messages...")
        await fetch_one_year_msg()
    minute_end = minute_start + duration
    if minute_start < 0 or duration < 0:
        await inter.edit_original_response("invalid parameters")
        return
    output_fn = f"excavate-{minute_start}-{minute_end}"
    data = await asyncio.to_thread(
        json.load,
        open(os.path.join(OUTPUT_TEXT_PATH, "all.json"), "r", encoding="utf-8"),
    )
    timeline_iter = create_global_timeline_iterator(data, CHANNELS)
    texts = []
    fns = []
    current_duration = 0
    idx_map = {CHANNELS[i]: i for i in range(len(CHANNELS))}
    tmp_res: list[list[tuple[str, str]]] = [[] for _ in range(len(idx_map))]
    first_reach = minute_start == 0
    await inter.edit_original_response(f"checking videos lengths...")
    for channel, dt, user, message in timeline_iter:
        if channel not in CHANNELS:
            continue
        page_url = extract_url_with_prefix(message, "https://outplayed.tv/")
        if not page_url:
            continue
        fn = hashlib.md5(page_url.encode()).hexdigest() + ".mp4"
        if not os.path.exists(os.path.join(VIDEO_PATH, fn)):
            video_url = await extract_video_url(page_url)
            if not video_url:
                continue
            await download_video(video_url, os.path.join(VIDEO_PATH, fn))
        video_duration = await asyncio.to_thread(
            get_media_duration, os.path.join(VIDEO_PATH, fn)
        )
        if video_duration == 0.0:
            logging.warning(
                f"video duration is 0: {os.path.join(VIDEO_PATH, fn)}, message {message}"
            )
            continue
        current_duration += video_duration
        if current_duration < minute_start * 60:
            continue
        elif not first_reach:
            first_reach = True
            continue
        simple_msg = cleanup_msg(message)
        tmp_res[idx_map[channel]].append(
            ("@" + user + " " + dt.strftime("%Y-%m-%d") + "\n" + simple_msg, fn)
        )
        if current_duration > minute_end * 60:
            break
    for l in tmp_res:
        for item in l:
            texts.append(item[0])
            fns.append(item[1])
    await create_and_upload_final_video(inter, texts, fns, output_fn, title)


@bot.slash_command(description="Bake a video from messages within the last 8 hours.")
async def bake(
    inter: disnake.ApplicationCommandInteraction, hours: int = 8, title: str = ""
) -> None:
    logging.info(f"@{inter.user.display_name} /bake hours:{hours} title:{title}")
    current_datetime = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_fn = current_datetime
    await inter.response.defer()
    await inter.edit_original_response("extracting messages...")
    data = await collect_messages(hours)
    json.dump(
        data,
        open(os.path.join(OUTPUT_TEXT_PATH, f"{output_fn}.json"), "w"),
        ensure_ascii=False,
        indent=4,
    )
    texts = []
    fns = []
    items = [item for channel in CHANNELS for item in data[channel]]
    await inter.edit_original_response(f"downloading {len(items)} videos...")
    for i, item in enumerate(items):
        for user, message in item.items():
            await inter.edit_original_response(
                f"downloading videos... {i+1}/{len(items)}"
            )
            page_url = extract_url_with_prefix(message, "https://outplayed.tv/")
            if not page_url:
                continue
            fn = hashlib.md5(page_url.encode()).hexdigest() + ".mp4"
            if not os.path.exists(os.path.join(VIDEO_PATH, fn)):
                video_url = await extract_video_url(page_url)
                if not video_url:
                    continue
                await download_video(video_url, os.path.join(VIDEO_PATH, fn))
            video_duration = await asyncio.to_thread(
                get_media_duration, os.path.join(VIDEO_PATH, fn)
            )
            if video_duration == 0.0:
                logging.warning(
                    f"video duration is 0: {os.path.join(VIDEO_PATH, fn)}, message {message}"
                )
                continue
            simple_msg = cleanup_msg(message)
            texts.append("@" + user + "\n" + simple_msg)
            fns.append(fn)
    await create_and_upload_final_video(inter, texts, fns, output_fn, title)


class CustomizeModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Title",
                placeholder="Foo Tag",
                custom_id="title",
                style=disnake.TextInputStyle.short,
                max_length=50,
            ),
            disnake.ui.TextInput(
                label="Content",
                placeholder="<description> <link> [@user]\n<description> <link> [@user]\n...",
                custom_id="content",
                style=disnake.TextInputStyle.paragraph,
            ),
            disnake.ui.TextInput(
                label="User",
                placeholder="John Doe (leave empty for yourself)",
                custom_id="user",
                style=disnake.TextInputStyle.short,
                required=False,
            ),
        ]
        super().__init__(title="Video Details", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        logging.info(
            f"@{inter.user.display_name} /customize title:{inter.text_values['title']} content:{inter.text_values['content']}"
        )
        title = inter.text_values["title"]
        content = inter.text_values["content"]
        user = inter.text_values["user"]
        current_datetime = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_fn = title + "-" + current_datetime
        await inter.response.defer()
        await inter.edit_original_response("extracting messages...")
        messages = [
            line
            for line in content.splitlines()
            if extract_url_with_prefix(line, "https://outplayed.tv/")
        ]
        user = inter.user.display_name if user == "" else user
        texts = []
        fns = []
        await inter.edit_original_response(f"downloading {len(messages)} videos...")
        for i, message in enumerate(messages):
            await inter.edit_original_response(
                f"downloading videos... {i+1}/{len(messages)}"
            )
            page_url = extract_url_with_prefix(message, "https://outplayed.tv/")
            if not page_url:
                continue
            fn = hashlib.md5(page_url.encode()).hexdigest() + ".mp4"
            if not os.path.exists(os.path.join(VIDEO_PATH, fn)):
                video_url = await extract_video_url(page_url)
                if not video_url:
                    continue
                await download_video(video_url, os.path.join(VIDEO_PATH, fn))
            video_duration = await asyncio.to_thread(
                get_media_duration, os.path.join(VIDEO_PATH, fn)
            )
            if video_duration == 0.0:
                logging.warning(
                    f"video duration is 0: {os.path.join(VIDEO_PATH, fn)}, message {message}"
                )
                continue
            parts = message.rsplit("@", 1)
            if len(parts) > 1:
                simple_msg = cleanup_msg(parts[0])
                user = parts[1].strip().lstrip("@") if parts[1].strip() else user
            else:
                simple_msg = cleanup_msg(message)
            texts.append("@" + user + "\n" + simple_msg)
            fns.append(fn)
        await create_and_upload_final_video(inter, texts, fns, output_fn, title, True)


@bot.slash_command(description="Bake a video from customized messages, 1 per line.")
async def customize(inter: disnake.ApplicationCommandInteraction):
    await inter.response.send_modal(modal=CustomizeModal())


@bot.slash_command(description="Get the list of commands.")
async def help(inter: disnake.ApplicationCommandInteraction, command: str = "") -> None:
    logging.info(f"@{inter.user.display_name} /help command:{command}")
    await inter.response.defer()
    embed = disnake.Embed(title="Commands Info", color=disnake.Color.blue())
    if command != "":
        for s_command in bot.slash_commands:
            if s_command.name == command:
                val = s_command.description
                for option in s_command.options:
                    val += "\n"
                    val += option.name + " - " + option.description
                embed.add_field(name=command, value=val, inline=True)
                await inter.edit_original_response(embed=embed)
                return
        embed.description = f"Command {command} doesn't exist."
    else:
        for s_command in bot.slash_commands:
            if s_command.name == "help":
                continue
            embed.add_field(
                name=s_command.name, value=s_command.description, inline=True
            )
    await inter.edit_original_response(embed=embed)


if __name__ == "__main__":
    import bilibili
    import youtube

    bot.run(BOT_TOKEN)
