Place your Kenney tileset PNG here as:

    tileset.png

If the file is not present, the UI falls back to solid colored squares.

Recommended Kenney assets (free, CC0):
  https://kenney.nl/assets/tiny-town       (16x16 tiles)
  https://kenney.nl/assets/1-bit-pack      (16x16, top-down)

After placing the file, open UI/src/components/WorldGrid.tsx and update
the SPRITE_MAP constants at the top of the file to point at the correct
source rectangles in your chosen sheet.
