import asyncio
import logging
import os
import sys
import time
import contextlib
import hashlib
from pathlib import Path
from dotenv import load_dotenv

from browser_use import Agent, ChatOpenAI


# -----------------------------
# 1) Log capture: write ALL console logs into one file
# -----------------------------
def setup_logging(out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")

    # File handler (UTF-8)
    fh = logging.FileHandler(out_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    # Console handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    # Clear existing handlers to avoid duplicates
    root.handlers.clear()
    root.addHandler(fh)
    root.addHandler(sh)

    # Make sure agent logs are visible
    logging.getLogger("Agent").setLevel(logging.INFO)
    logging.getLogger("browser_use").setLevel(logging.INFO)
    logging.getLogger("tools").setLevel(logging.INFO)


# -----------------------------
# 2) File tailer: periodically append todo.md/results.md content into the same file
# -----------------------------
logger = logging.getLogger("artifact_tailer")


class ArtifactTailer:
    """
    Append a FULL snapshot of each target file every time it changes.
    This records every update as a new block at the end of the combined file,
    including overwrite/rewrite updates.
    """
    def __init__(self, combined_file: Path, targets: list[Path], poll_sec: float = 0.2):
        self.combined_file = combined_file
        self.targets = targets
        self.poll_sec = poll_sec
        self._stop = False
        self._last_hash: dict[Path, str] = {}

    def stop(self):
        self._stop = True

    async def run(self):
        while not self._stop:
            for p in self.targets:
                try:
                    if not p.exists():
                        continue

                    data = p.read_bytes()
                    h = hashlib.sha256(data).hexdigest()

                    # Only when content changes, append a full snapshot
                    if self._last_hash.get(p) == h:
                        continue
                    self._last_hash[p] = h

                    text = data.decode("utf-8", errors="replace")
                    stamp = time.strftime("%Y-%m-%d %H:%M:%S")

                    with self.combined_file.open("a", encoding="utf-8", errors="replace") as f:
                        f.write("\n")
                        f.write(f"----- [ARTIFACT SNAPSHOT] {p.name} @ {stamp} -----\n")
                        f.write(text.rstrip() + "\n")
                        f.write(f"----- [END {p.name}] -----\n")

                except Exception as e:
                    logger.warning(f"Tail error for {p}: {e}")

            await asyncio.sleep(self.poll_sec)


# -----------------------------
# 3) Discover artifacts: try to find the run temp folder after agent starts
# -----------------------------
def guess_latest_browser_use_temp_dir() -> Path | None:
    """
    browser-use often writes into a temp dir like:
    %LOCALAPPDATA%\\Temp\\browser_use_agent_...\\browseruse_agent_data\\
    We'll find the newest matching folder.
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None

    temp_dir = Path(local_appdata) / "Temp"
    if not temp_dir.exists():
        return None

    candidates = sorted(
        temp_dir.glob("browser_use_agent_*"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for c in candidates[:10]:
        data_dir = c / "browseruse_agent_data"
        if data_dir.exists():
            return data_dir
    return None


async def main():
    load_dotenv()

    # --- Combined output file (everything goes here) ---
    combined = Path("run_artifacts_and_reasoning.log")
    setup_logging(combined)

    # (Optional but recommended) avoid Windows encoding issues globally
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    llm = ChatOpenAI(model="o3")

    task = "Go to python.org and enumerate all top-level navigation sections. Do not stop until all discovered sections are processed."
    agent = Agent(
        task=task,
        llm=llm,
        max_steps=500,
        max_failures=10,
    )

    # Start agent run and artifact tailer in parallel
    tailer = None
    tailer_task = None

    try:
        # Give it a moment to create temp folders/files
        await asyncio.sleep(1.0)

        data_dir = guess_latest_browser_use_temp_dir()
        if data_dir:
            logging.info(f"[Runner] Detected browser-use data dir: {data_dir}")

            targets = list(data_dir.glob("*.md"))
            tailer = ArtifactTailer(combined_file=combined, targets=targets, poll_sec=0.2)
            tailer_task = asyncio.create_task(tailer.run())
        else:
            logging.warning("[Runner] Could not detect browser-use temp data dir; only logs will be captured.")

        await agent.run()

    finally:
        if tailer:
            tailer.stop()
        if tailer_task:
            # Let it flush one last time
            await asyncio.sleep(0.2)
            tailer_task.cancel()
            with contextlib.suppress(Exception):
                await tailer_task


if __name__ == "__main__":
    asyncio.run(main())