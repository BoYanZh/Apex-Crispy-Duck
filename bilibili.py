import logging
import re
import subprocess

from utils import subprocess_run

subprocess.run = subprocess_run


def upload_video(video_path: str, image_path: str, title: str) -> str:
    """
    Uploads a video to Bilibili using the biliup CLI tool.
    """
    command = [
        "biliup",
        "upload",
        video_path,
        "--submit",
        "app",
        "--title",
        title,
        "--cover",
        image_path,
        "--copyright",
        "1",
        "--tid",
        "171",
        "--desc",
        "由 https://github.com/BoYanZh/Apex-Crispy-Duck 生成",
        "--tag",
        "FPS,第一视角,吃鸡,游戏视频,电子竞技,APEX英雄,精彩集锦",
    ]

    try:
        # The subprocess_run in utils.py will log the command.
        result = subprocess.run(
            command,
            check=True,
            text=True,
            encoding="utf-8",
            stream_print=True,  # Print output in real-time
        )
        output = result.stdout
        logging.info(f"biliup output: {output}")

        # Try to find the video URL or aid in the output
        # New format: ResponseData { ..., "aid": Number(1234567890), ... }
        aid_match = re.search(r'"aid":\s*Number\((\d+)\)', output)
        if aid_match:
            aid = aid_match.group(1)
            logging.info(f"Upload success! aid: {aid}")
            return f"https://www.bilibili.com/video/av{aid}"
        logging.error("Could not find video URL or aid in biliup output.")
        return ""

    except subprocess.CalledProcessError as e:
        logging.error(f"biliup upload failed: {e}")
        logging.error(f"stdout: {e.stdout}")
        logging.error(f"stderr: {e.stderr}")
        return ""
    except FileNotFoundError:
        logging.error(
            "biliup command not found. Please ensure it is installed and in your PATH."
        )
        return ""


# The login check is now handled by biliup, assuming cookies.json is present.
# You can run `biliup login` to generate the cookie file.
logging.info("Using biliup CLI for Bilibili uploads.")
