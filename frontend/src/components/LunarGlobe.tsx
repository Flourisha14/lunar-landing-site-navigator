import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Cartesian2,
  Cartesian3,
  Cesium3DTileset,
  Cartographic,
  Color,
  Ellipsoid,
  EllipsoidTerrainProvider,
  GeographicProjection,
  Globe,
  Ion,
  Math as CesiumMath,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Viewer,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import { LUNAR_REFERENCE_RADIUS_M, normalizeLunarSite, type LunarSite } from '../globe/lunarCoordinates';

interface Props {
  latitude: string;
  longitude: string;
  onSelect: (site: LunarSite) => void;
}

/**
 * A navigation-only sphere. No SPICE calculations, solar lighting model, lunar DEM,
 * Earth terrain, or geographic imagery are silently applied here.
 */
const MOON = new Ellipsoid(
  LUNAR_REFERENCE_RADIUS_M,
  LUNAR_REFERENCE_RADIUS_M,
  LUNAR_REFERENCE_RADIUS_M,
);

function sitePosition(site: LunarSite): Cartesian3 {
  return MOON.cartographicToCartesian(new Cartographic(
    CesiumMath.toRadians(site.longitudeDeg),
    CesiumMath.toRadians(site.latitudeDeg),
    0,
  ));
}

export function LunarGlobe({ latitude, longitude, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const markerRef = useRef<ReturnType<Viewer['entities']['add']> | null>(null);
  const selectRef = useRef(onSelect);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [terrainMode, setTerrainMode] = useState<'fallback' | 'loading' | 'tiles' | 'error'>('fallback');
  const [terrainError, setTerrainError] = useState<string | null>(null);
  const selected = useMemo(() => latitude.trim() === '' || longitude.trim() === '' ? null : normalizeLunarSite(Number(latitude), Number(longitude)), [latitude, longitude]);

  // Event handler registration is once per viewer, yet always calls current app state.
  useEffect(() => { selectRef.current = onSelect; }, [onSelect]);

  useEffect(() => {
    if (!container.current) return;
    let viewer: Viewer | null = null;
    let handler: ScreenSpaceEventHandler | null = null;
    let disposed = false;
    try {
      viewer = new Viewer(container.current, {
        // Explicitly avoid Cesium's default WGS84 globe, ion imagery and Earth terrain.
        ellipsoid: MOON,
        globe: new Globe(MOON),
        mapProjection: new GeographicProjection(MOON),
        terrainProvider: new EllipsoidTerrainProvider({ ellipsoid: MOON }),
        baseLayer: false,
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        animation: false,
        timeline: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        skyBox: false,
        skyAtmosphere: false,
        shouldAnimate: false,
        scene3DOnly: true,
      });
      const active = viewer;
      viewerRef.current = active;
      active.scene.globe.baseColor = Color.fromCssColorString('#68738a');
      active.scene.globe.enableLighting = false; // Never imply real Sun geometry.
      active.scene.backgroundColor = Color.fromCssColorString('#050a15');
      // Keep the camera away from the lunar polar axis.
      // Cesium's depth-plane calculation requires a non-degenerate
      // east direction when constructing the globe horizon.
      const initialCameraPosition = new Cartesian3(
        0,
        -LUNAR_REFERENCE_RADIUS_M * 3.3,
        LUNAR_REFERENCE_RADIUS_M * 0.65,
      );

      const initialCameraDirection = Cartesian3.normalize(
        Cartesian3.negate(initialCameraPosition, new Cartesian3()),
        new Cartesian3(),
      );

      active.camera.setView({
        destination: initialCameraPosition,
        orientation: {
          direction: initialCameraDirection,
          up: Cartesian3.UNIT_Z,
        },
      });
      // The grid is a visual coordinate guide, not lunar topography.
      const gridEntities: Array<ReturnType<Viewer['entities']['add']>> = [];
      const gridColor = Color.fromCssColorString('#b5c8e0').withAlpha(0.45);
      for (let lon = -150; lon <= 180; lon += 30) {
        const positions: Cartesian3[] = [];
        for (let lat = -90; lat <= 90; lat += 5) {
          positions.push(MOON.cartographicToCartesian(new Cartographic(
            CesiumMath.toRadians(lon), CesiumMath.toRadians(lat), 1500,
          )));
        }
        gridEntities.push(active.entities.add({ polyline: { positions, width: 1, material: gridColor } }));
      }
      for (let lat = -60; lat <= 60; lat += 30) {
        const positions: Cartesian3[] = [];
        for (let lon = -180; lon <= 180; lon += 5) {
          positions.push(MOON.cartographicToCartesian(new Cartographic(
            CesiumMath.toRadians(lon), CesiumMath.toRadians(lat), 1500,
          )));
        }
        gridEntities.push(active.entities.add({ polyline: { positions, width: 1, material: gridColor } }));
      }
      handler = new ScreenSpaceEventHandler(active.scene.canvas);
      handler.setInputAction((event: { position: Cartesian2 }) => {
        const hit = active.camera.pickEllipsoid(event.position, MOON);
        if (!hit) return; // Click in empty space, not on lunar surface.
        const coordinates = MOON.cartesianToCartographic(hit);
        const site = normalizeLunarSite(
          CesiumMath.toDegrees(coordinates.latitude),
          CesiumMath.toDegrees(coordinates.longitude),
        );
        if (site) selectRef.current(site);
      }, ScreenSpaceEventType.LEFT_CLICK);
      // Remote tiles are visualization only; scientific LOS still uses the Python DEM.
      const ionToken = (import.meta.env.VITE_CESIUM_ION_TOKEN ?? '').trim();
      if (ionToken) {
        Ion.defaultAccessToken = ionToken;
        setTerrainMode('loading');
        void Cesium3DTileset.fromIonAssetId(2684829, { enableCollision: true })
          .then((tileset) => {
            if (disposed || active.isDestroyed()) {
              if (!tileset.isDestroyed()) tileset.destroy();
              return;
            }
            active.scene.primitives.add(tileset);
            active.scene.globe.show = false;
            for (const grid of gridEntities) active.entities.remove(grid);
            setTerrainMode('tiles');
          })
          .catch((reason: unknown) => {
            if (disposed) return;
            setTerrainError(reason instanceof Error ? reason.message : String(reason));
            setTerrainMode('error');
            // Leave the Moon reference sphere visible on failure.
          });
      }
      setReady(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    return () => {
      disposed = true;
      handler?.destroy();
      viewerRef.current = null;
      markerRef.current = null;
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
    };
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    if (!selected) {
      if (markerRef.current) viewer.entities.remove(markerRef.current);
      markerRef.current = null;
      return;
    }
    const position = sitePosition(selected);
    if (markerRef.current) viewer.entities.remove(markerRef.current);
    markerRef.current = viewer.entities.add({
      position,
      point: {
        pixelSize: 13,
        color: Color.fromCssColorString('#65e3e4'),
        outlineColor: Color.WHITE,
        outlineWidth: 2,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      label: {
        text: 'SELECTED SITE',
        font: '12px sans-serif',
        fillColor: Color.WHITE,
        pixelOffset: new Cartesian2(0, -24),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
  }, [selected, ready]);

  const focusSelected = () => {
    const viewer = viewerRef.current;
    if (!selected || !viewer || viewer.isDestroyed()) return;
    const surface = sitePosition(selected);
    const destination = Cartesian3.multiplyByScalar(surface, 2.8, new Cartesian3());
    const direction = Cartesian3.negate(surface, new Cartesian3());
    const up = Math.abs(selected.latitudeDeg) > 80 ? Cartesian3.UNIT_Y : Cartesian3.UNIT_Z;
    viewer.camera.flyTo({ destination, orientation: { direction, up }, duration: 1.2 });
  };

  return (
    <section className="panel lunar-globe-panel" aria-label="Interactive lunar globe">
      <div className="panel-heading">
        <h2>Explore the Moon</h2>
        <span className="eyebrow">{terrainMode === 'tiles' ? 'CESIUM · NASA-DERIVED LUNAR TILES' : 'CESIUM · LUNAR REFERENCE SPHERE'}</span>
      </div>
      <p className="small muted">Drag to rotate, scroll to zoom, and click the sphere to select a lunar site.</p>
      <div className="lunar-canvas" ref={container} aria-label="Interactive Cesium lunar globe" />
      {terrainMode === 'loading' && <p className="tiny muted" role="status">Loading Cesium Moon 3D Tiles...</p>}
      {terrainMode === 'error' && <p className="tiny muted" role="status">Lunar tiles unavailable ({terrainError}). Showing reference sphere.</p>}
      {error && <div className="error-panel" role="alert">Cesium viewer failed: {error}</div>}
      <div className="lunar-globe-footer">
        <span>{selected ? `Selected: ${selected.latitudeDeg.toFixed(5)}°, ${selected.longitudeDeg.toFixed(5)}° E` : 'Enter valid coordinates to show marker'}</span>
        <button className="secondary lunar-focus" type="button" onClick={focusSelected} disabled={!selected || !ready}>Focus site</button>
      </div>
      <p className="tiny muted">{terrainMode === 'tiles'
        ? 'Global visualization: Cesium Moon (ion asset 2684829), NASA-derived imagery and terrain. This 3D Tiles source is independent of the backend regional LOLA DEM; reference-sphere picking remains in use until FE-005A terrain picking is implemented.'
        : 'Visualization fallback: Gray lunar reference sphere and coordinate grid; no real elevation shown. Scientific terrain analysis uses the Python backend LOLA DEM.'}</p>
      <p className="tiny muted">Selecting a site updates Mission Controls and requests fresh analysis at the currently selected UTC time. Terrain-aware results may be unavailable outside the configured DEM.</p>
    </section>
  );
}
