"""Plumbline setup: asks for each key and file, saves them, then tests every connection.

Run from backend/:   .venv/bin/python setup_keys.py
Press Enter to keep what's already saved or to skip something you don't have yet. Run it again any time.
Secrets are typed hidden and saved only to backend/.env (gitignored). Nothing is printed back.
"""
from __future__ import annotations

import getpass
import os
import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
ENV = HERE / ".env"
DATA = HERE / "app" / "data"
DOWNLOADS = Path.home() / "Downloads"

B, D, G, R, Y, X = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"

# (env name, label, where to find it, secret?)
STEPS = [
    ("Step 1 · CoStar track keys", "In the track Discord, type /costar-keys and enter a team name. Keep that card open.", [
        ("MATTERPORT_API_KEY", "Matterport API key", "Matterport card → \"API key\"", True),
        ("MATTERPORT_API_TOKEN", "Matterport API token", "Matterport card → \"API token\" (the secret half)", True),
        ("VITE_MATTERPORT_SDK_KEY", "Matterport SDK key", "Matterport card → \"SDK key\"", False),
        ("VEXCEL_API_KEY", "Vexcel API key", "Vexcel card → \"api_key\"", True),
        ("COSTAR_KIT_URL", "CoStar kit download link", "CoStar card → the kit's download link (or leave blank and use a zip below)", False),
        ("COSTAR_ZIP_PASSWORD", "CoStar zip password", "CoStar card → \"Zip password\"", True),
    ]),
    ("Step 2 · AI and data accounts", "Skip any you don't have yet.", [
        ("ANTHROPIC_API_KEY", "Anthropic API key", "console.anthropic.com → API keys", True),
        ("LANGSMITH_API_KEY", "LangSmith API key", "smith.langchain.com → Settings → API keys", True),
        ("TIGER_DATABASE_URL", "Tiger Cloud connection string", "console.cloud.timescale.com → your service → Connect (starts with postgres://)", True),
    ]),
]

ORDER = ["MATTERPORT_API_KEY", "MATTERPORT_API_TOKEN", "VITE_MATTERPORT_SDK_KEY", "MODELS_INDEX_CSV", "VEXCEL_API_KEY",
         "COSTAR_KIT_URL", "COSTAR_KIT_ZIP", "COSTAR_ZIP_PASSWORD", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY", "TIGER_DATABASE_URL"]


def ask(label: str, hint: str, current: str | None, secret: bool) -> str | None:
    state = f"{G}saved{X}" if current else f"{D}not set{X}"
    print(f"\n  {B}{label}{X}  [{state}]\n  {D}{hint}{X}")
    prompt = "  Paste it (Enter to keep): " if current else "  Paste it (Enter to skip): "
    value = (getpass.getpass(prompt) if secret else input(prompt)).strip().strip('"').strip("'")
    return value or current


def find_file(name: str | None) -> Path | None:
    if not name:
        return None
    for p in (DATA / name, DOWNLOADS / name, *DOWNLOADS.glob(f"**/{name}")):
        if p.is_file():
            return p
    return None


def ask_file(label: str, name: str | None, hint: str) -> Path | None:
    found = find_file(name)
    print(f"\n  {B}{label}{X}\n  {D}{hint}{X}")
    if found:
        print(f"  Found: {found}")
    raw = input("  Path to the file (Enter to use the one found, or skip): " if found else "  Path to the file, or drag it here (Enter to skip): ")
    raw = raw.strip().strip('"').strip("'").replace("\\ ", " ")
    path = Path(raw).expanduser() if raw else found
    if path and not path.is_file():
        print(f"  {R}No file at {path}; skipped.{X}")
        return None
    return path


def save(values: dict[str, str | None]) -> None:
    lines = ["# Written by setup_keys.py. Gitignored; never commit this file."]
    lines += [f'{k}="{v}"' for k in ORDER if (v := values.get(k))]
    lines += [f'{k}="{v}"' for k, v in values.items() if k not in ORDER and v]
    ENV.write_text("\n".join(lines) + "\n")
    os.chmod(ENV, 0o600)


def check_all() -> None:
    print(f"\n{B}Testing connections{X}")
    for k, v in dotenv_values(ENV).items():  # make freshly saved values visible to the app modules
        if v:
            os.environ[k] = v
    from app.settings import Settings
    s = Settings()

    def report(name, fn):
        try:
            msg = fn()
            print(f"  {G}✓{X} {name}: {msg}")
        except Exception as e:  # show the plain reason, never the key
            print(f"  {R}✗{X} {name}: {str(e)[:160]}")

    def skip(name, why):
        print(f"  {Y}–{X} {name}: {why}")

    if s.matterport_api_key and s.matterport_api_token:
        from app.integrations.matterport import MatterportClient
        report("Matterport", lambda: (lambda f: f"key works, {f['modelCountSummary']:,} models in '{f['name']}'")(
            MatterportClient(s.matterport_api_key, s.matterport_api_token).key_check()))
    else:
        skip("Matterport", "key or token not set")

    if s.models_index_csv.exists():
        from app.integrations.matterport import ModelIndex
        report("models_index.csv", lambda: f"{len(ModelIndex.load(s.models_index_csv).models):,} models with a location")
    else:
        skip("models_index.csv", "file not added")

    if s.vexcel_api_key:
        from app.integrations.vexcel import VexcelClient
        report("Vexcel", lambda: f"aerial image received ({len(VexcelClient(s.vexcel_api_key).ortho(29.7604, -95.3698, 40, 400)) // 1024} KB, downtown Houston)")
    else:
        skip("Vexcel", "key not set")

    if s.costar_zip_password and (s.costar_kit_url or s.costar_kit_zip):
        from app.integrations.costar import CostarKit
        report("CoStar kit", lambda: f"opened, {len(CostarKit.open(path=s.costar_kit_zip, url=s.costar_kit_url, password=s.costar_zip_password).files())} files inside")
    else:
        skip("CoStar kit", "link/zip or password not set")

    if s.anthropic_api_key:
        import httpx
        report("Anthropic", lambda: (lambda r: "key works" if r.status_code == 200 else (_ for _ in ()).throw(RuntimeError(f"HTTP {r.status_code}")))(
            httpx.get("https://api.anthropic.com/v1/models", headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"}, timeout=20)))
    else:
        skip("Anthropic", "key not set")

    for name, val in (("LangSmith", s.langsmith_api_key), ("Tiger Cloud", s.tiger_database_url)):
        print(f"  {G}✓{X} {name}: saved (tested when that feature is built)") if val else skip(name, "not set")


def main() -> None:
    os.chdir(HERE)
    sys.path.insert(0, str(HERE))
    values: dict[str, str | None] = dict(dotenv_values(ENV)) if ENV.exists() else {}
    print(f"{B}Plumbline setup{X}\n{D}Press Enter to keep a saved value or skip one you don't have yet. Typing is hidden for secrets.{X}")

    for title, intro, fields in STEPS:
        print(f"\n{B}{title}{X}\n  {intro}")
        for env, label, hint, secret in fields:
            values[env] = ask(label, hint, values.get(env), secret)
        if title.startswith("Step 1"):
            if not values.get("COSTAR_KIT_URL"):
                zip_path = ask_file("CoStar kit zip (only if you downloaded it instead of using the link)", None,
                                    "Give the full path to the downloaded zip, or drag the file here.")
                if zip_path and zip_path.suffix.lower() != ".zip":
                    print(f"  {R}That isn't a .zip file; skipped.{X}")
                elif zip_path:
                    values["COSTAR_KIT_ZIP"] = str(zip_path.resolve())

    print(f"\n{B}Step 3 · Files from the quick start page{X}\n  beta-app.matterport.com/2026-princeton-hackathon/quickstart → \"models_index.csv\" button. Download it.")
    for name, label in (("models_index.csv", "models_index.csv"), ("AGENTS.md", "AGENTS.md (optional)")):
        src = ask_file(label, name, f"Usually lands in {DOWNLOADS}.")
        if src and src.resolve() != (DATA / name).resolve():
            shutil.copy2(src, DATA / name)
            print(f"  {G}Copied to backend/app/data/{name}{X}")

    save(values)
    print(f"\n{G}Saved backend/.env{X} (only readable by you, ignored by git).")
    check_all()
    print(f"\n{B}Step 4 · Paste in chat{X}\n  The link to Vexcel's tutorial and Python quickstart (on the Vexcel keys card). It isn't secret.")
    print(f"\n{D}Restart the API server to pick up the new keys.{X}\n")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Nothing new was saved unless you saw \"Saved backend/.env\".")
