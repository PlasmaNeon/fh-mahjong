// Tile ids arrive from three sources with different JS types: proto decoding
// (number), paipu JSON (number|string), and DOM data attributes (string).
// Comparison is therefore string-based and null-safe.
export function tileIdsEqual(left: unknown, right: unknown): boolean {
  if (left == null || right == null) return false
  return String(left) === String(right)
}
