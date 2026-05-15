FROM python:3.10-bullseye

WORKDIR /workspace

ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_VISIBLE_DEVICES=""
ENV PYTHONUNBUFFERED=1
ENV WORKER_MODE=mock
ENV MODEL_DIR=/models
ENV MODEL_PATH=/models/wav2LM_Nes2Net_X.pth

RUN apt update && apt install -y \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "pip<24.1" setuptools wheel

COPY requirements.txt /workspace/requirements.txt

RUN pip install torch==1.13.1 torchaudio==0.13.1 \
    --index-url https://download.pytorch.org/whl/cpu

RUN grep -v "^torch==" requirements.txt | grep -v "^torchaudio==" > requirements-no-torch.txt && \
    pip install -r requirements-no-torch.txt

COPY inference.py /workspace/inference.py
COPY worker.py /workspace/worker.py
COPY config.py /workspace/config.py
COPY model_downloader.py /workspace/model_downloader.py
COPY s3_client.py /workspace/s3_client.py
COPY sqs_client.py /workspace/sqs_client.py
COPY db_client.py /workspace/db_client.py
COPY healthcheck.py /workspace/healthcheck.py
COPY model_scripts /workspace/model_scripts
COPY fairseq_src /workspace/fairseq_src
COPY data_utils_SSL.py /workspace/data_utils_SSL.py
COPY RawBoost.py /workspace/RawBoost.py

RUN cd /workspace/fairseq_src && \
    pip install --editable ./

CMD ["python", "-u", "worker.py"]
