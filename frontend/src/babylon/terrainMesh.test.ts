import { describe, expect, it } from 'vitest';
import { verifyTerrainMesh } from './terrainMesh';
import type { TerrainMeshResponse } from '../api/types';

const sample: TerrainMeshResponse = {
  status: 'complete', coordinate_frame: 'local_east_up_north',
  latitude_deg: -89.5, longitude_deg: 45, center_elevation_m: -393.18,
  radius_m: 160, sample_step_m: 320, grid_side: 2,
  valid_samples: 4, requested_samples: 4,
  vertices: [[-160, -1, 160], [160, 2, 160], [-160, -2, -160], [160, 0, -160]],
  indices: [0, 1, 2, 1, 3, 2],
  metadata: { coordinate_frame: 'local_east_up_north', vertical_exaggeration: 1,
    center_is_local_origin: true, datum_confirmed: true, visual_only: true,
    dataset_id: 'LOLA-fixture', pixel_size_m: 80, reference_frame: 'MOON_ME_DE421',
    frame_alignment_note: 'fixture' },
};

describe('real LOLA mesh contract validation', () => {
  it('preserves ENU order, metres, and triangle connectivity', () => {
    const mesh = verifyTerrainMesh(sample);
    expect(mesh.positions).toEqual(sample.vertices.flat());
    expect(mesh.indices).toEqual(sample.indices);
    expect(mesh.extentM).toBe(160);
  });
  it('rejects invented elevation scale and unchecked provenance', () => {
    expect(() => verifyTerrainMesh({ ...sample, metadata: { ...sample.metadata, vertical_exaggeration: 4 } })).toThrow();
    expect(() => verifyTerrainMesh({ ...sample, metadata: { ...sample.metadata, datum_confirmed: false } })).toThrow();
  });
  it('rejects out-of-bounds triangle indices or missing geometry', () => {
    expect(() => verifyTerrainMesh({ ...sample, indices: [0, 1, 4] })).toThrow();
    expect(() => verifyTerrainMesh({ ...sample, indices: [] })).toThrow();
  });
  it('rejects nonfinite positions or oversized geometry', () => {
    expect(() => verifyTerrainMesh({ ...sample, vertices: [[NaN, 0, 0], ...sample.vertices.slice(1)] })).toThrow();
    expect(() => verifyTerrainMesh({ ...sample, grid_side: 1000 })).toThrow();
  });
  it('allows partial terrain without fabricating missing pixels', () => {
    const partial: TerrainMeshResponse = { ...sample, status: 'partial_coverage',
      valid_samples: 3, vertices: sample.vertices.slice(0, 3), indices: [0, 1, 2] };
    expect(verifyTerrainMesh(partial).positions).toHaveLength(9);
  });
});
