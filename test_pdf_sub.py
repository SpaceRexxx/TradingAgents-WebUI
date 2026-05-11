import subprocess
import sys

script = '''
import sys
from playwright.sync_api import sync_playwright

html = "<html><body><h1>Test PDF</h1></body></html>"
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        pdf_bytes = page.pdf(format="A4", margin={"top": "1.5cm", "bottom": "1.5cm", "left": "1.5cm", "right": "1.5cm"})
        browser.close()
        sys.stdout.buffer.write(b"SUCCESS")
except Exception as e:
    sys.stderr.write(str(e))
    sys.exit(1)
'''
proc = subprocess.run([sys.executable, "-c", script], capture_output=True)
if proc.returncode != 0:
    print("ERROR:", proc.stderr.decode('utf-8'))
else:
    print("OUT:", proc.stdout.decode('utf-8'))
