"""生成地面贴图：可无缝平铺的草叶纹理和泥土纹理。地面按遮罩在两者之间混合，壳层草按草叶贴图的高度通道把高的草叶抬起来。

用法（后台运行）：
    blender -b --factory-startup -P blender/build_grass.py
输出：
    assets/textures/grass.png  RGBA：RGB 是颜色，A 是草叶高度（0 贴地，1 最高）；一张图覆盖 TILE 米
    assets/textures/dirt.png   RGBA：RGB 是颜色，A 是高度（土块高，坑洼低）；一张图覆盖 DIRT_TILE 米
    两张图的高度通道用于地面的高度混合：草地和泥土交界处按高低互相穿插，边缘不是一条平滑的线。
草叶画法：先铺一层暗绿的草根底色，再画上万根带锥度的草叶。草根随机分布，按一张疏密噪声取舍，形成一丛丛草和稀疏处；
朝向沿一张缓慢变化的梳向场再加随机偏转；草叶从根到尖逐渐变细、变亮、变高，同一像素取最高的那根草叶的颜色和高度。
另有两张大片噪声控制高矮和偏黄的区域，让草坪不整齐。
泥土画法：几层不同尺度的噪声给出浅黄褐、深褐（潮湿处）和偏红的色块，叠上细颗粒；土块起伏按高度梯度做明暗，
再撒少量干草屑。所有坐标按贴图大小取模，上下左右无缝衔接。
"""
import math
import os

import bpy
import numpy as np

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(PROJECT, "assets", "textures", "grass.png")
DIRT_OUT = os.path.join(PROJECT, "assets", "textures", "dirt.png")
SIZE = 1024
TILE = 4.0                # 一张图覆盖的边长（米），要和地面、壳层草着色器的 tile_size 一致
BLADES_PER_M2 = 210
BLADE_LENGTH = (0.15, 0.38)    # 俯视时草叶的长度（米）
BLADE_WIDTH = (15.0, 24.0)     # 草叶根部宽度（像素，一米 256 像素）
SEED = 5

SOIL = np.array([0.24, 0.35, 0.11])
SOIL_LIGHT = np.array([0.3, 0.42, 0.13])
ROOT = np.array([0.3, 0.44, 0.13])
TIPS = np.array([[0.54, 0.7, 0.22], [0.62, 0.76, 0.26], [0.7, 0.82, 0.32], [0.48, 0.66, 0.2]])
DRY_TIP = np.array([0.78, 0.78, 0.38])

DIRT_TILE = 3.0           # 泥土贴图覆盖的边长（米），要和地面着色器的 dirt_tile 一致
DIRT_LIGHT = np.array([0.66, 0.52, 0.37])
DIRT_MID = np.array([0.56, 0.42, 0.29])
DIRT_DARK = np.array([0.4, 0.29, 0.2])
DIRT_RED = np.array([0.6, 0.4, 0.28])
STRAW_PER_M2 = 8
STRAW_COLOR = np.array([0.78, 0.72, 0.46])


def _tile_noise(size, cells, rng):
    """可平铺的平滑值噪声，cells × cells 个格点。"""
    g = rng.random((cells, cells))
    xs = np.arange(size) * cells / size
    i0 = np.floor(xs).astype(int)
    f = xs - i0
    f = f * f * (3 - 2 * f)
    i1 = (i0 + 1) % cells
    i0 %= cells
    a, b = g[np.ix_(i0, i0)], g[np.ix_(i0, i1)]
    c, d = g[np.ix_(i1, i0)], g[np.ix_(i1, i1)]
    fx, fy = f[None, :], f[:, None]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _fbm(size, base, octaves, rng):
    total = np.zeros((size, size))
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        total += amp * _tile_noise(size, base * 2 ** o, rng)
        norm += amp
        amp *= 0.5
    v = total / norm
    lo, hi = np.percentile(v, 2), np.percentile(v, 98)
    return np.clip((v - lo) / (hi - lo), 0.0, 1.0)


def paint(rng):
    n = SIZE
    ppm = SIZE / TILE
    density = _fbm(n, 3, 3, rng)
    tall = _fbm(n, 4, 3, rng)
    dry = _fbm(n, 2, 3, rng)
    comb = _fbm(n, 2, 2, rng) * math.tau * 1.5

    soil = _fbm(n, 16, 3, rng)[..., None]
    rgb = SOIL + (SOIL_LIGHT - SOIL) * soil
    hgt = np.zeros((n, n))

    count = int(BLADES_PER_M2 * TILE * TILE)
    for x, y in rng.random((count, 2)) * n:
        ix, iy = int(x) % n, int(y) % n
        if rng.random() > 0.3 + 0.7 * density[iy, ix]:
            continue
        ang = comb[iy, ix] + rng.normal(0.0, 0.7)
        length = rng.uniform(*BLADE_LENGTH) * ppm * (0.7 + 0.6 * tall[iy, ix])
        width = rng.uniform(*BLADE_WIDTH)
        hmax = rng.uniform(0.45, 1.0) * (0.5 + 0.5 * tall[iy, ix])
        dx, dy = math.cos(ang) * length, math.sin(ang) * length
        xs = np.arange(math.floor(min(x, x + dx) - width), math.ceil(max(x, x + dx) + width) + 1)
        ys = np.arange(math.floor(min(y, y + dy) - width), math.ceil(max(y, y + dy) + width) + 1)
        px = xs[None, :] + 0.5 - x
        py = ys[:, None] + 0.5 - y
        t = (px * dx + py * dy) / (length * length)
        perp = np.abs(px * dy - py * dx) / length
        tc = np.clip(t, 0.0, 1.0)
        inside = (t >= -0.05) & (t <= 1.0) & (perp <= width * 0.5 * (1.0 - 0.85 * tc))
        h = hmax * (0.3 + 0.7 * tc)
        idx = np.ix_(ys % n, xs % n)
        upd = inside & (h > hgt[idx])
        if not upd.any():
            continue
        tip = DRY_TIP if rng.random() < 0.25 * dry[iy, ix] ** 2 else TIPS[rng.integers(len(TIPS))]
        tip = tip * rng.uniform(0.88, 1.08)
        col = ROOT + (tip - ROOT) * (tc ** 0.8)[..., None]
        col = col * (1.0 - 0.12 * np.clip(perp / (width * 0.5), 0.0, 1.0))[..., None]
        region_rgb = rgb[idx]
        region_rgb[upd] = col[upd]
        rgb[idx] = region_rgb
        region_h = hgt[idx]
        region_h[upd] = h[upd]
        hgt[idx] = region_h

    out = np.ones((n, n, 4))
    out[..., :3] = np.clip(rgb, 0.0, 1.0)
    out[..., 3] = hgt
    return out


def paint_dirt(rng):
    n = SIZE
    ppm = SIZE / DIRT_TILE
    macro = _fbm(n, 3, 4, rng)[..., None]
    damp = _fbm(n, 5, 3, rng)[..., None]
    red = _fbm(n, 4, 3, rng)[..., None]
    grain = _fbm(n, 96, 2, rng)[..., None]
    lumps = _fbm(n, 12, 4, rng)

    rgb = DIRT_MID + (DIRT_LIGHT - DIRT_MID) * macro
    rgb = rgb + (DIRT_RED - rgb) * np.clip((red - 0.55) * 1.6, 0.0, 0.5)
    rgb = rgb + (DIRT_DARK - rgb) * np.clip((damp - 0.6) * 2.0, 0.0, 0.7)
    # 土块起伏：光从左上来，朝光的坡面提亮、背光的坡面压暗
    relief = (np.roll(lumps, 1, axis=1) - np.roll(lumps, -1, axis=1)) + (np.roll(lumps, 1, axis=0) - np.roll(lumps, -1, axis=0))
    relief = np.clip(relief * 6.0, -1.0, 1.0)[..., None]
    rgb = rgb * (0.9 + 0.2 * grain) * (1.0 - 0.14 * relief)
    hgt = 0.15 + 0.3 * lumps + 0.1 * grain[..., 0]

    for _ in range(int(STRAW_PER_M2 * DIRT_TILE * DIRT_TILE)):
        x, y = rng.random(2) * n
        ang = rng.uniform(0, math.tau)
        length = rng.uniform(0.04, 0.1) * ppm
        dx, dy = math.cos(ang) * length, math.sin(ang) * length
        w = rng.uniform(1.2, 2.2)
        xs = np.arange(math.floor(min(x, x + dx) - w), math.ceil(max(x, x + dx) + w) + 1)
        ys = np.arange(math.floor(min(y, y + dy) - w), math.ceil(max(y, y + dy) + w) + 1)
        px = xs[None, :] + 0.5 - x
        py = ys[:, None] + 0.5 - y
        t = (px * dx + py * dy) / (length * length)
        perp = np.abs(px * dy - py * dx) / length
        inside = (t >= 0.0) & (t <= 1.0) & (perp <= w * 0.5)
        idx = np.ix_(ys % n, xs % n)
        region = rgb[idx]
        region[inside] = STRAW_COLOR * rng.uniform(0.85, 1.05)
        rgb[idx] = region
        region_h = hgt[idx]
        region_h[inside] = 0.55
        hgt[idx] = region_h

    out = np.ones((n, n, 4))
    out[..., :3] = np.clip(rgb, 0.0, 1.0)
    out[..., 3] = np.clip(hgt, 0.0, 1.0)
    return out


def _save(name, pixels, path):
    img = bpy.data.images.new(name, SIZE, SIZE, alpha=True)
    img.pixels.foreach_set(pixels[::-1].astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    print(name.upper(), path, "mean rgb", pixels[..., :3].mean(axis=(0, 1)).round(3), "mean height", round(float(pixels[..., 3].mean()), 3))


def main():
    _save("grass", paint(np.random.default_rng(SEED)), OUT)
    _save("dirt", paint_dirt(np.random.default_rng(SEED + 1)), DIRT_OUT)


if __name__ == "__main__":
    main()
