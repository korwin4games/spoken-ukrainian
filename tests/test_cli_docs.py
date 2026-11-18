"""Ensure both entry-point guides contain the same runnable examples."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CLIDocsTests(unittest.TestCase):
    def test_guide_links_fences_commands_and_parity(self):
        examples = []
        for name in ("CLI.md", "CLI.uk.md"):
            path = ROOT / "docs" / name
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("```"), text.count("```bash") * 2)
            blocks = re.findall(r"```bash\n(.*?)\n```", text, re.S)
            examples.append(blocks)
            for block in blocks:
                subprocess.run(["bash", "-n"], input=block, text=True, check=True)
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if "://" not in link and not link.startswith("#"):
                    self.assertTrue((path.parent / link.split("#")[0]).is_file(), link)
            mentioned = set(re.findall(r"uv run --locked python (tools/\w+\.py)", text))
            available = {str(f.relative_to(ROOT)) for f in (ROOT / "tools").glob("*.py")
                         if 'if __name__ == "__main__":' in f.read_text(encoding="utf-8")
                         or "if __name__ == '__main__':" in f.read_text(encoding="utf-8")}
            self.assertEqual(mentioned, available)
        self.assertEqual(*examples)
