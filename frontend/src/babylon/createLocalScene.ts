import {
  ArcRotateCamera, Color3, Color4, DirectionalLight, Engine,
  HemisphericLight, Mesh, Scene, StandardMaterial, Vector3, VertexData,
} from '@babylonjs/core';
import type { SolarLightVector } from './solarLighting';
import { verifyTerrainMesh } from './terrainMesh';
import type { TerrainMeshResponse } from '../api/types';

export interface LocalSceneHandle {
  setSun: (solar: SolarLightVector | null) => void;
  setTerrain: (terrain: TerrainMeshResponse | null) => void;
  dispose: () => void;
}

/** Uses real LOLA vertices in metres, with no generated ground or rock geometry. */
export function createLocalScene(canvas: HTMLCanvasElement): LocalSceneHandle {
  const engine = new Engine(canvas, true, { stencil: true, preserveDrawingBuffer: false });
  let scene: Scene | null = null;
  let disposed = false;
  let onResize: (() => void) | null = null;
  let observer: ResizeObserver | null = null;

  try {
    scene = new Scene(engine);
    scene.clearColor = new Color4(0.012, 0.016, 0.027, 1);

    const camera = new ArcRotateCamera(
      'local-site-camera',
      -Math.PI / 4,
      0.45,
      14000,
      Vector3.Zero(),
      scene,
    );
    camera.lowerRadiusLimit = 30;
    camera.upperRadiusLimit = 48000;
    camera.lowerBetaLimit = 0.07;
    camera.upperBetaLimit = Math.PI / 2 - 0.012;
    camera.minZ = 0.5;
    camera.maxZ = 120000;
    camera.wheelPrecision = 45;
    camera.panningSensibility = 150;
    camera.attachControl(canvas, true);
    scene.activeCamera = camera;

    // Production terrain material. This is an inspection-friendly visual
    // representation, NOT a calibrated lunar photometric or irradiance model.
    // A small emissive component keeps the actual DEM mesh recognizable even
    // before terrain-cast shadows and per-point illumination are implemented.
    const regolith = new StandardMaterial('NASA-LOLA-regolith-visual', scene);
    regolith.disableLighting = false;
    regolith.diffuseColor = new Color3(0.53, 0.52, 0.50);
    regolith.emissiveColor = new Color3(0.14, 0.14, 0.14);
    regolith.specularColor = new Color3(0.01, 0.01, 0.01);
    regolith.backFaceCulling = false;
    regolith.wireframe = false;

    // Non-scientific visualization fill: direct Sun direction comes from the
    // backend, but shadowing and physical brightness remain deferred work.
    const fill = new HemisphericLight('ui-only-fill', new Vector3(0, 1, 0), scene);
    fill.intensity = 0.28;

    const sun = new DirectionalLight('backend-solar-direction', new Vector3(0, -1, 0), scene);
    sun.intensity = 1.4;
    sun.setEnabled(false);

    let terrainMesh: Mesh | null = null;
    engine.runRenderLoop(() => { if (scene && !disposed) scene.render(); });
    onResize = () => engine.resize();
    window.addEventListener('resize', onResize);
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => engine.resize());
      observer.observe(canvas);
    }

    return {
      setTerrain(terrain) {
        if (disposed) return;
        // Discard the preceding site's mesh before loading a new selection.
        terrainMesh?.dispose();
        terrainMesh = null;
        if (!terrain) return;

        const validated = verifyTerrainMesh(terrain);
        const data = new VertexData();
        data.positions = validated.positions;
        data.indices = validated.indices;
        const normals: number[] = [];
        VertexData.ComputeNormals(validated.positions, validated.indices, normals);
        data.normals = normals;

        const mesh = new Mesh('NASA-LOLA-selected-site-mesh', scene!);
        try {
          data.applyToMesh(mesh, false);
          mesh.material = regolith;
          terrainMesh = mesh;

          const boundingBox = mesh.getBoundingInfo().boundingBox;
          camera.setTarget(boundingBox.centerWorld);
          camera.alpha = -Math.PI / 4;
          camera.beta = 0.45;
          camera.radius = Math.max(900, validated.extentM * 2.8);

        } catch (error) {
          mesh.dispose();
          terrainMesh = null;
          throw error;
        }
      },
      setSun(solar) {
        if (disposed) return;
        if (!solar || !solar.aboveHorizon) {
          sun.setEnabled(false);
          return;
        }
        const [x, y, z] = solar.direction;
        // A site-to-Sun vector points toward the Sun; Babylon's directional
        // light points in the direction the incoming light rays travel.
        sun.direction = new Vector3(-x, -y, -z);
        sun.setEnabled(true);
      },
      dispose() {
        if (disposed) return;
        disposed = true;
        observer?.disconnect();
        if (onResize) window.removeEventListener('resize', onResize);
        engine.stopRenderLoop();
        camera.detachControl();
        scene?.dispose();
        engine.dispose();
      },
    };
  } catch (error) {
    observer?.disconnect();
    if (onResize) window.removeEventListener('resize', onResize);
    engine.stopRenderLoop();
    scene?.dispose();
    engine.dispose();
    throw error;
  }
}
