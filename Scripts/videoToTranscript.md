# Transcribe an MP4 with OpenAI Whisper (Linux)

This guide resets your virtual environment, installs the correct dependencies, and runs `transcript.py` to produce a text transcript.

## 0) Quick reset: uninstall everything that was installed in this venv

If you installed packages inside a virtual environment (your prompt shows `(venv)`), the cleanest uninstall is deleting and recreating the venv.

From the folder that contains the `venv/` directory:

```bash
deactivate  # if you're currently in the venv
rm -rf venv
python3 -m venv venv
source venv/bin/activate
python -m pip install -U pip
```

### Alternative: uninstall packages without deleting the venv (less recommended)

```bash
python -m pip freeze > /tmp/venv_packages.txt
python -m pip uninstall -y -r /tmp/venv_packages.txt
```

## 1) System dependency: install ffmpeg

Whisper uses `ffmpeg` to read and convert audio.

```bash
sudo apt update
sudo apt install -y ffmpeg
ffmpeg -version
```

## 2) Python dependency: install the correct Whisper package

Important: do **not** install the PyPI package named `whisper` (it is not OpenAI Whisper).  
You want **`openai-whisper`**.

Inside the venv:

```bash
python -m pip uninstall -y whisper
python -m pip install -U openai-whisper
```

Verify Python is importing the right library:

```bash
python -c "import whisper; print('whisper:', whisper.__file__); print('load_model:', hasattr(whisper,'load_model'))"
```

You should see `load_model: True`.

### If `load_model` is still False

You may have a local file/folder shadowing the library (for example `./whisper.py` or `./whisper/`).

```bash
ls -la | grep -i whisper
```

If you see a local `whisper.py` or `whisper/`, rename it and retry.

## 3) Confirm your script is present

Your working directory should contain:

- `transcript.py`
- your video file, for example `Flow12.MP4`

```bash
ls -la
```

## 4) Run the script

Basic usage:

```bash
python transcript.py Flow12.MP4
```

With an explicit output file:

```bash
python transcript.py Flow12.MP4 Flow12.txt
```

The transcript will be saved to the output file you specify.

## 5) Common errors and fixes

### `FileNotFoundError: ffmpeg`

Install ffmpeg:

```bash
sudo apt install -y ffmpeg
```

### `AttributeError: module 'whisper' has no attribute 'load_model'`

You installed the wrong `whisper` package or something is shadowing the import.

Fix:

```bash
python -m pip uninstall -y whisper
python -m pip install -U openai-whisper
python -c "import whisper; print(whisper.__file__); print(hasattr(whisper,'load_model'))"
```

## 6) Optional improvements to `transcript.py`

Show ffmpeg errors instead of hiding them:

- Replace the `subprocess.run(...)` line with:

```python
subprocess.run(command, check=True)
```

Fail fast if ffmpeg is missing:

```python
import shutil, sys
if shutil.which("ffmpeg") is None:
    sys.exit("ffmpeg not found. Install it with: sudo apt install -y ffmpeg")
```
