import ast
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page_script():
    tree = ast.parse((ROOT / "relay/bin/tunnel-status-web.py").read_text())
    page = next(
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "PAGE" for target in node.targets)
    )
    return page.split("<script>", 1)[1].split("</script>", 1)[0]


class SourceTests(unittest.TestCase):
    def test_embedded_python_in_shell_helpers_compiles(self):
        for directory in ("campus", "relay", "scripts"):
            for path in (ROOT / directory).rglob("*.sh"):
                for marker, body in re.findall(r"<<'([A-Z]+)'\n(.*?)\n\1", path.read_text(), re.S):
                    with self.subTest(path=path, marker=marker):
                        compile(body, str(path), "exec")

    def test_documentation_relative_links_exist(self):
        files = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *(ROOT / "docs").glob("*.md")]
        for path in files:
            for link in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if "://" in link or link.startswith("#"):
                    continue
                with self.subTest(path=path, link=link):
                    self.assertTrue((path.parent / link.split("#")[0]).exists())

    @unittest.skipUnless(shutil.which("node"), "Node is needed for browser-script checks")
    def test_browser_script_syntax(self):
        result = subprocess.run(
            ["node", "--check"], input=page_script(), text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node is needed for browser-script checks")
    def test_stale_status_clears_live_indicators(self):
        harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
function element() {
  const classes = new Set();
  return {
    textContent: '', className: '', children: [],
    classList: {
      toggle(c, on) { on ? classes.add(c) : classes.delete(c); },
      remove(c) { classes.delete(c); },
      contains(c) { return classes.has(c); }
    },
    replaceChildren(...children) { this.children = children; }
  };
}
const context = vm.createContext({
  document: {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement() { return element(); }
  },
  fetch: async () => ({ok: true, json: async () => ({tunnel_up: true, checked: 'test'})}),
  AbortController,
  setTimeout() { return 1; },
  clearTimeout() {}
});
"""
        harness += "\nvm.runInContext(" + repr(page_script()) + ", context);\n"
        harness += r"""
setImmediate(() => {
  assert.equal(elements.get('word').textContent, 'up');
  assert.equal(elements.get('n-campus').classList.contains('reachable'), true);
  vm.runInContext('paint({tunnel_up:null,stale:true})', context);
  assert.equal(elements.get('word').textContent, '—');
  assert.equal(elements.get('word').className, '');
  assert.equal(elements.get('n-campus').classList.contains('reachable'), false);
  assert.equal(elements.get('n-relay').classList.contains('on'), false);
});
"""
        result = subprocess.run(["node"], input=harness, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
