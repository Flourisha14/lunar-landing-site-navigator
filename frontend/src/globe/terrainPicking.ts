/**
 * A terrain hit must belong to the active lunar tileset, not Cesium's
 * selected-site entity, another primitive, or empty canvas space.
 * The depth coordinate is read separately via Scene.pickPosition().
 */
export function isMoonTilesetPick(picked: unknown, activeTileset: object): boolean {
  if (typeof picked !== 'object' || picked === null) return false;
  const candidate = picked as { primitive?: unknown; tileset?: unknown };
  return candidate.primitive === activeTileset || candidate.tileset === activeTileset;
}