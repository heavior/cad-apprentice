# Trims the white space around a picture down to the model plus a margin. With a width:height ratio it
# pads with white where the model sits near an edge; with ratio 0 it keeps the model's own shape and never
# grows past the picture's edges. Usage: trim_picture.py in.png out.png [ratio] [pad]
import sys
from PIL import Image, ImageOps

EDGE = 4  # Fusion draws a thin grey frame line at the picture's edge; it is not the model


def trim(src, dst, ratio=1.5, pad=0.06):
    im = Image.open(src).convert('RGB')
    inner = im.crop((EDGE, EDGE, im.width - EDGE, im.height - EDGE))
    l, t, r, b = ImageOps.invert(inner).point(lambda v: 255 if v > 12 else 0).getbbox()
    l, t, r, b = l + EDGE, t + EDGE, r + EDGE, b + EDGE
    w, h = (r - l) * (1 + 2 * pad), (b - t) * (1 + 2 * pad)
    cx, cy = (l + r) / 2, (t + b) / 2
    if not ratio:
        box = (max(int(cx - w / 2), 0), max(int(cy - h / 2), 0),
               min(int(cx + w / 2), im.width), min(int(cy + h / 2), im.height))
        out = im.crop(box)
    else:
        w, h = max(w, h * ratio), max(h, w / ratio)
        x0, y0 = int(cx - w / 2), int(cy - h / 2)
        out = Image.new('RGB', (int(w), int(h)), 'white')
        out.paste(im.crop((max(x0, 0), max(y0, 0), min(x0 + int(w), im.width), min(y0 + int(h), im.height))),
                  (max(-x0, 0), max(-y0, 0)))
    out.save(dst)
    return out.size


if __name__ == '__main__':
    print(trim(sys.argv[1], sys.argv[2], *(float(a) for a in sys.argv[3:])))
