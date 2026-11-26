#!/usr/bin/env python3
"""Estimate a model's reported VRAM the same way the approved-model table does.

    python scripts/estimate_vram.py Qwen/Qwen2.5-Coder-32B-Instruct-AWQ

Reported VRAM = published checkpoint size (weights, as released)
              + KV cache for a 16k context at fp16, single batch
              + 2 GB headroom (activations, runner overhead)

Weights are taken from the actual file sizes on the HuggingFace Hub, so
quantized checkpoints (AWQ, GPTQ, FP8, ...) are handled automatically —
no parameter counting or bits math. KV cache comes from the model's
config.json. Needs network access to huggingface.co; no GPU, no downloads
beyond two small JSON requests.

This is a sanity check, not a measurement. If your number lands within a
few GB of an existing approved-model entry, the table is right. If you're
proposing a new row, include this script's output in your Kaggle
Discussion post.

Don't compare against nvidia-smi — most serving stacks preallocate a
large memory pool at startup, so the reading reflects your GPU, not the
model.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

HUB = "https://huggingface.co"
KV_CONTEXT = 16384          # tokens, per the approved-model table
KV_BYTES_PER_ELEM = 2       # fp16
OVERHEAD_GB = 2.0


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "estimate-vram"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def weights_bytes(repo: str) -> int:
    """Sum the sizes of the checkpoint's weight files on the Hub."""
    info = fetch_json(f"{HUB}/api/models/{repo}?blobs=true")
    sizes = {}
    for f in info.get("siblings", []):
        name, size = f.get("rfilename", ""), f.get("size")
        if size and name.endswith((".safetensors", ".bin", ".gguf")):
            sizes[name] = size
    if not sizes:
        raise SystemExit(f"No weight files found in {repo} — is the repo id right?")
    # Prefer safetensors when a repo ships both formats
    st = {n: s for n, s in sizes.items() if n.endswith(".safetensors")}
    return sum((st or sizes).values())


def kv_cache_bytes(repo: str) -> tuple[int, dict]:
    cfg = fetch_json(f"{HUB}/{repo}/resolve/main/config.json")
    # VL / multimodal checkpoints nest the language model's config
    text = cfg.get("text_config", cfg)
    layers = text["num_hidden_layers"]
    kv_heads = text.get("num_key_value_heads") or text["num_attention_heads"]
    head_dim = text.get("head_dim") or text["hidden_size"] // text["num_attention_heads"]
    per_token = layers * kv_heads * head_dim * 2 * KV_BYTES_PER_ELEM  # 2 = K and V
    detail = {"layers": layers, "kv_heads": kv_heads, "head_dim": head_dim}
    return per_token * KV_CONTEXT, detail


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", help="HuggingFace repo id, e.g. Qwen/Qwen2.5-Coder-32B-Instruct-AWQ")
    repo = parser.parse_args().repo

    try:
        w = weights_bytes(repo)
        kv, detail = kv_cache_bytes(repo)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} fetching {e.url} — private/gated repo or typo?")

    w_gb, kv_gb = w / 1e9, kv / 1e9
    total = w_gb + kv_gb + OVERHEAD_GB
    print(f"{repo}")
    print(f"  weights (published checkpoint): {w_gb:6.1f} GB")
    print(f"  KV cache @ {KV_CONTEXT} tokens, fp16:  {kv_gb:6.1f} GB"
          f"  ({detail['layers']} layers x {detail['kv_heads']} KV heads x {detail['head_dim']} head_dim)")
    print(f"  headroom:                       {OVERHEAD_GB:6.1f} GB")
    print(f"  reported VRAM estimate:         {total:6.1f} GB")
    print(f"  48 GB limit:                    {'OK' if total <= 48 else 'OVER'}")


if __name__ == "__main__":
    main()
