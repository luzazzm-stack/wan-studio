# App icon matching the UI: black rounded square, white ring with a dot, small tiffany glow.
from PIL import Image, ImageDraw, ImageFilter
S = 512
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
base = Image.new("RGBA", (S, S), (8, 8, 10, 255))
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse((-120, -160, 330, 290), fill=(129, 216, 208, 120))
base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(90)))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=116, fill=255)
im.paste(base, (0, 0), mask)
d = ImageDraw.Draw(im)
d.ellipse((116, 116, 396, 396), outline="white", width=34)
d.ellipse((214, 214, 298, 298), fill="white")
im = im.resize((256, 256), Image.LANCZOS)
im.save("web/wanstudio.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
im.save("web/icon-256.png")
im512 = Image.new("RGBA", (S, S), (0, 0, 0, 0)); im512.paste(base, (0, 0), mask); d2 = ImageDraw.Draw(im512)
d2.ellipse((116, 116, 396, 396), outline="white", width=34); d2.ellipse((214, 214, 298, 298), fill="white"); im512.save("web/icon-512.png")
