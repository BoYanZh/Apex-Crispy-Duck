import datetime
import io
import json
import logging
import os
import random
import re
import shlex
import subprocess
import tempfile
from urllib.parse import urlparse

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from config import *

_original_subprocess_run = subprocess.run


def subprocess_run(*args, **kwargs):
    run_args = args[0]
    logging.info(f"Running command: {shlex.join(run_args)}")
    return _original_subprocess_run(*args, **kwargs)


subprocess.run = subprocess_run


async def extract_video_url(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                html_content = await response.text()
        video_src_pattern = re.search(
            r'<video[^>]*src=[\'"]([^\'"]+)[\'"]', html_content
        )
        if not video_src_pattern:
            logging.error(f"No video tag or src attribute found in {url}")
            return None
        video_url = video_src_pattern.group(1)
        if video_url.startswith("/"):
            base_url = "{0.scheme}://{0.netloc}".format(urlparse(url))
            video_url = base_url + video_url
        if not video_url.startswith("http"):
            return None
        return video_url

    except Exception as e:
        logging.error(f"Error during URL extraction: {e} in {url}")
        return None


async def download_video(video_url, output_path="downloaded_video.mp4"):
    try:
        logging.info(f"Downloading video from: {video_url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        if chunk:
                            f.write(chunk)

        logging.info(f"Video successfully downloaded to: {output_path}")
        return True

    except Exception as e:
        logging.error(f"Error during download: {e}")
        return False


def get_media_duration(media_path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        media_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        logging.error(f"Error getting media {media_path} duration: {e}")
        return 0.0


def process_video(fn: str, text: str) -> None:
    """Process video by adding text overlay and normalizing audio."""
    args = [
        "ffmpeg",
        "-hwaccel",
        "cuda",
        "-i",
        os.path.join(VIDEO_PATH, fn),
        "-y",
        "-vf",
        f"scale=1920:1080,drawtext=text='{text}':fontfile={FONT_FILE_PATH}:font={FONT_NAME}:fontcolor=white:fontsize=64:borderw=4:bordercolor=black:x=20:y=20",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v",
        "h264_nvenc",
        "-preset",
        "fast",
        "-rc",
        "vbr",
        "-cq",
        "23",
        "-b:v",
        "0",
        "-r",
        "30",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-y",
        os.path.join(OUTPUT_VIDEO_PATH, "tmp", fn),
    ]
    subprocess.run(args, check=True)


def merge_audios(
    output_path: str,
    minimum_duration: float = 120,
):
    """Merge multiple audio files into one file."""
    fns = [fn for fn in os.listdir(AUDIO_PATH)]
    for fn in fns:
        if fn.endswith("_standardized.m4a"):
            continue
        file_base, _ = os.path.splitext(fn)
        args = [
            "ffmpeg",
            "-i",
            os.path.join(AUDIO_PATH, fn),
            "-vn",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-y",
            os.path.join(AUDIO_PATH, f"{file_base}_standardized.m4a"),
        ]
        subprocess.run(args, check=True)
        os.remove(os.path.join(AUDIO_PATH, fn))
    fns = [fn for fn in os.listdir(AUDIO_PATH)]
    random.shuffle(fns)
    current_duration = 0.0
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as f:
        for fn in fns:
            duration = get_media_duration(os.path.join(AUDIO_PATH, fn))
            if duration == 0.0:
                logging.error(f"Error getting duration for {fn}")
                continue
            f.write(f"file '{os.path.abspath(os.path.join(AUDIO_PATH, fn))}'\n")
            current_duration += duration
            if current_duration > minimum_duration:
                break
        logging.info(f"total audio duration: {current_duration}")
        f.flush()
        args = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            f.name,
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            output_path,
        ]
        subprocess.run(args, check=True)
    return os.path.abspath(output_path)


def merge_videos_with_bgm(
    fns: list[str],
    output_path: str,
    audio_path: str = "./assets/bili1.m4a",
    video_volume: float = 1.0,
    bgm_volume: float = 0.25,
) -> str:
    """Merge multiple videos into one file and add background music in one step."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as f:
        f.write(
            "\n".join(
                f"file '{os.path.abspath(os.path.join(OUTPUT_VIDEO_PATH, 'tmp', fn))}'"
                for fn in fns
            )
        )
        f.flush()
        filter_complex = (
            f"[0:a]volume={video_volume}[v_audio];"
            f"[1:a]volume={bgm_volume}[bgm_audio];"
            "[v_audio][bgm_audio]amix=inputs=2:duration=shortest"
        )
        args = [
            "ffmpeg",
            "-hwaccel",
            "cuda",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            f.name,
            "-i",
            audio_path,
            "-filter_complex",
            filter_complex,
            "-c:v",
            "hevc_nvenc",
            "-preset",
            "p4",
            "-cq",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            output_path,
        ]
        subprocess.run(args, check=True)
    return os.path.abspath(output_path)


def scp(src: str, dst: str) -> None:
    args = ["scp", src, dst]
    subprocess.run(args, check=True)


def extract_url_with_prefix(text, prefix):
    escaped_prefix = re.escape(prefix)
    pattern = escaped_prefix + r'[^\s\'"()<>\[\]{}|\\^`]*'
    match = re.search(pattern, text)
    if match:
        return match.group(0)
    else:
        return ""


def create_global_timeline_iterator(data, channels):
    "return (channel, dt, user, content)"
    all_entries = []
    for channel in channels:
        channel_data = data.get(channel, {})
        for user, msg in channel_data.items():
            for timestamp_str, content in msg.items():
                dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                all_entries.append((channel, dt, user, content))
    sorted_entries = sorted(all_entries, key=lambda x: x[1])
    for entry in sorted_entries:
        yield entry


def cleanup_msg(msg: str) -> str:
    msg = msg.strip()
    msg = re.sub(r"https?://[- \w.%+?&#=/:;@()~\[\]]*$", "", msg)
    msg = re.sub(r"Check out my video! (\#\w+ |)\| Captured by (#|)Outplayed", "", msg)
    msg = re.sub(r"<@\d+>", "", msg)
    msg = msg.strip()
    return msg


def create_cover_image(video_path: str, output_image_path: str) -> str:
    command = [
        "ffmpeg",
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_data, _ = process.communicate()
    image_stream = io.BytesIO(stdout_data)
    img = Image.open(image_stream).convert("RGBA")
    draw = ImageDraw.Draw(img)

    text1 = "Apex"
    text2 = "精彩时刻"
    text3 = datetime.datetime.now().strftime("%m/%d/%y")
    color1 = (255, 223, 0)
    color2 = (255, 69, 0)
    color3 = (0, 150, 0)
    font1 = ImageFont.truetype(FONT_FILE_PATH, 350)
    font2 = ImageFont.truetype(FONT_FILE_PATH, 200)
    font3 = ImageFont.truetype(FONT_FILE_PATH, 150)
    img_width, img_height = img.size
    padding_x = 40
    padding_y = 20

    text1_bbox = draw.textbbox((0, 0), text1, font=font1)
    text1_width = text1_bbox[2] - text1_bbox[0]
    text1_height = text1_bbox[3] - text1_bbox[1]
    text1_x = (img_width - text1_width) / 2
    text1_y = img_height * 0.0

    text2_bbox = draw.textbbox((0, 0), text2, font=font2)
    text2_width = text2_bbox[2] - text2_bbox[0]
    text2_height = text2_bbox[3] - text2_bbox[1]
    text2_x = (img_width - text2_width) / 2
    text2_y = text1_y + text1_height + 100

    text3_bbox = draw.textbbox((0, 0), text3, font=font3)
    text3_width = text3_bbox[2] - text3_bbox[0]
    text3_height = text3_bbox[3] - text3_bbox[1]
    text3_x = (img_width - text3_width) / 2
    text3_y = text2_y + text2_height + 100

    # rect3_x1 = text3_x - padding_x
    # rect3_y1 = text3_y
    # rect3_x2 = text3_x + text3_width + padding_x
    # rect3_y2 = text3_y + text3_height + padding_y * 3

    # draw.rectangle([rect3_x1, rect3_y1, rect3_x2, rect3_y2], fill=(0, 0, 0, 180))

    draw.text(
        (text1_x, text1_y),
        text1,
        fill=color1,
        font=font1,
        stroke_width=20,
        stroke_fill=(0, 0, 0),
    )
    draw.text(
        (text2_x, text2_y),
        text2,
        fill=color2,
        font=font2,
        stroke_width=20,
        stroke_fill=(0, 0, 0),
    )
    draw.text(
        (text3_x, text3_y),
        text3,
        fill=color3,
        font=font3,
        stroke_width=10,
        stroke_fill=(0, 0, 0),
    )
    img.save(output_image_path, optimize=True, compress_level=9)
    return output_image_path
