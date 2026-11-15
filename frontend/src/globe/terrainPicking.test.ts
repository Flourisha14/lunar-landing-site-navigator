import { describe, expect, it } from 'vitest';
import { isMoonTilesetPick } from './terrainPicking';

describe('Cesium Moon terrain-hit gating', () => {
  const tileset = {};

  it('accepts a feature belonging to the active lunar tileset', () => {
    expect(isMoonTilesetPick({ primitive: tileset }, tileset)).toBe(true);
    expect(isMoonTilesetPick({ tileset }, tileset)).toBe(true);
  });

  it('rejects empty scene picks and missing tile content', () => {
    expect(isMoonTilesetPick(undefined, tileset)).toBe(false);
    expect(isMoonTilesetPick(null, tileset)).toBe(false);
    expect(isMoonTilesetPick({}, tileset)).toBe(false);
  });

  it('rejects markers and primitives belonging to another dataset', () => {
    expect(isMoonTilesetPick({ primitive: {} }, tileset)).toBe(false);
    expect(isMoonTilesetPick({ tileset: {} }, tileset)).toBe(false);
  });

  it('never compares by an asset id or a string label', () => {
    expect(isMoonTilesetPick({ primitive: '2684829' }, tileset)).toBe(false);
  });
});