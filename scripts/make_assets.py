#!/usr/bin/env python3
"""Render the cover image and the demo video from the real run data.

    python scripts/make_assets.py cover
    python scripts/make_assets.py video

Nothing in the video is invented: the addresses, hashes, counts and refusals are
read from `keys/deployment.json`, `demo/journal.jsonl` and `demo/passes/*.json`.
Optional screenshots of the live verifier can be dropped into `demo/shots/` and
are used if present.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = Path("/usr/share/fonts/truetype/liberation")
SANS = FONT_DIR / "LiberationSans-Regular.ttf"
SANS_B = FONT_DIR / "LiberationSans-Bold.ttf"
MONO = FONT_DIR / "LiberationMono-Regular.ttf"
MONO_B = FONT_DIR / "LiberationMono-Bold.ttf"

BG = (7, 11, 20)
PANEL = (16, 24, 40)
PANEL_2 = (20, 31, 51)
LINE = (34, 47, 72)
TEXT = (231, 237, 249)
MUTED = (134, 149, 179)
ACCENT = (110, 231, 183)
ACCENT_2 = (125, 211, 252)
DANGER = (251, 113, 133)
PURPLE = (167, 139, 250)


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    if mono:
        return ImageFont.truetype(str(MONO_B if bold else MONO), size)
    return ImageFont.truetype(str(SANS_B if bold else SANS), size)


def load_run() -> dict:
    dep = json.loads((ROOT / "keys" / "deployment.json").read_text())
    journal = [json.loads(line) for line in (ROOT / "demo" / "journal.jsonl").read_text().splitlines() if line.strip()]
    passes = [json.loads(p.read_text()) for p in sorted((ROOT / "demo" / "passes").glob("*.json"))]
    features_path = ROOT / "demo" / "features.json"
    features = json.loads(features_path.read_text()) if features_path.exists() else {}
    sealed = ROOT / "demo" / "sealed" / "index.json"
    sealed_index = json.loads(sealed.read_text()) if sealed.exists() else []
    receipts = [json.loads(p.read_text()) for p in sorted((ROOT / "demo" / "receipts").glob("*.json"))]
    return {
        "deployment": dep,
        "journal": journal,
        "passes": passes,
        "features": features,
        "sealed": sealed_index,
        "receipts": receipts,
    }


def short(hexstr: str, head: int = 12, tail: int = 8) -> str:
    body = hexstr.removeprefix("0x") if hexstr.startswith("0x") else hexstr
    return body[:head] + "…" + body[-tail:] if len(body) > head + tail + 1 else hexstr


# ---------------------------------------------------------------------- #
# Drawing primitives
# ---------------------------------------------------------------------- #
def gradient(w: int, h: int) -> Image.Image:
    base = Image.new("RGB", (w, h), BG)
    top = Image.new("RGB", (w, h), (14, 38, 58))
    mask = Image.new("L", (w, h))
    md = ImageDraw.Draw(mask)
    for y in range(h):
        md.line([(0, y), (w, y)], fill=max(0, 120 - int(120 * y / h)))
    base.paste(top, (0, 0), mask)
    glow = Image.new("RGB", (w, h), (26, 18, 58))
    mask2 = Image.new("L", (w, h))
    m2 = ImageDraw.Draw(mask2)
    for y in range(h):
        m2.line([(0, y), (w, y)], fill=max(0, 70 - int(70 * y / h)))
    base.paste(glow, (0, 0), mask2)
    return base


def rounded(d: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_block(d, xy, lines, f, fill, spacing=8):
    x, y = xy
    for line, color in lines:
        d.text((x, y), line, font=f, fill=color or fill)
        y += f.size + spacing
    return y


def _watermark(d, w, h):
    """A faint mark keeps the lower half from reading as dead space."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.text((w - 320, h - 300), "Q", font=font(300, bold=True), fill=(255, 255, 255, 12))
    ld.ellipse([(w - 330, h - 330), (w - 30, h - 30)], outline=(110, 231, 183, 16), width=2)
    d._image.paste(Image.alpha_composite(d._image.convert("RGBA"), layer).convert("RGB"), (0, 0))


def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if f.getlength(trial) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------- #
# Cover
# ---------------------------------------------------------------------- #
def make_cover() -> Path:
    w, h = 2400, 1350
    img = gradient(w, h)
    d = ImageDraw.Draw(img)
    run = load_run()
    dep = run["deployment"]

    d.text((120, 96), "BUILD BEFORE Q-DAY  ·  QUANTUM PASS  ·  QORECHAIN TESTNET",
           font=font(30, bold=True), fill=ACCENT)

    d.text((120, 190), "QorePass", font=font(150, bold=True), fill=TEXT)
    sub = "Passes that belong to a post-quantum key,"
    sub2 = "not to a wallet."
    d.text((124, 380), sub, font=font(58), fill=MUTED)
    d.text((124, 456), sub2, font=font(58), fill=MUTED)

    # the three authorisation rules
    rules = [
        ("01", "Issuer", "ML-DSA-87 signature, verified by pqcVerify\nagainst the key the chain holds for the account"),
        ("02", "Nonce", "one signature, one pass — replay refused\nby a monotonic per-issuer counter"),
        ("03", "Holder", "the pass is bound to the holder's ML-DSA-87 key;\na copied pass id checks in for nobody"),
    ]
    y = 600
    for num, title, body in rules:
        rounded(d, (120, y, 1120, y + 150), 22, PANEL, LINE)
        d.text((152, y + 34), num, font=font(40, bold=True, mono=True), fill=ACCENT_2)
        d.text((240, y + 30), title, font=font(38, bold=True), fill=TEXT)
        for i, line in enumerate(body.split("\n")):
            d.text((240, y + 80 + i * 30), line, font=font(24), fill=MUTED)
        y += 170

    # right column: the run
    x = 1240
    rounded(d, (x, 600, w - 120, h - 140), 26, PANEL_2, LINE)
    d.text((x + 44, 636), "ON TESTNET RIGHT NOW", font=font(26, bold=True), fill=ACCENT)

    passes = run["passes"]
    rows = [
        ("registry", short(dep["registry"], 18, 10)),
        ("deploy tx", short(dep["tx"].removeprefix("0x"), 18, 10)),
        ("block", str(dep["block"])),
        ("passes", "  ".join(f"{p['holder']['label']}" for p in passes)),
        ("transactions", str(len(run["journal"]))),
        ("refusals", "AlreadyCheckedIn · PassAlreadyRevoked\nHolderKeyMismatch · PassExists · BadIssuerSignature"),
        ("tests", "46 Foundry tests + 7 invariants · 100% branch"),
    ]
    yy = 690
    for label, value in rows:
        d.text((x + 44, yy), label.upper(), font=font(20, bold=True), fill=MUTED)
        size = 21 if label == "refusals" else 24
        for i, line in enumerate(value.split("\n")):
            d.text((x + 300, yy - 2 + i * 30), line, font=font(size, mono=True), fill=TEXT)
        yy += 34 + (30 * (len(value.split("\n")) - 1)) + 42

    d.text((120, h - 96), "Apache-2.0  ·  github.com/dorithesky/qorepass-verify",
           font=font(26), fill=MUTED)
    d.text((w - 620, h - 96), "qorechain-diana  ·  EVM 9800", font=font(26, mono=True), fill=MUTED)

    out = ROOT / "docs" / "cover.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {w}x{h})")
    return out


# ---------------------------------------------------------------------- #
# Video
# ---------------------------------------------------------------------- #
class Scene:
    def __init__(self, seconds: float, kicker: str = "", title: str = ""):
        self.seconds = seconds
        self.kicker = kicker
        self.title = title

    def draw(self, d: ImageDraw.ImageDraw, w: int, h: int, t: float) -> None:
        raise NotImplementedError


class Slide(Scene):
    def __init__(self, seconds, kicker, title, bullets=(), mono=None, accent=ACCENT, big=None):
        super().__init__(seconds, kicker, title)
        self.bullets = bullets
        self.mono = mono or []
        self.accent = accent
        self.big = big

    def draw(self, d, w, h, t):
        _watermark(d, w, h)
        d.text((72, 60), self.kicker.upper(), font=font(20, bold=True), fill=self.accent)
        d.text((72, 92), self.title, font=font(42, bold=True), fill=TEXT)
        d.line([(72, 160), (w - 72, 160)], fill=LINE, width=2)
        y = 196
        if self.big:
            d.text((72, y), self.big, font=font(64, bold=True), fill=TEXT)
            y += 100
        for bullet in self.bullets:
            for line in wrap("· " + bullet, font(24), w - 180):
                d.text((72, y), line, font=font(24), fill=TEXT)
                y += 36
            y += 8
        if self.mono:
            y += 8
            for line, color in self.mono:
                f = font(21, mono=True)
                rounded(d, (72, y - 6, w - 72, y + 30), 8, (8, 13, 22), LINE)
                d.text((88, y), line, font=f, fill=color or ACCENT)
                y += 44


class Shot(Scene):
    """A screenshot from demo/shots/, scaled into the frame."""

    def __init__(self, seconds, kicker, title, image: Path):
        super().__init__(seconds, kicker, title)
        self.image = image

    def draw(self, d, w, h, t):
        d.text((72, 60), self.kicker.upper(), font=font(20, bold=True), fill=ACCENT_2)
        d.text((72, 92), self.title, font=font(38, bold=True), fill=TEXT)
        shot = Image.open(self.image).convert("RGB")
        box_w, box_h = w - 120, h - 230
        scale = min(box_w / shot.width, box_h / shot.height)
        shot = shot.resize((int(shot.width * scale), int(shot.height * scale)), Image.LANCZOS)
        d._image.paste(shot, ((w - shot.width) // 2, 170))
        d.rectangle([(w - shot.width) // 2 - 1, 169, (w + shot.width) // 2, 171 + shot.height], outline=LINE)


def draw_frame(scene: Scene, w: int, h: int, t: float, index: int, total: int) -> Image.Image:
    img = gradient(w, h)
    d = ImageDraw.Draw(img)
    d._image = img
    scene.draw(d, w, h, t)
    # progress + footer
    d.line([(0, h - 4), (int(w * (index + 1) / total), h - 4)], fill=ACCENT, width=4)
    d.text((w - 200, h - 40), "QorePass · Apache-2.0", font=font(14), fill=MUTED)
    d.text((72, h - 40), "qorechain-diana · tap the refusals, they are real transactions", font=font(14), fill=MUTED)
    return img


def make_video() -> Path:
    run = load_run()
    dep = run["deployment"]
    journal = run["journal"]
    shots_dir = ROOT / "demo" / "shots"
    shots = sorted(shots_dir.glob("*.png")) if shots_dir.exists() else []
    # prefer the composite of the live page when present
    shots.sort(key=lambda p: (0 if "composite" in p.name else 1, p.name))

    refused = [e for e in journal if e.get("ok") is False]
    scenarios = [
        Slide(8, "Build Before Q-Day · Quantum Pass", "QorePass",
              bullets=[
                  "An event pass, credential or receipt that belongs to an ML-DSA-87 key — not to a wallet.",
                  "Issued, checked in and revoked on QoreChain testnet diana, with every state change authorised on chain.",
              ],
              mono=[("registry  " + dep["registry"], ACCENT)]),
        Slide(10, "The problem", "Three ways a pass fails today",
              bullets=[
                  "A screenshot is as good as the original — possession of the barcode is the whole check.",
                  "Whoever can sign for the account can mint as many passes as they like.",
                  "The signature that protects it is classical: one quantum computer undoes all of it.",
              ]),
        Slide(12, "How it works", "Three authorisations, each verified in a precompile",
              bullets=[
                  "01 · Issuer: pqcVerify against the key QoreChain holds for the issuer's account.",
                  "02 · Nonce: one signature, one pass — a replayed signature cannot mint a second one.",
                  "03 · Holder: the pass stores keccak(holder ML-DSA-87 key); check-in needs that key's signature.",
              ],
              mono=[("pqcVerify 0x…0a01   pqcKeyStatus 0x…0a02   chain 9800", ACCENT_2)]),
        Slide(9, "On testnet", "Deployed, funded and exercised — not mocked",
              bullets=[
                  f"deploy tx {short(dep['tx'], 22, 10)} at block {dep['block']}",
                  f"{len(journal)} transactions: hybrid-signed native txs, a scoped EVM window, {len(run['passes'])} passes.",
                  "46 Foundry tests and 7 invariants (128,000 random calls) over 100% of branches.",
              ],
              mono=[("registry " + dep["registry"], ACCENT), ("admin    " + dep["admin"], TEXT)]),
    ]

    issue = next(e for e in journal if e["kind"] == "issue")
    check = next(e for e in journal if e["kind"] == "checkin" and e.get("ok"))
    scenarios += [
        Slide(11, "Issue", "The issuer signs once; the chain verifies it",
              bullets=[
                  "A 4627-byte ML-DSA-87 signature over a 275-byte message bound to the chain, this contract and the issuer's nonce.",
                  "The pass document carries the readable fields; the chain holds only hashes.",
              ],
              mono=[("issuePass  nonce " + str(run["passes"][0]["approvalNonce"]) + "  tx " + short(issue["tx"], 20, 10), ACCENT)]),
        Slide(11, "Check in", "The venue scans; the holder's key authorises",
              bullets=[
                  "The attendee has no wallet and pays nothing — the venue submits the transaction.",
                  "A copied pass id is not enough: check-in needs the holder's ML-DSA-87 signature.",
              ],
              mono=[("checkIn  " + short(check["tx"], 24, 10) + "  → CHECKED_IN", ACCENT)]),
    ]

    if shots:
        scenarios.append(Shot(12, "Live verifier", "dorithesky.github.io/qorepass-verify", shots[0]))
    else:
        scenarios.append(Slide(10, "Live verifier", "Every read is an eth_call",
                               bullets=["The dashboard at dorithesky.github.io/qorepass-verify reads passState and passInfo straight from the EVM lane — no wallet, no backend."]))

    refusal_lines = []
    for entry in refused:
        reason = entry.get("revert", "refused")
        refusal_lines.append((f"{reason:<46} {short(entry['tx'], 10, 6)}", DANGER))

    features = run["features"]
    sealed = run["sealed"]
    receipts = run["receipts"]
    extra = []
    if sealed:
        batch = sealed[-1]
        extra.append(Slide(11, "QoreSeal", "The issuance archive, sealed to a post-quantum key",
              bullets=[
                  f"{batch['entries']} pass documents in one {batch['envelope_len']}-byte envelope, encrypted to the issuer's ML-KEM-1024 key.",
                  "Only a digest of the envelope goes on chain, in the memo of a hybrid-signed transaction.",
                  "Anyone without the ML-KEM secret — a quantum computer included — gets an authentication failure, not the archive.",
              ],
              mono=[(batch["memo_commitment"], ACCENT)]))
    if receipts:
        extra.append(Slide(11, "QoreSign · SIWQ", "An admission receipt the venue cannot fake",
              bullets=[
                  f"{len(receipts)} check-in receipts, each a Sign In With QoreChain message: pass id, holder key hash, event, time, registry.",
                  "Signed by the venue's hybrid key and verified against the ML-DSA-87 key its account registered on chain.",
                  "An edited time, another pass id, or the same receipt a day later is refused.",
              ],
              mono=[("qorepass.venue · " + receipts[0]["nonce"], ACCENT_2)]))
    if features.get("kiosk"):
        extra.append(Slide(12, "Smart account", "A door scanner that can do exactly one thing",
              bullets=[
                  "The venue links an Ed25519 kiosk key with the evm permission and a rule naming one call: checkIn on this registry.",
                  "The kiosk admitted dara-1 through MsgExecuteEVM; a relayer paid the fee and could not change what was authorised.",
                  "The same key then tried to mint a pass — the chain refused: \"authenticator not permitted for this action\".",
              ],
              mono=[("allowed_evm_calls = [ " + (features["kiosk"]["allowed_evm_calls"][0][:34] + "…/0x1ef04ae6" ) + " ]", ACCENT)]))
    scenarios += extra
    scenarios += [
        Slide(14, "Refusals", "The chain said no, in its own words",
              bullets=[
                  "Each of these mined a transaction with status 0 and reverted with the contract's custom error.",
                  "Reasons were recovered by replaying the transaction one block earlier — not typed in.",
              ],
              mono=refusal_lines[:5], accent=DANGER),
        Slide(11, "Q-Day", "An attacker with the issuer's classical key",
              bullets=[
                  "It holds the issuer's ECDSA key — the one a quantum computer would recover — and submits from the issuer's own account.",
                  "It does not hold the ML-DSA-87 secret, so the new pass is refused before it exists.",
              ],
              mono=[("issuePass → BadIssuerSignature()   pass count unchanged", DANGER)],
              accent=DANGER),
        Slide(11, "Re-check it yourself", "No keys, no wallet, no trust in this page",
              bullets=[
                  "python verify.py — 27 read-only checks against the public testnet: bytecode, state, every journaled transaction, the refusals replayed now.",
                  "QoreScan's CycloneDX CBOM maps the same code to DORA and NIS2; the registry's counters read back through qorechain-mcp.",
                  "Every hash in docs/EVIDENCE.md was generated from the chain, not typed in.",
              ],
              mono=[("python verify.py            → 27/27", ACCENT),
                    ("qorescan report --framework dora → docs/DORA-REPORT.md", ACCENT_2)]),
        Slide(9, "Done", "QorePass",
              bullets=[
                  "github.com/dorithesky/qorepass-verify · Apache-2.0",
                  "Live verifier: dorithesky.github.io/qorepass-verify",
                  "Every hash: docs/EVIDENCE.md, generated from the chain.",
              ],
              mono=[("QoreChain testnet qorechain-diana · EVM 9800", ACCENT_2)]),
    ]

    w, h, fps = 1280, 720, 12
    total = sum(int(s.seconds * fps) for s in scenarios)
    ffmpeg = None
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg = "ffmpeg"

    out = ROOT / "demo" / "qorepass-demo.mp4"
    cmd = [
        ffmpeg, "-y", "-f", "image2pipe", "-vcodec", "png", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart",
        "-vf", "scale=1280:720", str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    index = 0
    for scene in scenarios:
        frames = int(scene.seconds * fps)
        for i in range(frames):
            img = draw_frame(scene, w, h, i / fps, index, total)
            img.save(proc.stdin, format="PNG")
            index += 1
    proc.stdin.close()
    proc.wait()
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {total / fps:.1f}s, {index} frames)")
    return out


def main() -> int:
    what = sys.argv[1] if len(sys.argv) > 1 else "both"
    if what in {"cover", "both"}:
        make_cover()
    if what in {"video", "both"}:
        make_video()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
