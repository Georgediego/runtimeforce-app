# BitNet external runtime integration

RuntimeForce connects to a separately installed and managed BitNet inference server. RuntimeForce does not install BitNet, clone its source, compile it, download model weights, or stop the external process.

## 1. Run BitNet independently

Install and configure Microsoft's BitNet runtime using its official instructions: https://github.com/microsoft/BitNet

Start its OpenAI-compatible HTTP server. The server must expose:

- `GET /v1/models`
- `POST /v1/chat/completions` with streaming SSE responses

Keep the server bound to localhost unless remote access is intentionally secured. The example URL below assumes port 8080; use the actual address and port configured in your BitNet runtime.

## 2. Connect in RuntimeForce

Open **Settings → Providers → Local Models → Add Local Engine** and enter:

- Provider Name: `bitnet`
- Base URL: `http://localhost:8080` (replace with your server address)

Select **Discover & Add**. RuntimeForce queries `/v1/models` and adds every model returned by the external server. There is no hard-coded two-model catalog.

## 3. Use models

Select discovered `bitnet/<model-id>` models in the model picker. RuntimeForce sends chat requests to the configured server's `/v1/chat/completions` endpoint. Model installation, lifecycle, storage, CPU/GPU configuration, and updates remain the responsibility of the external BitNet runtime.

## Compatibility

The external server must implement the OpenAI-compatible models endpoint and streamed chat-completions endpoint. Tool calling is forwarded when supplied by RuntimeForce; actual support depends on the selected BitNet server and model.
