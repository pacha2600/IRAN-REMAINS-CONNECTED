"""Installer smoke test; use a file to avoid PowerShell quoting pitfalls."""
from iran_proxy_monitor._vendor import yaml
import tkinter

parsed = yaml.safe_load("x: 1")
if parsed != {"x": 1}:
    raise RuntimeError("Bundled YAML parser returned unexpected data")
print("Bundled YAML and Tkinter available")
