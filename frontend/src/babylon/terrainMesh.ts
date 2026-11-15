import type { TerrainMeshResponse } from '../api/types';

/** Geometry is already sampled in selected-site ENU metres by lunar_engine. */
export interface VerifiedTerrainMesh {
  positions: number[];
  indices: number[];
  extentM: number;
}

export function verifyTerrainMesh(mesh: TerrainMeshResponse): VerifiedTerrainMesh {
  if (mesh.coordinate_frame !== 'local_east_up_north' ||
      mesh.metadata.coordinate_frame !== 'local_east_up_north' ||
      mesh.metadata.vertical_exaggeration !== 1 ||
      mesh.metadata.center_is_local_origin !== true ||
      mesh.metadata.datum_confirmed !== true ||
      mesh.metadata.visual_only !== true) {
    throw new Error('Unsupported terrain coordinates, datum, scale or provenance.');
  }
  if (!['complete', 'partial_coverage'].includes(mesh.status) ||
      !Number.isInteger(mesh.grid_side) || mesh.grid_side < 2 || mesh.grid_side > 65 ||
      !Number.isInteger(mesh.valid_samples) || !Number.isInteger(mesh.requested_samples) ||
      mesh.requested_samples !== mesh.grid_side ** 2 ||
      mesh.valid_samples !== mesh.vertices.length || mesh.valid_samples < 3 ||
      mesh.valid_samples > mesh.requested_samples ||
      (mesh.status === 'complete' && mesh.valid_samples !== mesh.requested_samples) ||
      !Number.isFinite(mesh.center_elevation_m) ||
      !Number.isFinite(mesh.radius_m) || mesh.radius_m < 160 || mesh.radius_m > 5000 ||
      !Number.isFinite(mesh.sample_step_m) || mesh.sample_step_m <= 0 ||
      !Array.isArray(mesh.vertices) || !Array.isArray(mesh.indices)) {
    throw new Error('Invalid terrain mesh dimensions or coverage.');
  }
  if (mesh.indices.length < 3 || mesh.indices.length % 3 !== 0 ||
      mesh.indices.length > 6 * (mesh.grid_side - 1) ** 2) {
    throw new Error('Invalid terrain triangle count.');
  }
  const positions: number[] = [];
  for (const xyz of mesh.vertices) {
    if (!Array.isArray(xyz) || xyz.length !== 3 || xyz.some(v => !Number.isFinite(v))) {
      throw new Error('Terrain contains invalid vertex coordinates.');
    }
    // Prevent rogue/malformed responses from creating enormous GPU geometry.
    if (Math.abs(xyz[0]) > 12000 || Math.abs(xyz[1]) > 12000 || Math.abs(xyz[2]) > 12000) {
      throw new Error('Terrain vertex lies outside bounded site footprint.');
    }
    positions.push(xyz[0], xyz[1], xyz[2]);
  }
  for (const index of mesh.indices) {
    if (!Number.isInteger(index) || index < 0 || index >= mesh.vertices.length) {
      throw new Error('Terrain contains invalid triangle indices.');
    }
  }
  const used = new Set(mesh.indices);
  if (used.size < 3) throw new Error('Terrain contains no usable triangles.');
  return { positions, indices: [...mesh.indices], extentM: mesh.radius_m };
}
