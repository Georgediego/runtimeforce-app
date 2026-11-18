# BitNet local inference

RuntimeForce can run the Microsoft bitnet.cpp CPU inference server locally. Model files and source are stored under `$XDG_DATA_HOME/runtimeforce/bitnet` (normally `~/.local/share/runtimeforce/bitnet`). Prompts and project context stay on the local machine.

## Linux prerequisites

On Ubuntu 24.04, install the native build tools once:

```bash
sudo bash /usr/share/runtimeforce/install-bitnet-prerequisites.sh
```

For source checkouts, run `sudo apt-get install build-essential cmake git clang-18 python3-dev python3-venv`.

## Install a model

Open **Settings → Providers → Local Models** and use **Download & Build** for one of the available models:

- BitNet-b1.58-2B-4T
- Falcon3-7B-Instruct-1.58bit

RuntimeForce clones the official Microsoft BitNet repository, downloads the selected weights from Hugging Face, and builds the OpenAI-compatible `llama-server`. The first setup can take a long time and requires free disk space for source, build artifacts, and model weights.

## CPU compatibility

RuntimeForce detects CPU architecture, AVX2, NEON, and logical core count. On x86-64 without AVX2 it requests a generic `x86-64` compiler target instead of compiling with `-march=native`; this avoids making AVX2 a build-time assumption. The selected BitNet kernel still has to be supported by the upstream bitnet.cpp build and the model. RuntimeForce does not claim that every legacy x86 CPU is supported.

The local server binds only to `127.0.0.1:8088`. It starts on first use of a selected BitNet model and is stopped when RuntimeForce exits. The API is OpenAI-compatible at `/v1`, including `/v1/models` and streamed `/v1/chat/completions`.

## Storage and logs

- Source/build: `~/.local/share/runtimeforce/bitnet/source`
- Weights: `~/.local/share/runtimeforce/bitnet/models`
- Server/setup log: `~/.local/share/runtimeforce/bitnet/bitnet.log`

Model downloads require a working internet connection. Inference after installation is local.
