import urllib.request
import json
req = urllib.request.Request(
    'https://raw.githubusercontent.com/containers/podman/main/docs/source/markdown/podman-machine-init.1.md',
    headers={'User-Agent': 'Mozilla/5.0'}
)
try:
    with urllib.request.urlopen(req) as response:
        content = response.read().decode('utf-8')
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'rosetta' in line.lower():
                print('\n'.join(lines[max(0, i-2):min(len(lines), i+5)]))
except Exception as e:
    print(f"Error: {e}")
