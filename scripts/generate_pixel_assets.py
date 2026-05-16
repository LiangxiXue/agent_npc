from __future__ import annotations

import struct
import zlib
from pathlib import Path


Color = tuple[int, int, int, int]

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "assets" / "pixel"


def write_png(path: Path, width: int, height: int, pixels: list[Color]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    payload = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
            chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(payload)


class Canvas:
    def __init__(self, width: int, height: int, bg: Color) -> None:
        self.width = width
        self.height = height
        self.pixels = [bg for _ in range(width * height)]

    def rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        for py in range(max(0, y), min(self.height, y + h)):
            for px in range(max(0, x), min(self.width, x + w)):
                self.pixels[py * self.width + px] = color

    def border(self, x: int, y: int, w: int, h: int, color: Color, t: int = 1) -> None:
        self.rect(x, y, w, t, color)
        self.rect(x, y + h - t, w, t, color)
        self.rect(x, y, t, h, color)
        self.rect(x + w - t, y, t, h, color)

    def line(self, x1: int, y1: int, x2: int, y2: int, color: Color) -> None:
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        error = dx + dy
        x, y = x1, y1
        while True:
            self.rect(x, y, 1, 1, color)
            if x == x2 and y == y2:
                break
            e2 = 2 * error
            if e2 >= dy:
                error += dy
                x += sx
            if e2 <= dx:
                error += dx
                y += sy

    def save(self, filename: str) -> None:
        write_png(OUT / filename, self.width, self.height, self.pixels)


C = {
    "ink": (15, 11, 14, 255),
    "night": (24, 16, 26, 255),
    "wood": (78, 48, 31, 255),
    "wood2": (105, 70, 40, 255),
    "gold": (218, 158, 76, 255),
    "lamp": (255, 219, 126, 255),
    "stone": (78, 82, 88, 255),
    "stone2": (108, 113, 120, 255),
    "green": (58, 117, 76, 255),
    "deepgreen": (31, 75, 52, 255),
    "cloth": (151, 50, 63, 255),
    "blue": (45, 74, 106, 255),
    "purple": (82, 61, 112, 255),
    "skin": (196, 126, 83, 255),
    "paper": (220, 190, 128, 255),
    "metal": (160, 168, 158, 255),
    "copper": (188, 92, 43, 255),
    "shadow": (0, 0, 0, 70),
}


def checker(canvas: Canvas, a: Color, b: Color, size: int) -> None:
    for y in range(0, canvas.height, size):
        for x in range(0, canvas.width, size):
            canvas.rect(x, y, size, size, a if (x // size + y // size) % 2 == 0 else b)


def make_maps() -> None:
    town = Canvas(320, 180, C["night"])
    checker(town, (34, 39, 38, 255), (41, 47, 44, 255), 8)
    town.rect(0, 122, 320, 58, (43, 34, 29, 255))
    town.line(0, 155, 120, 100, C["wood2"])
    town.line(120, 100, 320, 148, C["wood2"])
    for x in range(22, 290, 64):
        town.rect(x, 64, 42, 42, C["wood"])
        town.rect(x + 4, 52, 34, 14, C["cloth"])
        town.rect(x + 12, 82, 12, 24, C["ink"])
        town.rect(x + 28, 74, 8, 8, C["lamp"])
    town.rect(132, 34, 62, 82, C["stone"])
    town.rect(142, 22, 42, 16, C["stone2"])
    town.rect(154, 72, 18, 44, C["ink"])
    town.rect(10, 18, 20, 20, C["lamp"])
    town.save("map-grayhaven-town.png")

    tavern = Canvas(320, 180, (30, 18, 15, 255))
    checker(tavern, (45, 28, 19, 255), (52, 32, 21, 255), 10)
    tavern.rect(0, 112, 320, 68, (54, 34, 22, 255))
    tavern.rect(34, 44, 252, 78, C["wood"])
    tavern.rect(44, 54, 232, 58, (88, 55, 32, 255))
    for x in range(62, 250, 48):
        tavern.rect(x, 68, 24, 22, C["lamp"])
        tavern.rect(x + 4, 72, 16, 14, (255, 237, 160, 255))
    tavern.rect(118, 108, 86, 18, C["wood2"])
    tavern.rect(36, 130, 248, 12, C["wood2"])
    tavern.rect(232, 88, 34, 34, (30, 15, 16, 255))
    tavern.save("map-tavern.png")

    guard = Canvas(320, 180, (23, 29, 31, 255))
    checker(guard, (35, 41, 42, 255), (42, 48, 48, 255), 8)
    guard.rect(0, 128, 320, 52, (47, 39, 34, 255))
    guard.rect(32, 58, 64, 78, C["stone"])
    guard.rect(224, 58, 64, 78, C["stone"])
    guard.rect(50, 34, 28, 24, C["stone2"])
    guard.rect(242, 34, 28, 24, C["stone2"])
    guard.rect(96, 84, 128, 48, (91, 61, 35, 255))
    guard.rect(108, 92, 104, 30, C["wood2"])
    for x in range(116, 202, 20):
        guard.rect(x, 84, 8, 48, C["ink"])
    guard.rect(145, 24, 30, 30, C["lamp"])
    guard.save("map-guard-post.png")

    ruins = Canvas(320, 180, (17, 22, 27, 255))
    checker(ruins, (24, 33, 37, 255), (28, 38, 42, 255), 8)
    ruins.rect(0, 132, 320, 48, (31, 48, 42, 255))
    ruins.rect(82, 42, 156, 106, C["stone"])
    ruins.rect(100, 58, 120, 76, (48, 54, 61, 255))
    ruins.rect(132, 72, 56, 76, C["ink"])
    ruins.rect(116, 38, 88, 16, C["stone2"])
    ruins.line(160, 84, 136, 126, C["green"])
    ruins.line(160, 84, 184, 126, C["green"])
    ruins.line(136, 126, 184, 126, C["green"])
    for x in range(28, 292, 44):
        ruins.rect(x, 118, 18, 10, C["deepgreen"])
        ruins.rect(x + 7, 98, 4, 22, C["deepgreen"])
    ruins.save("map-ruins-entrance.png")


def make_portrait(filename: str, hair: Color, outfit: Color, accent: Color) -> None:
    img = Canvas(96, 96, (18, 13, 16, 255))
    img.border(0, 0, 96, 96, C["gold"], 3)
    img.rect(22, 62, 52, 26, outfit)
    img.rect(28, 28, 40, 38, C["skin"])
    img.rect(24, 22, 48, 22, hair)
    img.rect(20, 34, 12, 30, hair)
    img.rect(64, 34, 12, 30, hair)
    img.rect(36, 44, 6, 5, C["ink"])
    img.rect(56, 44, 6, 5, C["ink"])
    img.rect(43, 56, 14, 4, (88, 36, 42, 255))
    img.rect(28, 68, 40, 8, accent)
    img.rect(34, 18, 28, 8, accent)
    img.save(filename)


def make_npcs() -> None:
    make_portrait("npc-lina.png", (92, 48, 34, 255), (94, 43, 37, 255), C["gold"])
    make_portrait("npc-ron.png", (55, 46, 39, 255), (50, 67, 82, 255), C["metal"])
    make_portrait("npc-mira.png", (66, 48, 88, 255), (45, 63, 91, 255), C["paper"])
    make_portrait("npc-sable.png", (38, 32, 35, 255), (79, 43, 86, 255), C["copper"])


def make_item(filename: str, draw: callable[[Canvas], None]) -> None:
    icon = Canvas(48, 48, (18, 13, 16, 255))
    icon.border(0, 0, 48, 48, (96, 66, 43, 255), 2)
    icon.rect(4, 4, 40, 40, (29, 21, 19, 255))
    draw(icon)
    icon.save(filename)


def make_items() -> None:
    make_item(
        "item-copper-key.png",
        lambda c: (
            c.rect(14, 22, 24, 6, C["copper"]),
            c.rect(10, 18, 10, 14, C["copper"]),
            c.rect(13, 21, 4, 8, C["ink"]),
            c.rect(32, 18, 4, 4, C["copper"]),
            c.rect(36, 22, 4, 4, C["copper"]),
        ),
    )
    make_item(
        "item-tavern-coupon.png",
        lambda c: (
            c.rect(11, 15, 26, 18, C["paper"]),
            c.border(11, 15, 26, 18, C["gold"], 2),
            c.rect(16, 21, 16, 3, C["cloth"]),
            c.rect(16, 27, 10, 2, C["wood"]),
        ),
    )
    make_item(
        "item-guard-badge.png",
        lambda c: (
            c.rect(18, 12, 12, 4, C["metal"]),
            c.rect(14, 16, 20, 16, C["metal"]),
            c.rect(18, 32, 12, 5, C["metal"]),
            c.rect(20, 20, 8, 8, C["blue"]),
        ),
    )
    make_item(
        "item-ruins-notes.png",
        lambda c: (
            c.rect(12, 10, 24, 30, C["paper"]),
            c.rect(15, 16, 18, 2, C["stone"]),
            c.rect(15, 22, 14, 2, C["stone"]),
            c.line(17, 31, 24, 24, C["green"]),
            c.line(24, 24, 31, 31, C["green"]),
        ),
    )
    make_item(
        "item-relic-tip.png",
        lambda c: (
            c.rect(18, 12, 12, 24, C["purple"]),
            c.rect(14, 18, 20, 12, C["purple"]),
            c.rect(21, 17, 6, 14, C["lamp"]),
            c.rect(20, 8, 8, 5, C["gold"]),
        ),
    )
    make_item(
        "item-empty-slot.png",
        lambda c: (
            c.rect(15, 15, 18, 18, (48, 38, 34, 255)),
            c.line(15, 15, 32, 32, (97, 73, 52, 255)),
            c.line(32, 15, 15, 32, (97, 73, 52, 255)),
        ),
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_maps()
    make_npcs()
    make_items()
    print(f"Wrote pixel assets to {OUT}")


if __name__ == "__main__":
    main()
