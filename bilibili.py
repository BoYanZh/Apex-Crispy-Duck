import logging

from bilitool import CheckFormat, LoginController, UploadController
from bilitool.model.model import Model
from requests.adapters import HTTPAdapter


def upload_video(video_path: str, image_path: str, title: str) -> str:
    if not LoginController().check_bilibili_login():
        logging.error("bilibili login check failed")
        return ""
    uploader = UploadController()
    uploader.bili_uploader.session.mount("http://", HTTPAdapter(max_retries=5))
    uploader.bili_uploader.session.mount("https://", HTTPAdapter(max_retries=5))
    upload_metadata = uploader.package_upload_metadata(
        copyright=1,
        tid=171,
        title=title,
        desc="由 https://github.com/BoYanZh/Apex-Crispy-Duck 生成",
        tag="FPS,第一视角,吃鸡,游戏视频,电子竞技,APEX英雄,精彩集锦",
        source="",
        cover=image_path,
        dynamic="",
    )
    if upload_metadata["cover"]:
        upload_metadata["cover"] = uploader.bili_uploader.cover_up(
            upload_metadata["cover"]
        )
    Model().update_multiple_config("upload", upload_metadata)
    bilibili_filename = uploader.upload_video(video_path, cdn=None)
    publish_video_response = uploader.bili_uploader.publish_video(
        bilibili_filename=bilibili_filename
    )
    logging.debug(f"publish_video_response: {publish_video_response}")
    if publish_video_response["code"] == 0:
        bvid = publish_video_response["data"]["bvid"]
        logging.info(f"upload success!\tbvid:{bvid}")
        avid = CheckFormat().bv2av(bvid)
        return f"https://www.bilibili.com/video/av{avid}/"
    else:
        logging.error(publish_video_response["message"])
        return ""


if not LoginController().check_bilibili_login():
    logging.error("BiliBili login check failed")
else:
    logging.info("BiliBili login check passed")
