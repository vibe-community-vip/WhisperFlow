# -*- coding: utf-8 -*-
"""Render del indicador flotante con Pillow (una imagen por frame, no widgets Tk).

Por qué Pillow y no primitivas de ``tkinter.Canvas``:

  - **El texto**. En Windows, Tk dibuja con ClearType (antialiasing sub-pixel que
    asume un fondo sólido conocido); por eso el overlay no podía usar ``-alpha``
    sin que salieran flecos de color. Pillow rasteriza el texto en escala de
    grises **dentro de la imagen que nosotros componemos**, así que ese problema
    desaparece y además podemos usar pesos finos (Segoe UI Semilight) y
    *tracking* (espaciado entre letras), imposibles con la fuente de Tk.
  - **La luz**. Los degradados, el halo del punto de estado y el resplandor de
    las barras se hacen con desenfoque gaussiano; ``Canvas`` no tiene nada
    equivalente (solo formas planas de color liso, que es lo que se veía "duro").

Rendimiento: el fondo (degradado + borde + texto) se rasteriza **una vez por
estado** y se cachea; por frame solo se pegan sprites RGBA pequeños ya
pre-renderizados (barras y punto). Ver ``OverlayRenderer.frame``.

La imagen se devuelve en RGB **aplanada sobre ``KEY_COLOR``**, que en Windows es el
color que ``-transparentcolor`` vuelve invisible (de ahí las esquinas redondeadas
sin ``-alpha``). En Mac/Linux el backend usa ``-alpha`` y el mismo KEY_COLOR de fondo.

**Por qué KEY_COLOR es casi negro y no magenta**: el colorkey de Windows solo borra
los píxeles *exactamente* iguales al color clave. El borde redondeado es
antialiaseado, así que sus píxeles son una mezcla entre la píldora y el fondo sobre
el que se aplanó — mezclas que NO son el color clave y por lo tanto se ven. Con
magenta eso deja un fleco fucsia alrededor de la cápsula (verificado). Aplanando
sobre un casi-negro, ese mismo fleco queda como un borde oscuro suave: invisible
sobre fondos oscuros y con aspecto de sombra sobre fondos claros.
"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# --- Geometría -------------------------------------------------------------
PILL_W, PILL_H = 236, 34
PILL_RADIUS = PILL_H // 2          # cápsula completa
PAD_LEFT, PAD_RIGHT = 15, 14
DOT_R = 3.0                        # radio del punto sólido
DOT_GLOW_R = 11.0                  # alcance del halo alrededor del punto
TEXT_GAP = 11                      # separación punto -> texto
BAR_COUNT = 5
BAR_W, BAR_GAP = 2.0, 3.6
BAR_MIN_H, BAR_MAX_H = 2.0, 15.0
BARS_AREA_W = BAR_COUNT * BAR_W + (BAR_COUNT - 1) * BAR_GAP

SS = 4           # supersampling: se dibuja a 4x y se reduce -> bordes suaves
_BAR_STEPS = 28  # sprites de barra pre-renderizados (altura cuantizada)
_DOT_STEPS = 4   # niveles de intensidad del halo del punto

# --- Paleta ----------------------------------------------------------------
KEY_COLOR = (1, 0, 1)              # casi negro: lo que el colorkey vuelve invisible
PILL_TOP = (36, 37, 44)            # degradado del cuerpo, arriba
PILL_BOTTOM = (20, 21, 25)         #                        abajo
TEXT_COLOR = (170, 176, 189)       # gris frío: legible pero que no grita
BORDER_ALPHA = 0.13                # el borde es el color de estado MUY diluido
SHEEN_ALPHA = 0.075                # brillo de 1px en el borde superior (vidrio)
RIM_ALPHA = 0.12                   # halo interior contra el borde (muy sutil)
BLOOM_ALPHA = 0.20                 # luz difusa detrás del punto y de las barras

STATE_COLOR = {
    "recording":  (134, 216, 239),   # celeste
    "hands_free": (182, 167, 240),   # lavanda
    "processing": (239, 201, 138),   # ámbar
    "loading":    (154, 160, 166),   # gris
}
STATE_TEXT = {
    "recording":  "grabando",
    "hands_free": "manos libres",
    "processing": "procesando",
    "loading":    "cargando modelo",
}

# Tipografía: fina y con tracking. Cada SO tiene su equivalente "semilight".
# Ojo con macOS: SFNSText.ttf existía hasta Catalina; de Big Sur en adelante la fuente
# del sistema es SFNS.ttf. Se listan las dos, y varias más, porque si NINGUNA carga el
# fallback es la fuente de mapa de bits de Pillow y el indicador se ve roto.
_FONT_CANDIDATES = {
    "win32": [r"C:\Windows\Fonts\segoeuisl.ttf", r"C:\Windows\Fonts\segoeuil.ttf",
              r"C:\Windows\Fonts\segoeui.ttf"],
    "darwin": ["/System/Library/Fonts/SFNS.ttf",              # Big Sur en adelante
               "/System/Library/Fonts/SFNSText.ttf",          # hasta Catalina
               "/System/Library/Fonts/SFNSDisplay.ttf",
               "/System/Library/Fonts/HelveticaNeue.ttc",
               "/System/Library/Fonts/Helvetica.ttc",
               "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "linux": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
              "/usr/share/fonts/TTF/DejaVuSans.ttf",          # Arch
              "/usr/share/fonts/dejavu/DejaVuSans.ttf",       # Fedora
              "/usr/share/fonts/noto/NotoSans-Regular.ttf",
              "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"],
}
# Si ninguna de las rutas de arriba existe (distros con otro layout), se busca
# cualquier .ttf en estos directorios antes de rendirse al fallback de mapa de bits.
_FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts",
              "/System/Library/Fonts", "/Library/Fonts"]
FONT_SIZE = 11        # px del render final (se multiplica por SS al rasterizar)
TRACKING = 1.5        # espaciado extra entre letras, en px finales


def _load_font(size_px):
    plat = "win32" if sys.platform == "win32" else ("darwin" if sys.platform == "darwin" else "linux")
    for path in _FONT_CANDIDATES.get(plat, []):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size_px)
            except Exception:
                continue
    # Red de seguridad: la primera .ttf utilizable que aparezca en el sistema. Fea
    # quizá, pero legible — mejor que la fuente de mapa de bits de Pillow.
    for base in _FONT_DIRS:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for name in sorted(files):
                if name.lower().endswith(".ttf"):
                    try:
                        return ImageFont.truetype(os.path.join(root, name), size_px)
                    except Exception:
                        continue
    print("[whisperflow] no se encontró ninguna fuente TrueType; el indicador usará "
          "la fuente por defecto de Pillow y se verá peor.", flush=True)
    try:
        return ImageFont.load_default(size_px)
    except Exception:
        return ImageFont.load_default()


def _mix(a, b, t):
    """Interpola dos colores RGB (t=0 -> a, t=1 -> b)."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _draw_tracked_text(draw, xy, text, font, fill, tracking):
    """Dibuja el texto letra por letra agregando ``tracking`` px entre caracteres.
    Pillow no tiene letter-spacing, y el tracking es justo lo que hace que un
    texto chico se lea "de interfaz" y no "de sistema"."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += draw.textlength(ch, font=font) + tracking
    return x


class OverlayRenderer:
    """Compone el frame del indicador. Un objeto por overlay (vive en el hilo de Tk)."""

    def __init__(self):
        self._bg_cache = {}     # state -> Image RGB del fondo (con texto), a 1x
        self._bar_cache = {}    # (state, step) -> sprite RGBA de una barra
        self._dot_cache = {}    # (state, step) -> sprite RGBA del punto con halo
        self._font = _load_font(int(FONT_SIZE * SS))

    # --- fondo (una vez por estado) ---
    def _build_bg(self, state):
        color = STATE_COLOR.get(state, STATE_COLOR["recording"])
        w, h, r = PILL_W * SS, PILL_H * SS, PILL_RADIUS * SS

        # La cápsula se construye con alpha REAL (transparente afuera) y recién al
        # final se aplana sobre KEY_COLOR: así el borde antialiaseado se degrada
        # hacia el casi-negro del key y no deja fleco de color.
        shape = Image.new("L", (w, h), 0)
        ImageDraw.Draw(shape).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)

        # 1) Cuerpo: degradado vertical recortado a la cápsula.
        grad = Image.new("RGB", (1, h))
        gpx = grad.load()
        for y in range(h):
            gpx[0, y] = _mix(PILL_TOP, PILL_BOTTOM, y / max(1, h - 1))
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        img.paste(grad.resize((w, h), Image.NEAREST), (0, 0), shape)

        # 2) Luz difusa: en vez de un anillo neón uniforme (que se veía "de tubo"),
        #    la luz nace de los elementos vivos — el punto de estado y las barras —
        #    y se apaga hacia el centro. Recortada a la cápsula: con colorkey no hay
        #    alpha real afuera, así que un halo externo sería imposible.
        bloom = Image.new("L", (w, h), 0)
        bd = ImageDraw.Draw(bloom)
        dot_cx = (PAD_LEFT + DOT_R) * SS
        bars_cx = (PILL_W - PAD_RIGHT - BARS_AREA_W / 2) * SS
        for cx, rad in ((dot_cx, 15 * SS), (bars_cx, 17 * SS)):
            bd.ellipse([cx - rad, h / 2 - rad, cx + rad, h / 2 + rad], fill=255)
        bloom = bloom.filter(ImageFilter.GaussianBlur(7.0 * SS))
        bloom = bloom.point(lambda v: int(v * BLOOM_ALPHA))
        bloom = Image.composite(bloom, Image.new("L", (w, h), 0), shape)
        img.paste(Image.new("RGB", (w, h), color), (0, 0), bloom)

        # 3) Halo interior contra el borde: da sensación de vidrio iluminado por dentro.
        rim = Image.new("L", (w, h), 0)
        ImageDraw.Draw(rim).rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                                              outline=255, width=int(2.4 * SS))
        rim = rim.filter(ImageFilter.GaussianBlur(2.6 * SS)).point(lambda v: int(v * RIM_ALPHA))
        rim = Image.composite(rim, Image.new("L", (w, h), 0), shape)
        img.paste(Image.new("RGB", (w, h), color), (0, 0), rim)

        d = ImageDraw.Draw(img, "RGBA")

        # 4) Borde: color de estado diluido casi hasta el fondo -> línea tenue.
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                            outline=color + (int(255 * BORDER_ALPHA),),
                            width=max(1, int(1.0 * SS)))
        # 5) Brillo de vidrio: el filo SUPERIOR de la cápsula, blanco casi
        #    imperceptible, apagándose hacia abajo. (Ojo: no sirve ``arc`` sobre el
        #    bounding box — dibuja la elipse inscrita, que cruza la píldora en
        #    diagonal en vez de seguir su borde.) Se hace enmascarando el contorno
        #    redondeado con un degradado vertical.
        sheen = Image.new("L", (w, h), 0)
        ImageDraw.Draw(sheen).rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                                                outline=255, width=max(1, int(1.0 * SS)))
        fade = Image.new("L", (1, h))
        fpx = fade.load()
        for y in range(h):
            t = min(1.0, y / (h * 0.45))
            fpx[0, y] = int(255 * (1.0 - t) ** 2)
        sheen = ImageChops.multiply(sheen, fade.resize((w, h), Image.NEAREST))
        sheen = sheen.point(lambda v: int(v * SHEEN_ALPHA))
        img.paste(Image.new("RGB", (w, h), (255, 255, 255)), (0, 0), sheen)

        # 6) Texto (rasterizado por Pillow, no por Tk -> sin ClearType, con tracking).
        text = STATE_TEXT.get(state, STATE_TEXT["recording"])
        tx = (PAD_LEFT + DOT_R * 2 + TEXT_GAP) * SS
        baseline = (PILL_H / 2 + FONT_SIZE * 0.36) * SS
        _draw_tracked_text(d, (tx, baseline), text, self._font, TEXT_COLOR, TRACKING * SS)

        small = img.resize((PILL_W, PILL_H), Image.LANCZOS)
        flat = Image.new("RGB", (PILL_W, PILL_H), KEY_COLOR)
        flat.paste(small, (0, 0), small.getchannel("A"))
        return flat

    def _bg(self, state):
        if state not in self._bg_cache:
            self._bg_cache[state] = self._build_bg(state)
        return self._bg_cache[state]

    # --- sprites dinámicos (barras y punto) ---
    def _bar_sprite(self, state, step):
        key = (state, step)
        if key in self._bar_cache:
            return self._bar_cache[key]
        color = STATE_COLOR.get(state, STATE_COLOR["recording"])
        height = BAR_MIN_H + (BAR_MAX_H - BAR_MIN_H) * (step / (_BAR_STEPS - 1))
        pad = 5                                    # margen para que el halo respire
        w = int(BAR_W + pad * 2)
        h = int(BAR_MAX_H + pad * 2)
        W, H = w * SS, h * SS

        shape = Image.new("L", (W, H), 0)
        cx, cy = W / 2, H / 2
        half = height * SS / 2
        ImageDraw.Draw(shape).rounded_rectangle(
            [cx - BAR_W * SS / 2, cy - half, cx + BAR_W * SS / 2, cy + half],
            radius=BAR_W * SS / 2, fill=255)

        halo = shape.filter(ImageFilter.GaussianBlur(2.2 * SS)).point(lambda v: int(v * 0.55))
        alpha = Image.new("L", (W, H), 0)
        alpha.paste(halo, (0, 0))
        alpha.paste(shape, (0, 0), shape)          # el núcleo sólido va sobre el halo

        sprite = Image.new("RGBA", (W, H), color + (0,))
        sprite.putalpha(alpha)
        sprite = sprite.resize((w, h), Image.LANCZOS)
        self._bar_cache[key] = sprite
        return sprite

    def _dot_sprite(self, state, step):
        """``step`` 0..3: intensidad del halo (el punto respira mientras graba)."""
        key = (state, step)
        if key in self._dot_cache:
            return self._dot_cache[key]
        color = STATE_COLOR.get(state, STATE_COLOR["recording"])
        size = int(DOT_GLOW_R * 2)
        S = size * SS
        c = S / 2

        core = Image.new("L", (S, S), 0)
        ImageDraw.Draw(core).ellipse([c - DOT_R * SS, c - DOT_R * SS,
                                      c + DOT_R * SS, c + DOT_R * SS], fill=255)
        bloom_r = (DOT_R + 1.6) * SS
        bloom = Image.new("L", (S, S), 0)
        ImageDraw.Draw(bloom).ellipse([c - bloom_r, c - bloom_r, c + bloom_r, c + bloom_r], fill=255)
        intensity = 0.30 + 0.16 * step
        bloom = bloom.filter(ImageFilter.GaussianBlur(2.6 * SS)).point(lambda v: int(v * intensity))

        alpha = Image.new("L", (S, S), 0)
        alpha.paste(bloom, (0, 0))
        alpha.paste(core, (0, 0), core)

        sprite = Image.new("RGBA", (S, S), color + (0,))
        sprite.putalpha(alpha)
        sprite = sprite.resize((size, size), Image.LANCZOS)
        self._dot_cache[key] = sprite
        return sprite

    # --- frame completo ---
    def frame(self, state, bar_levels, dot_step=0):
        """``bar_levels``: lista de BAR_COUNT floats 0..1. Devuelve una imagen RGB."""
        img = self._bg(state).copy()

        dot_cx = PAD_LEFT + DOT_R
        dot = self._dot_sprite(state, max(0, min(_DOT_STEPS - 1, int(dot_step))))
        img.paste(dot, (int(dot_cx - dot.width / 2), int(PILL_H / 2 - dot.height / 2)), dot)

        bars_x0 = PILL_W - PAD_RIGHT - BARS_AREA_W
        for i in range(BAR_COUNT):
            lvl = max(0.0, min(1.0, bar_levels[i] if i < len(bar_levels) else 0.0))
            step = int(round(lvl * (_BAR_STEPS - 1)))
            sprite = self._bar_sprite(state, step)
            cx = bars_x0 + i * (BAR_W + BAR_GAP) + BAR_W / 2
            img.paste(sprite, (int(cx - sprite.width / 2), int(PILL_H / 2 - sprite.height / 2)), sprite)
        return img

    def prewarm(self):
        """Rasteriza fondos y sprites antes de mostrarse (evita el tirón del 1er frame)."""
        for state in STATE_COLOR:
            self._bg(state)
            for step in range(_BAR_STEPS):
                self._bar_sprite(state, step)
            for step in range(_DOT_STEPS):
                self._dot_sprite(state, step)
