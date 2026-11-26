# Qwen3.8-27B Model Card Summary

Extracted from the [NVIDIA NGC Model Card](https://catalog.ngc.nvidia.com/orgs/nim/qwen/models/qwen3.8-27b).

---

## 1. Key Details

- **Model Name:** Qwen3.8-27B
- **Publisher / Developer:** Qwen
- **Hosting / Catalog:** NVIDIA NIM / NGC
- **Release Date:** August 14, 2026 (via Hugging Face)
- **License & Terms:**
  - **Governing Download Terms:** [NVIDIA Open Model Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement/)
  - **Base License:** Apache 2.0 (commercial and non-commercial use permitted)
- **Deployment Geography:** Global
- **Available Checksums / Quantizations:**
  - `nvfp4-1.0` (Latest, compressed size: ~20.44 GB)
  - `bf16-1.0` (Source revision: `1d4bf0f`)
  - `fp8-1.0` (Source revision: `017b9c7`)

---

## 2. Model Architecture & Specifications

- **Architecture Type:** Transformer
- **Network Architecture Class:** `Qwen3_5ForConditionalGeneration`
- **Total Parameters:** 27 Billion (Dense)
- **Layer Count:** 64 layers
- **Hidden Dimension:** 5,120
- **Intermediate Dimension (FFN):** 17,408
- **Structural Layout:** Hybrid architecture arranged in **16 repeated groups**:
  - **Per Group:** 3 Gated DeltaNet + FFN units, followed by 1 Gated Attention + FFN unit.
- **Gated DeltaNet Configuration:**
  - Value Heads: 48
  - Query / Key Heads: 16
  - Head Dimension: 128
- **Gated Attention Configuration:**
  - Query Heads: 24
  - Key / Value Heads: 4
  - Head Dimension: 256
  - Rotary Position Embedding (RoPE) Dimension: 64
- **Generation Mechanism:** Multi-token prediction

---

## 3. Context Window Size

- **Native Context Window:** **262,144 tokens** (256K tokens)
- **Extended Context Window:** Scalable up to **1,000,000 tokens** (1M tokens)

---

## 4. Capabilities & Features

- **Multimodal Understanding:** Native processing of text, images, and video (MP4/WebM).
- **Reasoning & Configurable Thinking:**
  - Integrated "thinking" mode enabled by default (can be toggled off).
  - Configurable reasoning effort levels: `xhigh`, `medium`, and `low`.
  - Thinking process state can be preserved across conversation turns.
- **Coding & Agentic Workflows:**
  - High performance on coding agent tasks and multi-step agent execution.
  - Native tool calling and function calling support.
- **Document & Visual Reasoning:** Document understanding, chart/visual data extraction, and video sequence comprehension.
- **Professional & Research Workflows:** Long-context comprehension and mathematical reasoning.

---

## 5. Input and Output Specifications

### Inputs
- **Input Modalities:** Text, Image, Video
- **Input Formats:** String (text), RGB (images), MP4 / WebM (video)
- **Dimensionality:** 1D, 2D, and 3D tensors

### Outputs
- **Output Modalities:** Text (natural language and code)
- **Output Format:** String / 1D token sequences
- **Sampling Controls:** Supports standard configurable sampling and output-length parameters

---

## 6. Software & Hardware Compatibility

- **Runtime / Serving Engine:** SGLang
- **Supported Operating Systems:** Linux
- **Compatible Hardware Microarchitectures:**
  - **NVIDIA Blackwell:** B200 Tensor Core GPU, RTX PRO 6000D
  - **NVIDIA Hopper:** H200 Tensor Core GPU, H20 Tensor Core GPU
- **API Support:** Industry-standard OpenAI-compatible API via NVIDIA NIM
