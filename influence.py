#!/usr/bin/env python3
"""
sgf_influence_map.py

Generate a coloured “influence map” from a Go SGF file.

The map shows, for every board intersection, a blended colour that
represents the influence of the two players:

* **Green** (100 % = #00ff00)  – black stones
* **Red** (100 % = #ff0000) – white stones

The influence percentage for a colour at a point is

    p = 1 / (d + 1) * 100

where *d* is the minimum number of orthogonal steps (Manhattan distance)
required to connect the point to the nearest stone of the same colour.
The two percentages are blended linearly and drawn as a semi‑transparent
square (50 % opacity) on the board.

Dependencies
------------
* sgfmill – SGF parsing (`pip install sgfmill`)
* Pillow  – image generation (`pip install pillow`)

Usage
-----
    python sgf_influence_map.py <input.sgf> [output.png] [--cell-size N]

If *output.png* is omitted the script writes `<input>_influence.png`.
*--cell-size* controls the pixel size of a board intersection
(default = 30 px).

Author: Goose (Block) – 2025
"""

import argparse
import math
import os
from pathlib import Path

from sgfmill import sgf, sgf_moves
from sgfmill import boards as sgf_board
from PIL import Image, ImageDraw

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------

def manhattan(p1, p2):
    """Return Manhattan distance between two (col,row) points."""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def colour_from_percentages(black_pct, white_pct):
    """
    Blend the two percentages into an RGB tuple.

    * 100 % black (now shown as **green**) → (0, 255, 0)
    * 100 % white (now shown as **red**)   → (255, 0, 0)

    The blending is linear:
        red   = white_pct/100 * 255
        green = black_pct/100 * 255
        blue  = 0 (unused)
    """
    red = int(round(white_pct * 2.55))
    green = int(round(black_pct * 2.55))
    blue = 0
    # Clamp just in case
    red = max(0, min(255, red))
    green = max(0, min(255, green))
    return (red, green, blue)


def compute_influence(board, size):
    """
    For each point on the board return a tuple (black_pct, white_pct, rgb).
    """
    # Use list_occupied_points to get stones
    occupied = board.list_occupied_points()
    black_stones = [pt for colour, pt in occupied if colour == "b"]
    white_stones = [pt for colour, pt in occupied if colour == "w"]

    # Pre‑compute distances – the board size is tiny (≤ 19) so O(N²) is fine.
    influence = {}
    for row in range(size):
        for col in range(size):
            pt = (col, row)

            # --- Black stones (green) ---
            if black_stones:
                d_black = min(manhattan(pt, s) for s in black_stones)
                black_pct = 1.0 / (d_black + 1) * 100.0
            else:
                black_pct = 0.0

            # --- White stones (red) ---
            if white_stones:
                d_white = min(manhattan(pt, s) for s in white_stones)
                white_pct = 1.0 / (d_white + 1) * 100.0
            else:
                white_pct = 0.0

            rgb = colour_from_percentages(black_pct, white_pct)
            influence[pt] = (black_pct, white_pct, rgb)

    return influence


def draw_board(size, cell_sz, margin):
    """
    Return a Pillow Image with a black background only.
    Grid lines will be drawn later by ``draw_grid``.
    """
    img_sz = size * cell_sz + 2 * margin
    img = Image.new("RGBA", (img_sz, img_sz), (0, 0, 0, 255))
    return img

def draw_grid(img, size, cell_sz, margin):
    """Draw white grid lines and star points on *img* (in‑place)."""
    draw = ImageDraw.Draw(img)
    # White grid lines
    for i in range(size):
        x0 = margin + i * cell_sz
        y0 = margin
        x1 = x0
        y1 = margin + (size - 1) * cell_sz
        draw.line((x0, y0, x1, y1), fill=(255, 255, 255), width=1)

        x0 = margin
        y0 = margin + i * cell_sz
        x1 = margin + (size - 1) * cell_sz
        y1 = y0
        draw.line((x0, y0, x1, y1), fill=(255, 255, 255), width=1)

    # Star points (19×19 board only – you can extend this table if needed)
    star_coords = {
        9: [(4, 4), (4, 8), (8, 4), (8, 8)],
        13: [(3, 3), (3, 9), (9, 3), (9, 9), (6, 6)],
        19: [(3, 3), (3, 9), (3, 15),
             (9, 3), (9, 9), (9, 15),
             (15, 3), (15, 9), (15, 15)],
    }.get(size, [])
    radius = cell_sz // 6
    for (c, r) in star_coords:
        cx = margin + c * cell_sz
        cy = margin + r * cell_sz
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(255, 255, 255),
        )
    # No return needed – img modified in place


def overlay_influence(img, influence, size, cell_sz, margin, alpha=128):
    """
    Paint a semi‑transparent square on each intersection according to its colour.
    """
    draw = ImageDraw.Draw(img, "RGBA")
    for (col, row), (_, _, rgb) in influence.items():
        x0 = margin + col * cell_sz - cell_sz // 2
        y0 = margin + row * cell_sz - cell_sz // 2
        x1 = x0 + cell_sz
        y1 = y0 + cell_sz
        draw.rectangle(
            (x0, y0, x1, y1),
            fill=rgb + (alpha,),
        )
    return img


def draw_stones(img, board, size, cell_sz, margin):
    """
    Draw the actual black/white stones on top of the influence map.
    """
    draw = ImageDraw.Draw(img)
    stone_radius = cell_sz // 2 - 2
    # Draw stones using board.list_occupied_points()
    occupied = board.list_occupied_points()
    for (col, row) in [pt for colour, pt in occupied if colour == "b"]:
        cx = margin + col * cell_sz
        cy = margin + row * cell_sz
        draw.ellipse(
            (cx - stone_radius, cy - stone_radius,
             cx + stone_radius, cy + stone_radius),
            fill=(0, 0, 0),
            outline=(0, 0, 0),
        )
    for (col, row) in [pt for colour, pt in occupied if colour == "w"]:
        cx = margin + col * cell_sz
        cy = margin + row * cell_sz
        draw.ellipse(
            (cx - stone_radius, cy - stone_radius,
             cx + stone_radius, cy + stone_radius),
            fill=(255, 255, 255),
            outline=(0, 0, 0),
        )
    return img

# ----------------------------------------------------------------------
# Main routine
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Create an influence‑map PNG from an SGF file and generate a video."
    )
    parser.add_argument(
        "--video",
        default="influence.mp4",
        help="Output video filename (default: influence.mp4)",
    )
    parser.add_argument("sgf_file", type=Path, help="Path to the SGF file")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Path for the generated PNG (default: <sgf>_influence.png)",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=30,
        help="Pixel size of a board intersection (default: 30)",
    )
    args = parser.parse_args()

    if not args.sgf_file.is_file():
        parser.error(f"File not found: {args.sgf_file}")

    # ------------------------------------------------------------------
    # Load & play SGF
    # ------------------------------------------------------------------
    with open(args.sgf_file, "rb") as f:
        sgf_data = f.read()

    try:
        sgf_game = sgf.Sgf_game.from_bytes(sgf_data)
    except Exception as exc:
        parser.error(f"Could not parse SGF: {exc}")

    board_size = sgf_game.get_size()
    board = sgf_board.Board(board_size)

    # Retrieve the move sequence (we will replay them step‑by‑step)
    board, moves = sgf_moves.get_setup_and_moves(sgf_game)

    # ------------------------------------------------------------------
    # Prepare frames directory
    # ------------------------------------------------------------------
    import shutil
    import subprocess
    frames_dir = Path(f"{args.sgf_file.stem}_frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Replay moves and generate a frame after each move
    # ------------------------------------------------------------------
    CELL = args.cell_size
    MARGIN = CELL  # enough space for outer border

    for idx, (color, move) in enumerate(moves, start=1):
        if move is None:
            # Pass - still generate a frame representing no change
            pass
        else:
            col, row = move
            try:
                board.play(row, col, color)
            except Exception as exc:
                parser.error(f"Invalid move {sgf.format_point(move)} for {color}: {exc}")
        # Compute influence for current board state
        influence = compute_influence(board, board_size)
        # Render image for this state
        img = draw_board(board_size, CELL, MARGIN)
        img = overlay_influence(img, influence, board_size, CELL, MARGIN, alpha=255)
        draw_grid(img, board_size, CELL, MARGIN)
        img = draw_stones(img, board, board_size, CELL, MARGIN)
        # Save frame as PNG with zero‑padded index
        frame_path = frames_dir / f"{idx:04d}.png"
        img.save(frame_path)
        print(f"Saved frame {frame_path}")

    # ------------------------------------------------------------------
    # Create video from frames using ffmpeg (1 fps by default)
    # ------------------------------------------------------------------
    ffmpeg_cmd = f"ffmpeg -y -framerate 1 -i {frames_dir}/%04d.png -c:v libx264 -pix_fmt yuv420p {args.video}"
    print("Running ffmpeg to generate video...")
    result = subprocess.run(ffmpeg_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print("ffmpeg failed:", result.stderr)
    else:
        print(f"Video saved to {args.video}")


if __name__ == "__main__":
    main()
