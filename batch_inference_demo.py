import argparse
import glob
import os
import time

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


def load_model(args, device):
    if args.model_name == "wav2vec2_AASIST":
        from model_scripts.wav2vec2_AASIST import Model
    elif args.model_name == "wav2vec2_Nes2Net_X":
        from model_scripts.wav2vec2_Nes2Net_X import wav2vec2_Nes2Net_no_Res_w_allT as Model
    else:
        raise ValueError(f"Unsupported model_name: {args.model_name}")

    model = Model(args, device).to(device)
    model.load_state_dict(torch.load(args.model_path, map_location=device))
    model.eval()

    return model


def predict_one(model, wav_path, device, test_mode):
    audio, _ = librosa.load(wav_path, sr=16000, mono=True)

    if test_mode == "4s":
        audio = pad(audio, 64000)

    x = torch.tensor(audio).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(x)
        prob = torch.softmax(logits, dim=1)[0]

    fake_score = logits[0, 0].item()
    real_score = logits[0, 1].item()

    fake_prob = prob[0].item()
    real_prob = prob[1].item()

    label = "real" if real_prob >= fake_prob else "fake"
    confidence = max(fake_prob, real_prob)

    return {
        "file": wav_path,
        "label": label,
        "confidence": confidence,
        "fake_score": fake_score,
        "real_score": real_score,
        "fake_prob": fake_prob,
        "real_prob": real_prob,
    }


def main(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    start_load = time.time()
    model = load_model(args, device)
    print(f"Model loaded: {args.model_path}")
    print(f"Model load time: {time.time() - start_load:.2f}s")

    files = sorted(glob.glob(os.path.join(args.input_dir, "*")))
    files = [f for f in files if f.lower().endswith((".wav", ".flac", ".mp3", ".m4a"))]

    print(f"Total files: {len(files)}")

    start_infer = time.time()

    for wav_path in files:
        item_start = time.time()
        result = predict_one(model, wav_path, device, args.test_mode)

        print(
            f"{os.path.basename(result['file'])}, "
            f"result={result['label']}, "
            f"confidence={result['confidence']:.6f}, "
            f"fake_prob={result['fake_prob']:.6f}, "
            f"real_prob={result['real_prob']:.6f}, "
            f"time={time.time() - item_start:.2f}s"
        )

    print(f"Total inference time: {time.time() - start_infer:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--n_output_logits", type=int, default=2)
    parser.add_argument("--model_name", type=str, required=True, choices=["wav2vec2_AASIST", "wav2vec2_Nes2Net_X"])
    parser.add_argument("--dilation", type=int, default=2)
    parser.add_argument("--pool_func", type=str, default="mean", choices=["mean", "ASTP"])
    parser.add_argument("--SE_ratio", type=int, nargs="+", default=[1])
    parser.add_argument("--Nes_ratio", type=int, nargs="+", default=[8, 8])
    parser.add_argument("--AASIST_scale", type=int, default=32, choices=[24, 32, 40, 48, 56, 64, 96])

    parser.add_argument("--input_dir", type=str, required=True)
    parser.add_argument("--model_path", type=str, required=True)
    parser.add_argument("--test_mode", type=str, default="4s", choices=["4s", "full"])

    args = parser.parse_args()
    main(args)