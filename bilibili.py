import logging

from bilitool import CheckFormat, LoginController, UploadController
from bilitool.model.model import Model


def upload_video(video_path: str, output_fn: str) -> str:
    LoginController().check_bilibili_login()
    uploader = UploadController()
    upload_metadata = uploader.package_upload_metadata(
        copyright=1,
        tid=5,
        title=output_fn,
        desc="由 https://github.com/BoYanZh/Apex-Crispy-Duck 生成",
        tag="FPS,第一视角,吃鸡,游戏视频,电子竞技,APEX英雄,精彩集锦,合集",
        source="",
        cover="",
        dynamic="",
    )
    Model().update_multiple_config("upload", upload_metadata)
    bilibili_filename = uploader.upload_video(video_path, cdn=None)
    publish_video_response = uploader.bili_uploader.publish_video(
        bilibili_filename=bilibili_filename
    )
    if publish_video_response["code"] == 0:
        bvid = publish_video_response["data"]["bvid"]
        logging.info(f"upload success!\tbvid:{bvid}")
        avid = CheckFormat().bv2av(bvid)
        return f"https://www.bilibili.com/video/av{avid}/"
    else:
        logging.error(publish_video_response["message"])
        return ""
