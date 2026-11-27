<script lang="ts">
  import { onMount } from 'svelte';
  import * as maplibregl from 'maplibre-gl';
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
  import type { Map as LibreMap, Marker } from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import { SYDNEY } from './scenario';
  import type { Coordinates, Place, RentalCandidate } from './scenario';

  let {
    candidates,
    destinations,
    selectedId,
    placing,
    onlocation,
    onselect,
  }: {
    candidates: RentalCandidate[];
    destinations: Place[];
    selectedId: string | null;
    placing: boolean;
    onlocation: (point: Coordinates) => void;
    onselect: (id: string) => void;
  } = $props();

  const key = import.meta.env.VITE_MAPTILER_KEY?.trim();
  let container: HTMLDivElement;
  let map = $state.raw<LibreMap>();
  let loaded = $state(false);
  let error = $state('');
  const markers = new Map<string, { marker: Marker; button: HTMLButtonElement }>();

  onMount(() => {
    if (!key) return;
    let instance: LibreMap;
    // Let Vite bundle and serve the ESM worker instead of resolving it from an optimized dependency.
    maplibregl.setWorkerUrl(workerUrl);
    try {
      instance = new maplibregl.Map({
        container,
        style: `https://api.maptiler.com/maps/streets-v4/style.json?key=${encodeURIComponent(key)}`,
        center: [SYDNEY.longitude, SYDNEY.latitude],
        zoom: 11,
        attributionControl: false,
      });
    } catch {
      error =
        'The map could not start. This browser may not support WebGL. You can still enter coordinates in the sidebar.';
      return;
    }
    map = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    instance.addControl(
      new maplibregl.AttributionControl({
        compact: false,
        customAttribution:
          '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener noreferrer">© MapTiler</a> <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>',
      }),
    );
    instance.on('load', () => {
      loaded = true;
      error = '';
    });
    instance.on('error', () => {
      error =
        'Map data could not load. Check your key, allowed origins, connection and MapTiler quota. Your workspace is unaffected.';
    });
    instance.on('click', (event) => {
      if (placing) onlocation({ latitude: event.lngLat.lat, longitude: event.lngLat.wrap().lng });
    });
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(container);
    const timeout = window.setTimeout(() => {
      if (!loaded)
        error =
          'The map is taking longer than expected. Check your connection and MapTiler key. Coordinate entry is still available.';
    }, 15_000);
    return () => {
      clearTimeout(timeout);
      observer.disconnect();
      for (const { marker } of markers.values()) marker.remove();
      markers.clear();
      instance.remove();
    };
  });

  $effect(() => {
    const instance = map;
    if (!instance) return;
    const places = [
      ...destinations.map((place) => ({ place, work: true })),
      ...candidates.map((place) => ({ place, work: false })),
    ];
    const ids = new Set(places.map(({ place }) => place.id));
    for (const [id, entry] of markers) {
      if (!ids.has(id)) {
        entry.marker.remove();
        markers.delete(id);
      }
    }
    for (const { place, work } of places) {
      let entry = markers.get(place.id);
      if (!entry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.addEventListener('click', (event) => {
          event.stopPropagation();
          onselect(place.id);
        });
        const marker = new maplibregl.Marker({ element: button, anchor: 'bottom' })
          .setLngLat([place.coordinates.longitude, place.coordinates.latitude])
          .addTo(instance);
        entry = { marker, button };
        markers.set(place.id, entry);
      }
      entry.button.classList.add('map-pin');
      entry.button.classList.toggle('work-pin', work);
      entry.button.classList.toggle('rental-pin', !work);
      entry.button.classList.toggle('selected', !work && place.id === selectedId);
      entry.button.textContent = work
        ? 'W'
        : String(candidates.findIndex((item) => item.id === place.id) + 1);
      entry.button.setAttribute(
        'aria-label',
        work ? `Work destination: ${place.label}` : `Select rental on map: ${place.label}`,
      );
      if (!work) entry.button.setAttribute('aria-pressed', String(place.id === selectedId));
      entry.marker.setLngLat([place.coordinates.longitude, place.coordinates.latitude]);
    }
  });

  $effect(() => {
    const instance = map;
    const selected = candidates.find((item) => item.id === selectedId);
    if (instance && selected) {
      const { clientWidth: width, clientHeight: height } = instance.getContainer();
      // Keep the selected pin clear of the details panel on both layouts.
      const offset: [number, number] =
        width < 640 ? [0, -Math.min(90, height / 6)] : [-Math.min(200, width / 5), 0];
      instance.easeTo({
        center: [selected.coordinates.longitude, selected.coordinates.latitude],
        offset,
        duration: 350,
      });
    }
  });
</script>

<div
  class:placing
  class="map-surface"
  data-map-state={!key ? 'unconfigured' : error ? 'error' : loaded ? 'ready' : 'loading'}
>
  <div bind:this={container} class="map-canvas" aria-label="Map of Sydney"></div>
  {#if !key}
    <div class="map-notice setup-notice">
      <span class="eyebrow">One-time setup</span>
      <h2>Your map starts here.</h2>
      <p>
        Add your MapTiler key to <code>web/.env.local</code> as <code>VITE_MAPTILER_KEY</code>, then
        restart Vite or rebuild.
      </p>
      <p>
        You can already add rentals using coordinates, save locally and import or export your
        workspace.
      </p>
      <a href="https://cloud.maptiler.com/" target="_blank" rel="noopener noreferrer"
        >Get a free MapTiler key ↗</a
      >
    </div>
  {:else if error}
    <div class="map-notice map-warning" role="status">{error}</div>
  {:else if !loaded}
    <div class="map-notice map-warning" role="status">Loading Sydney map…</div>
  {/if}
  {#if key}
    <a
      class="maptiler-logo"
      href="https://www.maptiler.com/"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="MapTiler maps"
    >
      <img
        src="https://api.maptiler.com/resources/logo.svg"
        alt="MapTiler"
        width="100"
        height="30"
      />
    </a>
  {/if}
</div>
