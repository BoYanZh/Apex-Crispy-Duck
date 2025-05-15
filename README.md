# Apex Crispy Duck

A discord bot that can generate videos, collected from outplayed.tv, in Apex Crispy Duck style.

## Setup

Install `ffmpeg`, `ffprobe`, and `pdm`. Get your `youtube-oauth2.json` as [it](https://developers.google.com/youtube/v3/guides/uploading_a_video) told.

```bash
pdm install
cp .env.example .env # and edit the .env file
pdm run bot.py
```
