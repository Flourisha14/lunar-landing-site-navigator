import {
  ArcRotateCamera, Color3, Color4, DirectionalLight, Engine,
  HemisphericLight, MeshBuilder, Scene, StandardMaterial, Vector3,
} from '@babylonjs/core';
import type { SolarLightVector } from './solarLighting';

export interface LocalSceneHandle {
  setSun: (solar: SolarLightVector | null) => void;
  dispose: () => void;
}

/** One Babylon engine/render loop per mounted local view, independent of Cesium. */
export function createLocalScene(canvas: HTMLCanvasElement): LocalSceneHandle {
  const engine = new Engine(canvas, true, { stencil: true, preserveDrawingBuffer: false });
  let scene: Scene | null = null;
  let disposed = false;
  let onResize: (() => void) | null = null;
  let observer: ResizeObserver | null = null;
  try {
    scene = new Scene(engine);
    scene.clearColor = new Color4(0.02, 0.035, 0.07, 1);
    const camera = new ArcRotateCamera('local-site-camera', -Math.PI / 2, 1.05, 30, Vector3.Zero(), scene);
    camera.lowerRadiusLimit = 9;
    camera.upperRadiusLimit = 85;
    camera.lowerBetaLimit = 0.15;
    camera.upperBetaLimit = Math.PI / 2 - 0.03;
    camera.wheelPrecision = 25;
    camera.attachControl(canvas, true);
    scene.activeCamera = camera;

    const material = new StandardMaterial('illustrative-regolith', scene);
    material.diffuseColor = new Color3(0.42, 0.45, 0.50);
    material.specularColor = new Color3(0.035, 0.035, 0.035);
    const ground = MeshBuilder.CreateGround('illustrative-ground', { width: 90, height: 90, subdivisions: 4 }, scene);
    ground.material = material;

    // UI-only fill keeps the demonstrative scene legible when scientific Sun data is absent.
    // This is NOT lunar ambient irradiance or proof of daylight.
    const fill = new HemisphericLight('non-scientific-ui-fill', new Vector3(0, 1, 0), scene);
    fill.intensity = 0.12;
    const sun = new DirectionalLight('backend-solar-direction', new Vector3(0, -1, 0), scene);
    sun.intensity = 1.4; // Artistic brightness, not calibrated solar irradiance.
    sun.setEnabled(false);

    engine.runRenderLoop(() => { if (scene && !disposed) scene.render(); });
    onResize = () => engine.resize();
    window.addEventListener('resize', onResize);
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => engine.resize());
      observer.observe(canvas);
    }
    return {
      setSun(solar) {
        if (disposed) return;
        if (!solar || !solar.aboveHorizon) {
          sun.setEnabled(false);
          return;
        }
        const [x, y, z] = solar.direction;
        sun.direction = new Vector3(x, y, z);
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
