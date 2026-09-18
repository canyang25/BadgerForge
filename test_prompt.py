# pip install openai
from openai import OpenAI

client = OpenAI(base_url="https://llm-gw01.doit.wisc.edu/v1", timeout=300)

resp = client.chat.completions.create(
    model="qwen3.8-27b",
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "Explain PCA in two sentences."},
    ],
    reasoning_effort="medium",
)
print(resp.choices[0].message.content)