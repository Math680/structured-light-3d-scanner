import argparse
import ctypes
import ctypes.wintypes
import os
import sys
from dataclasses import dataclass
from typing import Tuple

import pygame


MONITOR_DEFAULTTONEAREST = 2
SWP_FRAMECHANGED = 0x0020
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1
GWL_STYLE = -16
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * 32),
    ]


@dataclass
class MonitorBounds:
    x: int
    y: int
    width: int
    height: int


def get_monitor_bounds(index: int) -> MonitorBounds:
    user32 = ctypes.windll.user32
    display_count = user32.GetSystemMetrics(80)
    if display_count < 2:
        raise RuntimeError("Au moins deux ecrans sont requis.")
    if index < 0 or index >= display_count:
        raise RuntimeError(f"Ecran {index + 1} introuvable. Ecrans detectes: {display_count}.")
    enum_monitors = []

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.wintypes.HMONITOR,
        ctypes.wintypes.HDC,
        ctypes.POINTER(RECT),
        ctypes.wintypes.LPARAM,
    )

    def callback(hmonitor, _hdc, _rect, _lparam):
        enum_monitors.append(hmonitor)
        return 1

    user32.EnumDisplayMonitors(0, 0, monitor_enum_proc(callback), 0)
    if index >= len(enum_monitors):
        raise RuntimeError(f"Ecran {index + 1} introuvable. Ecrans detectes: {len(enum_monitors)}.")

    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not user32.GetMonitorInfoW(enum_monitors[index], ctypes.byref(info)):
        raise RuntimeError("Impossible de lire la geometrie de l'ecran cible.")

    rect = info.rcMonitor
    return MonitorBounds(
        x=rect.left,
        y=rect.top,
        width=rect.right - rect.left,
        height=rect.bottom - rect.top,
    )


def force_borderless_fullscreen(window_handle: int, bounds: MonitorBounds) -> None:
    user32 = ctypes.windll.user32
    user32.SetWindowLongW(window_handle, GWL_STYLE, WS_POPUP | WS_VISIBLE)
    user32.SetWindowPos(
        window_handle,
        HWND_TOPMOST,
        bounds.x,
        bounds.y,
        bounds.width,
        bounds.height,
        SWP_FRAMECHANGED | SWP_SHOWWINDOW | SWP_NOACTIVATE,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Projette une suite de franges verticales noir/blanc en plein ecran sur le 2e moniteur."
    )
    parser.add_argument("n", type=int, help="Dernier niveau de subdivision. Le nombre de franges final vaut 2^N.")
    parser.add_argument(
        "interval_ms",
        type=float,
        help="Temps entre deux images projetees, en millisecondes.",
    )
    return parser.parse_args()


def build_pattern_surface(size: Tuple[int, int], n: int) -> pygame.Surface:
    width, height = size
    stripes = 2 ** n
    surface = pygame.Surface((width, height))

    for x in range(width):
        stripe_index = min((x * stripes) // width, stripes - 1)
        is_white = (stripe_index % 2 == 0)
        color = (255, 255, 255) if is_white else (0, 0, 0)
        pygame.draw.line(surface, color, (x, 0), (x, height))

    return surface


def main() -> int:
    args = parse_args()
    if args.n < 1:
        raise SystemExit("N doit etre >= 1.")
    if args.interval_ms <= 0:
        raise SystemExit("L'intervalle doit etre > 0 ms.")
    if sys.platform != "win32":
        raise SystemExit("Ce script cible Windows pour garantir le plein ecran sur le 2e ecran.")

    ctypes.windll.user32.SetProcessDPIAware()
    bounds = get_monitor_bounds(1)

    os.environ["SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS"] = "0"
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{bounds.x},{bounds.y}"

    pygame.init()
    pygame.display.init()
    pygame.mouse.set_visible(False)

    flags = pygame.NOFRAME
    screen = pygame.display.set_mode((bounds.width, bounds.height), flags)
    pygame.display.set_caption("Franges verticales")

    window_handle = pygame.display.get_wm_info()["window"]
    force_borderless_fullscreen(window_handle, bounds)

    clock = pygame.time.Clock()
    frame_interval = args.interval_ms / 1000.0
    next_change_at = frame_interval
    current_n = 1

    patterns = {
        n: build_pattern_surface((bounds.width, bounds.height), n)
        for n in range(1, args.n + 1)
    }

    while True:
        now = pygame.time.get_ticks() / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return 0
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                return 0
            if hasattr(pygame, "WINDOWFOCUSLOST") and event.type == pygame.WINDOWFOCUSLOST:
                force_borderless_fullscreen(window_handle, bounds)

        if current_n < args.n and now >= next_change_at:
            current_n += 1
            next_change_at = now + frame_interval

        screen.blit(patterns[current_n], (0, 0))
        pygame.display.flip()
        force_borderless_fullscreen(window_handle, bounds)
        clock.tick(120)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        pygame.quit()
