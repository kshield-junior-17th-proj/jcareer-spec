#!/usr/bin/env python3
"""Render a self-contained animated SVG to inspected PNG, GIF, and H.264 MP4."""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def chrome_binary() -> str:
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise FileNotFoundError("Chrome was not found; set up Chrome before rendering media.")


def capture_frames(svg_path: Path, width: int, height: int, fps: int, seconds: int) -> list[Image.Image]:
    options = Options()
    options.binary_location = chrome_binary()
    for argument in (
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
    ):
        options.add_argument(argument)

    driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        driver.get(svg_path.resolve().as_uri())
        driver.execute_script(
            "document.documentElement.pauseAnimations();"
            "document.getAnimations().forEach((animation) => animation.pause());"
        )
        frames: list[Image.Image] = []
        for frame_index in range(fps * seconds):
            seconds_elapsed = frame_index / fps
            driver.execute_script(
                "document.documentElement.setCurrentTime(arguments[0]);"
                "document.getAnimations().forEach((animation) => {"
                "animation.currentTime = arguments[0] * 1000;"
                "});",
                seconds_elapsed,
            )
            frame = Image.open(io.BytesIO(driver.get_screenshot_as_png())).convert("RGB")
            if frame.size != (width, height):
                raise RuntimeError(f"unexpected screenshot size: {frame.size}")
            frames.append(frame)
        return frames
    finally:
        driver.quit()


def write_gif(frames: list[Image.Image], output: Path, fps: int, width: int) -> None:
    source_width, source_height = frames[0].size
    height = round(source_height * width / source_width)
    resized = [
        frame.resize((width, height), Image.Resampling.LANCZOS).quantize(
            colors=256,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.FLOYDSTEINBERG,
        )
        for frame in frames
    ]
    resized[0].save(
        output,
        save_all=True,
        append_images=resized[1:],
        duration=round(1000 / fps),
        loop=0,
        disposal=2,
        optimize=False,
    )


def write_mp4(frames: list[Image.Image], output: Path, fps: int) -> None:
    with tempfile.TemporaryDirectory(prefix="jcareer-arch-frames-") as temporary_directory:
        frame_directory = Path(temporary_directory)
        for index, frame in enumerate(frames):
            frame.save(frame_directory / f"frame-{index:04d}.png", compress_level=2)
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_directory / "frame-%04d.png"),
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(output),
        ]
        subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--output-stem", type=Path)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=4)
    parser.add_argument("--still-at", type=float, default=1.4)
    parser.add_argument("--gif-width", type=int, default=1200)
    arguments = parser.parse_args()

    if arguments.fps < 1 or arguments.seconds < 1:
        parser.error("fps and seconds must be positive")
    spec = json.loads(arguments.spec.read_text(encoding="utf-8"))
    width = int(spec["canvas"]["w"])
    height = int(spec["canvas"]["h"])
    output_stem = arguments.output_stem or arguments.svg.with_suffix("")
    output_stem.parent.mkdir(parents=True, exist_ok=True)

    frames = capture_frames(
        arguments.svg,
        width=width,
        height=height,
        fps=arguments.fps,
        seconds=arguments.seconds,
    )
    still_index = min(len(frames) - 1, max(0, round(arguments.still_at * arguments.fps)))
    png_path = output_stem.with_suffix(".png")
    gif_path = output_stem.with_suffix(".gif")
    mp4_path = output_stem.with_suffix(".mp4")
    frames[still_index].save(png_path, optimize=True)
    write_gif(frames, gif_path, arguments.fps, arguments.gif_width)
    write_mp4(frames, mp4_path, arguments.fps)
    print(
        f"rendered {len(frames)} frames at {arguments.fps} fps: "
        f"{png_path.name}, {gif_path.name}, {mp4_path.name}"
    )


if __name__ == "__main__":
    main()
