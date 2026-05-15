import argparse
import json
import os
import time
from types import SimpleNamespace

import librosa
import numpy as np
import torch


def pad(x, max_len):
    x_len = x.shape[0]

    if x_len >= max_len:
        return x[:max_len]

    num_repeats = int(max_len / x_len) + 1
    padded_x = np.tile(x, (1, num_repeats))[:, :max_len][0]

    return padded_x


class Nes2NetInference:
    def __init__(
        self,
        model_path=None,
        model_name=None,
        test_mode=None,
    ):
        self.model_path = model_path or os.getenv(
            "MODEL_PATH",
            "./checkpoints/wav2LM_Nes2Net_X.pth"
        )
        self.model_name = model_name or os.getenv(
            "MODEL_NAME",
            "wav2vec2_Nes2Net_X"
        )
        self.test_mode = test_mode or os.getenv(
            "TEST_MODE",
            "4s"
        )

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        self.args = self._build_args()

        start = time.time()
        self.model = self._load_model()

        print(f"[MODEL] loaded={self.model_path}")
        print(f"[MODEL] device={self.device}")
        print(f"[MODEL] load_time_sec={time.time() - start:.2f}")

    def _build_args(self):
        return SimpleNamespace(
            n_output_logits=2,
            model_name=self.model_name,
            dilation=2,
            pool_func="mean",
            SE_ratio=[1],
            Nes_ratio=[8, 8],
            AASIST_scale=32,
            model_path=self.model_path,
            test_mode=self.test_mode,
        )

    def _load_model(self):
        print("[MODEL] importing model class", flush=True)

        if self.model_name == "wav2vec2_AASIST":
            from model_scripts.wav2vec2_AASIST import Model

        elif self.model_name == "wav2vec2_Nes2Net_X":
            from model_scripts.wav2vec2_Nes2Net_X import (
                wav2vec2_Nes2Net_no_Res_w_allT as Model
            )

        else:
            raise ValueError(f"Unsupported model_name: {self.model_name}")

        print("[MODEL] creating model instance", flush=True)
        model = Model(self.args, self.device).to(self.device)

        print(f"[MODEL] loading state_dict from {self.model_path}", flush=True)
        state_dict = torch.load(self.model_path, map_location=self.device)

        print("[MODEL] applying state_dict", flush=True)
        model.load_state_dict(state_dict)

        print("[MODEL] set eval mode", flush=True)
        model.eval()

        return model

    def predict(self, audio_path):
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"audio file not found: {audio_path}")

        audio, _ = librosa.load(
            audio_path,
            sr=16000,
            mono=True
        )

        if self.test_mode == "4s":
            audio = pad(audio, 64000)

        x = torch.tensor(audio).unsqueeze(0).to(self.device)

        start = time.time()

        with torch.no_grad():
            logits = self.model(x)
            prob = torch.softmax(logits, dim=1)[0]

        fake_score = logits[0, 0].item()
        real_score = logits[0, 1].item()

        fake_prob = prob[0].item()
        real_prob = prob[1].item()

        label = "real" if real_prob >= fake_prob else "fake"
        confidence = max(fake_prob, real_prob)

        return {
            "label": label,
            "confidence": confidence,
            "fake_score": fake_score,
            "real_score": real_score,
            "fake_prob": fake_prob,
            "real_prob": real_prob,
            "model_name": self.model_name,
            "model_version": os.getenv("MODEL_VERSION", "v1"),
            "test_mode": self.test_mode,
            "inference_time_sec": round(time.time() - start, 4),
            "class_mapping": {
                "0": "fake",
                "1": "real"
            }
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--audio", required=True)
    parser.add_argument(
        "--model_path",
        default="./checkpoints/wav2LM_Nes2Net_X.pth"
    )
    parser.add_argument(
        "--model_name",
        default="wav2vec2_Nes2Net_X"
    )
    parser.add_argument(
        "--test_mode",
        default="4s",
        choices=["4s", "full"]
    )

    args = parser.parse_args()

    inferencer = Nes2NetInference(
        model_path=args.model_path,
        model_name=args.model_name,
        test_mode=args.test_mode,
    )

    result = inferencer.predict(args.audio)

    print(json.dumps(result, indent=2, ensure_ascii=False))
