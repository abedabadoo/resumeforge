# ResumeForge for Intel Mac — preview build

This is a native desktop application for **Intel (x86_64) Macs running macOS 13 or newer**. It includes the Python runtime, native Qt interface, PDF preview/export, Liberation Sans fonts, and a fictional starter profile.

## Install

- Download `ResumeForge-macOS-Intel.dmg` (or the ZIP), open it, and drag **ResumeForge.app** into Applications.
- Double-click **ResumeForge** in Applications. This is a desktop app; you do not need Terminal, Python, or a browser.
- The preview is **not Apple Developer ID signed or notarized**. If macOS blocks the launch, use Finder's **Open** option or go to **System Settings → Privacy & Security → Open Anyway** after attempting to open it. Only override the warning for downloads you trust.
- Your data is stored at `~/Library/Application Support/ResumeForge/workspace`.

The download **does not include Qwen, Ollama, or another AI model**. ResumeForge runs with its built-in examples without a model. For AI generation, install/configure a local Ollama model or the supported Intel laptop runtime separately in **Model settings**.

The package was assembled and smoke-tested on a GitHub-hosted Intel Mac. Apple notarization and testing on every Intel Mac model are not included in this preview.
