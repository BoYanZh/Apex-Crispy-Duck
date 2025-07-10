# Apex Crispy Duck

A powerful Discord bot designed to automate the creation of "Apex Legends" highlight compilations. It fetches clips uploaded to outplayed.tv shared in your Discord server, processes them with professional-looking overlays and normalized audio, merges them into a single video with background music, and even generates a custom thumbnail. The entire process is hardware-accelerated using NVIDIA GPUs for maximum speed.

## Features

*   **Automated Clip Ingestion**: Listens to specified Discord channels for video links (e.g., from outplayed.tv).
*   **Video Processing**:
    *   Standardizes all clips to 1080p resolution.
    *   Adds a customizable text overlay to each clip, using the content of the original Discord message.
    *   Normalizes audio levels across all clips for a consistent listening experience.
*   **Compilation & Background Music**:
    *   Merges multiple processed clips into a final highlight reel.
    *   Intelligently mixes in a background music track, created from a library of your own audio files.
*   **Custom Thumbnail Generation**: Creates an eye-catching thumbnail for your video, featuring text and a frame from the compilation.
*   **High-Performance Encoding**: Leverages NVIDIA's NVENC hardware encoding (`h264_nvenc`, `hevc_nvenc`) for significantly faster video processing.

## Workflow

1.  A user posts a message with a video clip URL (e.g., from outplayed.tv) in a designated Discord channel.
2.  The bot detects the link, extracts the direct video source, and downloads the clip.
3.  The original message content is cleaned up and used as an overlay text for that specific clip.
4.  The bot processes the video: scaling, adding the text overlay, and normalizing audio. The processed clip is saved temporarily.
5.  When ready to compile, the bot gathers all processed clips.
6.  It creates a continuous background music track by shuffling and merging audio files from your `assets/audio` directory.
7.  It concatenates the video clips and mixes in the background music.
8.  Finally, it generates a dynamic cover image from the final video.
9.  The final video and cover image are saved, ready for upload to platforms like YouTube or Bilibili.

## Prerequisites

*   **Hardware**: An **NVIDIA GPU** that supports NVENC encoding is **required**.
*   **Software**:
    *   Python 3.8+
    *   `ffmpeg` and `ffprobe` installed and accessible in your system's PATH.
    *   `pdm` (for Python package management).
    *   `git` (for cloning the repository).

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-username/Apex-Crispy-Duck.git
    cd Apex-Crispy-Duck
    ```

2.  **Install System Dependencies:**
    You must have `ffmpeg` and `ffprobe` installed.
    *   **On Debian/Ubuntu:**
        ```bash
        sudo apt update && sudo apt install ffmpeg
        ```
    *   **On Windows (using Chocolatey):**
        ```bash
        choco install ffmpeg
        ```
    *   **On macOS (using Homebrew):**
        ```bash
        brew install ffmpeg
        ```
    Ensure you have the latest NVIDIA drivers for your GPU installed.

3.  **Install Python Dependencies:**
    This project uses `pdm` for dependency management.
    ```bash
    pdm install
    ```

4.  **Configure the Bot:**
    Create a `.env` file by copying the example and then fill in your details.
    ```bash
    cp .env.example .env
    ```
    Now, edit the `.env` file. You will need to provide your `DISCORD_BOT_TOKEN` and other configuration details. Check the comments for the usage of each variable.

5.  **Set up Assets:**
    *   **Fonts**: Place the font file you want to use for overlays and thumbnails into the `assets/fonts` directory and update the path in your configuration. You can use `chinese.msyh.ttf` from [Font.download](https://font.download/font/microsoft-yahei).
    *   **Background Music**: Add your `.mp3`, `.m4a`, or `.wav` audio files to the `assets/audio` directory. These will be used to create the background track.

6.  **YouTube API (Optional):**
    If you plan to upload to YouTube, get your `youtube-oauth2.json` credentials by following the official Google guide and place the file in the project root.

7.  **Bilibili API (Optional):**
    If you plan to upload to Bilibili, run `pdm run biliup login` and select a way to login to Bilibili. The credentials will be stored in virtual environments.

## Usage

1.  **Run the Bot:**
    ```bash
    pdm run bot.py # or just `pdm bot`
    ```

2.  **Interact in Discord:**
    Invite the bot to your server. Post messages containing links to your gameplay clips in the channels the bot is configured to listen to. Use the bot's commands to trigger the video compilation process. e.g. Use `/help` to see available commands.

### Commands

Here are the slash commands you can use to interact with the bot:

*   `/bake [hours] [title]`
    *   **Description**: Creates a highlight video from clips uploaded to outplayed.tv posted in the configured channels within a recent time frame. This is the most common command for generating regular compilations.
    *   **`hours`** (optional, default: 8): How many hours back to search for clips.
    *   **`title`** (optional): A custom title for the generated video. If not provided, a title will be generated based on the current date and time.

*   `/excavate [minute_start] [duration] [title]`
    *   **Description**: Creates a highlight video from a specific slice of the entire history of collected clips. This is useful for creating "best of" compilations from a large backlog. The bot maintains a global timeline of all clips it has ever seen.
    *   **`minute_start`** (optional, default: 0): The starting point in minutes on the global timeline.
    *   **`duration`** (optional, default: 10): The total length in minutes for the final video.
    *   **`title`** (optional): A custom title for the generated video.

*   `/customize`
    *   **Description**: Opens a dialog box allowing you to create a video from a custom list of clips. This gives you full control over the content, order, and on-screen text for the final video.
    *   **`Title`**: The title for your video.
    *   **`Content`**: A list of clips, with one clip per line. Each line should contain the outplayed.tv link. You can also add a description and an optional `@user` mention to credit the player.
    *   **`User`**: A default username to apply to all clips that don't have a specific `@user` mention. If left blank, it defaults to your Discord display name.

*   `/help [command]`
    *   **Description**: Shows information about the bot's commands.
    *   **`command`** (optional): If you specify a command name (e.g., `bake`), it will show detailed information for just that command. If left blank, it will list all available commands and their basic descriptions.
