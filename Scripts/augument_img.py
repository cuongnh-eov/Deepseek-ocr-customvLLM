# preprocess_ocr_eval_realworld.py
import argparse
from pathlib import Path
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

# Optional: PDF render
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


# ---------------------------
# Utils
# ---------------------------
def _to_rgb(img: Image.Image) -> Image.Image:
    return img.convert("RGB") if img.mode != "RGB" else img


def save_png(img: Image.Image, out_path: Path):
    img.save(out_path, format="PNG", optimize=True)


def list_default_inputs():
    exts = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.tif", "*.tiff", "*.pdf"]
    files = []
    for e in exts:
        files += sorted(Path(".").glob(e))
    return files


# ---------------------------
# 1) Skew/Rotation + crop nhẹ
# ---------------------------
def rotate_with_crop(img: Image.Image, angle_deg: float, crop_ratio: float = 0.96) -> Image.Image:
    # rotate with expand then center-crop back to avoid black borders
    w, h = img.size
    rotated = img.rotate(angle_deg, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    rw, rh = rotated.size

    cw, ch = int(w * crop_ratio), int(h * crop_ratio)
    left = (rw - cw) // 2
    top = (rh - ch) // 2
    cropped = rotated.crop((left, top, left + cw, top + ch))
    return cropped.resize((w, h), resample=Image.BICUBIC)


# ---------------------------
# 2) Perspective (keystone)
# ---------------------------
def _perspective_coeffs(pa, pb):
    # Solve for perspective transform coeffs mapping pa -> pb
    # pa: 4 pts in source, pb: 4 pts in target
    # returns 8 coeffs for PIL
    matrix = []
    for (x, y), (u, v) in zip(pa, pb):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    A = np.array(matrix, dtype=np.float64)
    B = np.array([p for uv in pb for p in uv], dtype=np.float64)
    coeffs, *_ = np.linalg.lstsq(A, B, rcond=None)
    return coeffs.tolist()


def random_perspective(img: Image.Image, max_shift: float = 0.06, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(seed)
    w, h = img.size

    # Original corners (target)
    pb = [(0, 0), (w, 0), (w, h), (0, h)]

    # Perturbed corners (source) to simulate keystone
    dx = max_shift * w
    dy = max_shift * h

    pa = [
        (rng.uniform(-dx, dx), rng.uniform(-dy, dy)),           # tl
        (w + rng.uniform(-dx, dx), rng.uniform(-dy, dy)),       # tr
        (w + rng.uniform(-dx, dx), h + rng.uniform(-dy, dy)),   # br
        (rng.uniform(-dx, dx), h + rng.uniform(-dy, dy)),       # bl
    ]

    coeffs = _perspective_coeffs(pa, pb)
    return img.transform((w, h), Image.PERSPECTIVE, coeffs, resample=Image.BICUBIC, fillcolor=(255, 255, 255))


# ---------------------------
# 3) Motion blur theo hướng
# ---------------------------
def horizontal_motion_blur(img: Image.Image, k: int = 15) -> Image.Image:
    k = int(k)
    if k < 3:
        return img
    if k % 2 == 0:
        k += 1

    arr = np.asarray(_to_rgb(img)).astype(np.float32)
    h, w, c = arr.shape

    # k không được lớn hơn width
    if k >= w:
        k = w - 1 if (w % 2 == 0) else w
        if k < 3:
            return img

    pad = k // 2
    arr_pad = np.pad(arr, ((0, 0), (pad, pad), (0, 0)), mode="edge")

    cs = np.cumsum(arr_pad, axis=1)
    cs = np.concatenate([np.zeros((h, 1, c), dtype=np.float32), cs], axis=1)

    out = (cs[:, k:, :] - cs[:, :-k, :]) / float(k)
    out = np.clip(out, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


def motion_blur(img: Image.Image, k: int = 15, angle_deg: float = 10.0) -> Image.Image:
    tmp = _to_rgb(img).rotate(angle_deg, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    tmp = horizontal_motion_blur(tmp, k=k)
    tmp = tmp.rotate(-angle_deg, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))

    w, h = img.size
    tw, th = tmp.size
    left = max(0, (tw - w) // 2)
    top = max(0, (th - h) // 2)
    return tmp.crop((left, top, left + w, top + h))



# ---------------------------
# 4) Shadow / uneven illumination
# ---------------------------
def add_shadow_gradient(img: Image.Image, strength: float = 0.35, seed: int = 0) -> Image.Image:
    # strength in [0,1], higher => darker shadow
    rng = np.random.default_rng(seed)
    arr = np.asarray(img).astype(np.float32) / 255.0
    h, w, _ = arr.shape

    # Random linear gradient direction
    x = np.linspace(0, 1, w)[None, :]
    y = np.linspace(0, 1, h)[:, None]
    angle = rng.uniform(0, 2 * np.pi)
    gx = np.cos(angle) * x + np.sin(angle) * y

    # Normalize gx to [0,1]
    gx = (gx - gx.min()) / (gx.max() - gx.min() + 1e-9)

    # Shadow mask: one side darker
    # mask in [1-strength, 1]
    mask = 1.0 - strength * gx

    out = arr * mask[..., None]
    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


# ---------------------------
# PDF render
# ---------------------------
def render_pdf_pages(pdf_path: Path, dpi: int = 200, max_pages: int | None = None):
    if fitz is None:
        raise RuntimeError("PyMuPDF (pymupdf) chưa được cài. Chạy: pip install pymupdf")
    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    pages = range(doc.page_count) if max_pages is None else range(min(doc.page_count, max_pages))
    for i in pages:
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        yield i + 1, img


# ---------------------------
# Main processing
# ---------------------------
def process_image(img0: Image.Image, out_dir: Path, stem: str, seed: int):
    img0 = _to_rgb(img0)
    outputs = []

    # A) skew/rotation
    for ang in (2.0, -3.5):
        img = rotate_with_crop(img0, angle_deg=ang, crop_ratio=0.96)
        p = out_dir / f"{stem}__skew_{str(ang).replace('.','p')}.png"
        save_png(img, p); outputs.append(p)

    # B) perspective
    for sft, ss in ((0.05, seed), (0.08, seed + 1)):
        img = random_perspective(img0, max_shift=sft, seed=ss)
        p = out_dir / f"{stem}__persp_{str(sft).replace('.','p')}.png"
        save_png(img, p); outputs.append(p)

    # C) motion blur
    for k, ang in ((13, 8.0), (21, 15.0)):
        img = motion_blur(img0, k=k, angle_deg=ang)
        p = out_dir / f"{stem}__mblur_k{k}_a{str(ang).replace('.','p')}.png"
        save_png(img, p); outputs.append(p)

    # D) shadow/uneven illumination
    for st, ss in ((0.30, seed), (0.45, seed + 2)):
        img = add_shadow_gradient(img0, strength=st, seed=ss)
        p = out_dir / f"{stem}__shadow_{str(st).replace('.','p')}.png"
        save_png(img, p); outputs.append(p)

    return outputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*", help="Paths to images or PDFs (if empty: process current folder)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dpi", type=int, default=200, help="Render DPI for PDF")
    ap.add_argument("--max_pages", type=int, default=0, help="Max pages per PDF (0 = all)")
    args = ap.parse_args()

    inps = [Path(x) for x in args.inputs] if args.inputs else list_default_inputs()
    if not inps:
        raise SystemExit("Không tìm thấy input nào (ảnh/pdf).")

    for p in inps:
        if not p.exists():
            print(f"[SKIP] Not found: {p}")
            continue

        if p.suffix.lower() == ".pdf":
            mp = None if args.max_pages == 0 else args.max_pages
            try:
                for page_no, img in render_pdf_pages(p, dpi=args.dpi, max_pages=mp):
                    stem = f"{p.stem}__p{page_no:03d}"
                    outs = process_image(img, p.parent, stem, seed=args.seed)
                    print(f"[OK] {p.name} page {page_no} -> {len(outs)} files in: {p.parent}")
            except Exception as e:
                print(f"[ERR] PDF {p}: {e}")
        else:
            img0 = Image.open(p)
            outs = process_image(img0, p.parent, p.stem, seed=args.seed)
            print(f"[OK] {p.name} -> {len(outs)} files saved in: {p.parent}")


if __name__ == "__main__":
    main()
