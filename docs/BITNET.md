# BitNet external runtime integration

RuntimeForce connects to a separately installed and managed Microsoft BitNet inference server. RuntimeForce does not clone BitNet, compile it, download model weights, or manage the external server process. Model files and inference remain on your computer.

## 1. Install BitNet on Ubuntu

Follow the upstream requirements and compatibility notes: https://github.com/microsoft/BitNet

The following example uses Python 3.12, uv, and the official 2B GGUF model:

```bash
mkdir -p ~/AI
cd ~/AI
git clone --recursive https://github.com/microsoft/BitNet.git
cd BitNet

curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
uv python install 3.12
uv venv --python 3.12 .venv
source .venv/bin/activate

uv pip install --python .venv/bin/python pip
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

hf download microsoft/BitNet-b1.58-2B-4T-gguf \
  --local-dir models/BitNet-b1.58-2B-4T

python setup_env.py \
  --model-dir models/BitNet-b1.58-2B-4T \
  --quant-type i2_s
```

Use a model and quantization supported by the current upstream BitNet build. The model ID exposed by the server is discovered automatically by RuntimeForce; it is not hard-coded.

## 2. Run the OpenAI-compatible server

For the example model above:

```bash
cd ~/AI/BitNet
source .venv/bin/activate

python run_inference_server.py \
  -m models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf \
  -t 4 -c 1024 -n 256 \
  --host 127.0.0.1 --port 8080
```

The server must expose:

- `GET /v1/models`
- `POST /v1/chat/completions` with streaming SSE responses

Check that the model has finished loading:

```bash
curl http://127.0.0.1:8080/v1/models
```

A temporary `503 Loading model` response means the model is still loading. Wait until the endpoint returns the model list.

## 3. Start BitNet automatically with systemd

Create a system service. The command uses your current Linux username and home directory:

```bash
BITNET_DIR="$HOME/AI/BitNet"

sudo tee /etc/systemd/system/bitnet.service >/dev/null <<EOF
[Unit]
Description=BitNet Local AI Runtime
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$BITNET_DIR
ExecStart=$BITNET_DIR/.venv/bin/python $BITNET_DIR/run_inference_server.py -m $BITNET_DIR/models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf -t 4 -c 1024 -n 256 --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now bitnet.service
systemctl status bitnet.service --no-pager
```

Useful diagnostics:

```bash
sudo journalctl -u bitnet.service -n 80 --no-pager
curl -s http://127.0.0.1:8080/v1/models
```

Keep the server bound to `127.0.0.1` unless remote access is intentionally secured.

## 4. Connect in RuntimeForce

Open **Settings → Providers → Local Models → Add Local Engine** and enter:

- Provider Name: `bitnet`
- Base URL: `http://127.0.0.1:8080`

Select **Discover & Add**. RuntimeForce queries `/v1/models` and adds the models returned by the external server. Select the discovered `bitnet/<model-id>` entry in the model picker.

## 5. Compatibility and performance

The external server must implement the OpenAI-compatible models endpoint and streamed chat-completions endpoint. RuntimeForce forwards tool definitions when supplied; actual tool-calling support depends on the BitNet server and selected model.

Model compatibility, tokenizer metadata, CPU instruction support, available RAM and quantization affect output quality and speed. If the BitNet log reports that generation quality will be degraded, verify that the GGUF and tokenizer metadata match the upstream runtime. CPU-only inference can be slow on older processors.

RuntimeForce stores the local server URL in its encrypted local settings. Prompts and project context are sent directly to the local BitNet server, not to the RuntimeForce SaaS.
