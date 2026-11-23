"""Terra arada procedural: sulcos alinhados à grade, período de um tile.

tilled_texture(grain, furrows=3, axis='u') -> Image 256x256 periódica
(grain: textura de IA usada só para o grão). Projetar com grid=1.
"""
import numpy as np
from PIL import Image


def tilled_texture(grain, furrows=3, axis="u", size=256, depth=0.45, wet=0.0, seed=0):
    g = np.asarray(grain.convert("RGB").resize((size, size)), float)
    lum = g.mean(2, keepdims=True)
    g = g / (lum.mean() + 1e-6)  # grão normalizado
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:size, 0:size] / size
    t = ys if axis == "u" else xs  # sulcos correm ao longo do outro eixo
    # leve ondulação para não ficar régua
    t = t + 0.012 * np.sin(2 * np.pi * (xs if axis == "u" else ys) * 2 + rng.uniform(0, 6))
    ph = 2 * np.pi * furrows * t
    h = np.cos(ph)  # altura do camalhão
    slope = -np.sin(ph)  # face voltada para a luz (cima) clareia
    base = np.array([112.0, 72.0, 50.0]) * (1 - 0.45 * wet) + np.array([20, 10, 25]) * wet
    shade = 1 + depth * (0.55 * h + 0.45 * slope)
    out = base * shade[..., None] * (0.85 + 0.15 * g)
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))
