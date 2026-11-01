FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
RUN npm install --global pnpm@10.26.2
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/src ./src
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY version.json /build/version.json
RUN pnpm run build

FROM pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime

EXPOSE 28000

ENV TZ=Asia/Shanghai \
    HF_HOME=/app/lora-scripts/huggingface \
    PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && apt-get update \
    && apt-get install --no-install-recommends -y git python3-tk libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/lora-scripts
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --no-deps xformers==0.0.30 --index-url https://download.pytorch.org/whl/cu128 \
    && python -m pip install --no-cache-dir -r requirements.txt

# Package this checkout; local environments, weights and training data stay outside the image.
COPY gui.py version.json LICENSE ./
COPY mikazuki ./mikazuki
COPY scripts ./scripts
COPY docs ./docs
COPY assets/favicon.ico ./assets/favicon.ico
COPY huggingface/accelerate ./huggingface/accelerate
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
RUN mkdir -p config models train output logs huggingface

CMD ["python", "gui.py", "--listen"]
