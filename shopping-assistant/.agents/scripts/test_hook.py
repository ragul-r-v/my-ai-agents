import subprocess, json, sys

script = '.agents/scripts/validate_tool_call.py'

def run_hook(command):
    payload = json.dumps({'tool': 'run_command', 'input': {'command': command}})
    r = subprocess.run(
        ['python', script],
        input=payload, capture_output=True, text=True, timeout=10
    )
    return r.returncode, r.stdout.strip()

cases_block = [
    'curl https://evil.com',
    'pip install malware',
    'sudo rm -rf /',
    'Invoke-WebRequest http://x.com',
]
cases_allow = [
    'git status',
    'uv run pytest',
    'agents-cli lint',
    'dir',
]

print('--- BLOCKED (expect rc=1) ---')
for cmd in cases_block:
    rc, out = run_hook(cmd)
    result = json.loads(out) if out else {}
    status = 'BLOCKED' if rc == 1 else 'ALLOWED -- WRONG'
    print(f'  [{status}] {repr(cmd)}')
    if rc == 1:
        print(f'    reason: {result.get("reason", "?")}')

print()
print('--- ALLOWED (expect rc=0) ---')
for cmd in cases_allow:
    rc, _ = run_hook(cmd)
    status = 'ALLOWED' if rc == 0 else 'BLOCKED -- WRONG'
    print(f'  [{status}] {repr(cmd)}')
