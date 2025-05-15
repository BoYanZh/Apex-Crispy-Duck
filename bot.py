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
)

_original_edit_original_response = disnake.Interaction.edit_original_response


async def _patched_edit_original_response(*args, **kwargs):
    try:
        return await _original_edit_original_response(*args, **kwargs)
    except Exception as e:
        logging.error(f"Error in edit_original_response: {e}")
    finally:
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


async def create_final_video(
    inter: disnake.ApplicationCommandInteraction,
    texts: list[str],
    fns: list[str],
    output_fn: str,
) -> str:
    if len(texts) == 0:
        await inter.edit_original_response("no messages found for videos")
        return ""
    await inter.edit_original_response(f"processing {len(texts)} videos...")
    video_durations = []
    for i, (text, fn) in enumerate(zip(texts, fns)):
        await inter.edit_original_response(f"processing videos... {i+1}/{len(texts)}")
        if not os.path.exists(os.path.join(OUTPUT_VIDEO_PATH, "tmp", fn)):
            await asyncio.to_thread(process_video, fn, text)
            video_durations.append(
                await asyncio.to_thread(
                    get_media_duration, os.path.join(VIDEO_PATH, fn)
                )
            )
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
    return video_path


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
) -> None:
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
    video_path = await create_final_video(inter, texts, fns, output_fn)
    if video_path == "":
        return
    await inter.edit_original_response("moving videos to homelab...")
    await asyncio.to_thread(scp, video_path, f"{SCP_DST_PATH}/{output_fn}.mp4")
    await inter.edit_original_response(f"{SCP_DST_URL}/{output_fn}.mp4")


@bot.slash_command(description="Bake a video from messages within the last 24 hours.")
async def bake(inter: disnake.ApplicationCommandInteraction, hours: int = 24) -> None:
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
    video_path = await create_final_video(inter, texts, fns, output_fn)
    if inter.guild_id == TEST_GUILD:
        await inter.edit_original_response(
            f"it's a test server, local file: {video_path}"
        )
        return
    if video_path == "":
        return
    await inter.edit_original_response("moving videos to homelab...")
    await asyncio.to_thread(scp, video_path, f"{SCP_DST_PATH}/{output_fn}.mp4")
    await inter.edit_original_response(f"{SCP_DST_URL}/{output_fn}.mp4")


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
