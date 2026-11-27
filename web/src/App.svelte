<script lang="ts">
  import { onMount } from 'svelte';
  import MapView from './lib/MapView.svelte';
  import {
    emptyScenario,
    formatRent,
    listingUrl,
    MAX_CANDIDATES,
    MAX_IMPORT_BYTES,
    parseCoordinates,
    parseRent,
    parseScenarioJSON,
    serializeScenario,
    validateScenario,
  } from './lib/scenario';
  import type { Coordinates, Place, RentalCandidate, Scenario } from './lib/scenario';
  import { loadScenario, saveScenario } from './lib/persistence';

  type Editor = {
    kind: 'rental' | 'work';
    id: string | null;
    label: string;
    latitude: string;
    longitude: string;
    rent: string;
    url: string;
  };
  let scenario = $state<Scenario>(emptyScenario());
  let selectedId = $state<string | null>(null);
  let editor = $state<Editor | null>(null);
  let formError = $state('');
  let notice = $state('');
  let storageWarning = $state<string | null>(null);
  let storageBlocked = $state(false);
  let unreadableSave = $state<string | null>(null);
  let ready = $state(false);
  let fileInput: HTMLInputElement;
  let labelInput = $state<HTMLInputElement>();
  const selected = $derived(scenario.candidates.find((item) => item.id === selectedId));
  const work = $derived(scenario.destinations[0]);

  onMount(() => {
    const saved = loadScenario(() => localStorage);
    scenario = saved.scenario;
    selectedId = scenario.candidates[0]?.id ?? null;
    storageWarning = saved.error;
    storageBlocked = !!saved.error;
    unreadableSave = saved.unreadable ?? null;
    ready = true;
  });

  function commit(next: Scenario) {
    scenario = validateScenario(next);
    if (!storageBlocked) {
      storageWarning = saveScenario(scenario, () => localStorage);
      storageBlocked = !!storageWarning;
    }
  }

  function openEditor(kind: 'rental' | 'work', place?: Place) {
    editor = {
      kind,
      id: place?.id ?? null,
      label: place?.label ?? (kind === 'work' ? 'Work' : ''),
      latitude: place ? String(place.coordinates.latitude) : '',
      longitude: place ? String(place.coordinates.longitude) : '',
      rent:
        place && 'weeklyRentCents' in place
          ? String((place as RentalCandidate).weeklyRentCents / 100)
          : '',
      url: place && 'listingUrl' in place ? ((place as RentalCandidate).listingUrl ?? '') : '',
    };
    formError = '';
    notice = '';
  }

  function mapPoint(point: Coordinates) {
    if (!editor) return;
    editor = {
      ...editor,
      latitude: point.latitude.toFixed(6),
      longitude: point.longitude.toFixed(6),
    };
    notice = 'Location chosen. Complete the details in the sidebar.';
    labelInput?.focus({ preventScroll: false });
  }

  function saveEditor(event: SubmitEvent) {
    event.preventDefault();
    if (!editor) return;
    try {
      const place: Place = {
        id: editor.id ?? crypto.randomUUID(),
        label: editor.label,
        coordinates: parseCoordinates(editor.latitude, editor.longitude),
      };
      let next: Scenario;
      if (editor.kind === 'work') {
        next = { ...scenario, destinations: [place] };
      } else {
        const url = listingUrl(editor.url);
        const candidate: RentalCandidate = {
          ...place,
          weeklyRentCents: parseRent(editor.rent),
          ...(url ? { listingUrl: url } : {}),
        };
        next = {
          ...scenario,
          candidates: editor.id
            ? scenario.candidates.map((item) => (item.id === editor!.id ? candidate : item))
            : [...scenario.candidates, candidate],
        };
      }
      const valid = validateScenario(next);
      commit(valid);
      if (editor.kind === 'rental') selectedId = place.id;
      notice = `${editor.kind === 'work' ? 'Work destination' : 'Rental'} saved.`;
      editor = null;
      formError = '';
    } catch (error) {
      formError = error instanceof Error ? error.message : 'Could not save these details.';
    }
  }

  function selectCandidate(id: string) {
    if (work?.id === id) {
      openEditor('work', work);
      return;
    }
    selectedId = id;
    editor = null;
    formError = '';
  }

  function removeCandidate(candidate: RentalCandidate) {
    if (!confirm(`Remove “${candidate.label}” from this workspace?`)) return;
    const candidates = scenario.candidates.filter((item) => item.id !== candidate.id);
    commit({ ...scenario, candidates });
    if (selectedId === candidate.id) selectedId = candidates[0]?.id ?? null;
    if (editor?.id === candidate.id) editor = null;
    notice = 'Rental removed.';
  }

  function removeWork() {
    if (!confirm('Remove your work destination?')) return;
    commit({ ...scenario, destinations: [] });
    if (editor?.kind === 'work') editor = null;
    notice = 'Work destination removed.';
  }

  function download(content: string, name: string) {
    const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportWorkspace() {
    download(serializeScenario(scenario), 'sydney-rental-workspace.json');
    notice =
      'Workspace exported. The file contains your rental and work locations; keep it private.';
  }

  async function importWorkspace(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    try {
      if (file.size > MAX_IMPORT_BYTES) throw new Error('Scenario file must be 1 MiB or smaller.');
      const imported = parseScenarioJSON(await file.text());
      if (
        !confirm(
          'Replace the current workspace with this file? Export your current workspace first if you want to keep it.',
        )
      )
        return;
      commit(imported);
      selectedId = imported.candidates[0]?.id ?? null;
      editor = null;
      formError = '';
      notice = 'Workspace imported.';
    } catch (error) {
      notice = `Import failed: ${error instanceof Error ? error.message : 'Could not read this file.'}`;
    } finally {
      input.value = '';
    }
  }

  function replaceLocalSave() {
    if (
      unreadableSave &&
      !confirm(
        'Replace the unreadable local save with your current workspace? Download the original first if you want to recover it.',
      )
    )
      return;
    const error = saveScenario(scenario, () => localStorage);
    storageWarning = error;
    storageBlocked = !!error;
    if (!error) {
      unreadableSave = null;
      notice = 'Current workspace saved in this browser.';
    }
  }
</script>

<svelte:head><title>Sydney Commute · Rental workspace</title></svelte:head>

<a class="skip-link" href="#workspace">Skip to workspace</a>
<header class="app-header">
  <div class="brand">
    <span class="brand-icon" aria-hidden="true">⌖</span>
    <div>
      <strong>Sydney Commute</strong><span>A little more perspective on where to live.</span>
    </div>
  </div>
  <div class="header-actions">
    <span class="prototype-tag">Rental prototype</span>
    <button class="quiet" disabled={!ready} onclick={() => fileInput.click()}>Import JSON</button>
    <button class="outline" disabled={!ready} onclick={exportWorkspace}>Export JSON ↗</button>
    <input
      class="visually-hidden"
      bind:this={fileInput}
      type="file"
      accept=".json,application/json"
      aria-label="Import workspace file"
      onchange={importWorkspace}
    />
  </div>
</header>

{#if storageWarning}
  <div class="storage-warning" role="alert">
    <span>{storageWarning}</span>
    {#if unreadableSave}<button
        onclick={() => download(unreadableSave!, 'sccc-unreadable-save.json')}
        >Download original save</button
      >{/if}
    {#if storageBlocked}<button onclick={replaceLocalSave}
        >{unreadableSave ? 'Replace local save' : 'Retry browser saving'}</button
      >{/if}
  </div>
{/if}

<main id="workspace" class="workspace">
  <aside class="sidebar" aria-label="Rental workspace">
    <div class="sidebar-intro">
      <span class="eyebrow">Find your balance</span>
      <h1>Where could you live?</h1>
      <p>Put a few places on the map.<br />Start with rent. Add the commute next.</p>
    </div>
    <fieldset class="workspace-controls" disabled={!ready}>
      <legend class="visually-hidden">Workspace controls</legend>
      <section class="work-section" aria-labelledby="work-heading">
        <div class="section-heading">
          <h2 id="work-heading">01 <span>Your work destination</span></h2>
        </div>
        {#if work}
          <div class="work-card">
            <span class="work-symbol" aria-hidden="true">W</span>
            <div>
              <strong>{work.label}</strong><small
                >{work.coordinates.latitude.toFixed(4)}, {work.coordinates.longitude.toFixed(
                  4,
                )}</small
              >
            </div>
          </div>
          <div class="inline-actions">
            <button class="text-button" onclick={() => openEditor('work', work)}
              >Edit destination</button
            ><button class="text-button muted" onclick={removeWork}>Remove destination</button>
          </div>
        {:else}
          <button class="work-placeholder" onclick={() => openEditor('work')}
            ><span aria-hidden="true">＋</span><span
              >Set work destination<small>Choose a point on the map</small></span
            ></button
          >
        {/if}
      </section>

      <section class="rentals-section" aria-labelledby="rentals-heading">
        <div class="section-heading">
          <h2 id="rentals-heading">02 <span>Rental shortlist</span></h2>
          <span class="count">{scenario.candidates.length}</span>
        </div>
        {#if scenario.candidates.length === 0}
          <div class="empty-list">
            <span class="empty-icon" aria-hidden="true">⌂</span>
            <h3>A new place starts with a pin.</h3>
            <p>Add a rental you’re considering.<br />Your shortlist stays in this browser.</p>
          </div>
        {:else}
          <ol class="candidate-list">
            {#each scenario.candidates as candidate, index (candidate.id)}
              <li>
                <button
                  class:active={selectedId === candidate.id}
                  class="candidate-card"
                  aria-pressed={selectedId === candidate.id}
                  aria-label={`Select rental: ${candidate.label}`}
                  onclick={() => selectCandidate(candidate.id)}
                >
                  <span class="candidate-number">{index + 1}</span><span class="candidate-copy"
                    ><strong>{candidate.label}</strong><span
                      >{formatRent(candidate.weeklyRentCents)} <small>/ week AUD</small></span
                    ></span
                  ><span class="card-arrow" aria-hidden="true">↗</span>
                </button>
              </li>
            {/each}
          </ol>
        {/if}
        <button
          class="add-rental"
          disabled={scenario.candidates.length >= MAX_CANDIDATES}
          onclick={() => openEditor('rental')}>＋ Add a rental</button
        >
        {#if scenario.candidates.length >= MAX_CANDIDATES}<p class="hint">
            This prototype supports up to {MAX_CANDIDATES} rentals.
          </p>{/if}
      </section>

      {#if editor}
        <form class="editor" onsubmit={saveEditor} novalidate>
          <div class="editor-heading">
            <h2>
              {editor.kind === 'work'
                ? 'Work destination'
                : editor.id
                  ? 'Edit rental'
                  : 'New rental'}
            </h2>
            <button
              type="button"
              class="text-button"
              onclick={() => {
                editor = null;
                formError = '';
              }}>Cancel</button
            >
          </div>
          <p class="hint">
            Click the map to choose a location, or enter coordinates below. No address search yet.
          </p>
          <label for="place-label"
            >{editor.kind === 'work' ? 'Destination label' : 'Rental label'}</label
          >
          <input
            id="place-label"
            bind:this={labelInput}
            bind:value={editor.label}
            maxlength="120"
            placeholder={editor.kind === 'work' ? 'Work' : 'e.g. Eastwood two-bedroom'}
            required
          />
          {#if editor.kind === 'rental'}
            <label for="weekly-rent">Weekly rent (AUD)</label>
            <div class="money-input">
              <span aria-hidden="true">$</span><input
                id="weekly-rent"
                bind:value={editor.rent}
                inputmode="decimal"
                placeholder="720"
                required
              />
            </div>
            <label for="listing-url">Listing URL <span class="optional">optional</span></label
            ><input
              id="listing-url"
              type="url"
              bind:value={editor.url}
              maxlength="2048"
              placeholder="https://…"
            />
          {/if}
          <div class="coordinate-fields">
            <div>
              <label for="latitude">Latitude</label><input
                id="latitude"
                bind:value={editor.latitude}
                inputmode="decimal"
                placeholder="−33.8688"
                required
              />
            </div>
            <div>
              <label for="longitude">Longitude</label><input
                id="longitude"
                bind:value={editor.longitude}
                inputmode="decimal"
                placeholder="151.2093"
                required
              />
            </div>
          </div>
          {#if formError}<p class="form-error" role="alert">{formError}</p>{/if}
          <button type="submit" class="primary"
            >Save {editor.kind === 'work' ? 'destination' : 'rental'}</button
          >
        </form>
      {/if}
    </fieldset>
    <div class="sidebar-footer">
      <span class="save-dot" class:warning={!!storageWarning}></span>{storageWarning
        ? 'Export JSON to keep a backup'
        : 'Saved locally · No account needed'}
      <p>Your JSON exports contain locations. Share with care.</p>
    </div>
  </aside>

  <section class="map-workspace" aria-label="Explore Sydney rentals">
    <MapView
      candidates={scenario.candidates}
      destinations={scenario.destinations}
      {selectedId}
      placing={!!editor}
      onlocation={mapPoint}
      onselect={selectCandidate}
    />
    <div class="map-topline">
      <div class="map-caption">
        <span class="live-dot"></span>Sydney, NSW <span class="map-caption-divider">/</span> Your rental
        shortlist
      </div>
    </div>
    {#if editor}<div class="placement-hint" role="status">
        ⌖ Click the map to locate this {editor.kind === 'work' ? 'destination' : 'rental'}
      </div>{/if}
    {#if selected}
      <section class="selection-panel" aria-label="Selected rental">
        <span class="eyebrow">On your shortlist</span>
        <div class="selected-title">
          <h2>{selected.label}</h2>
          <span>{formatRent(selected.weeklyRentCents)}<small>/ week AUD</small></span>
        </div>
        <p class="coordinates">
          {selected.coordinates.latitude.toFixed(5)}, {selected.coordinates.longitude.toFixed(5)}
        </p>
        {#if selected.listingUrl}<a
            class="listing-link"
            href={selected.listingUrl}
            target="_blank"
            rel="noopener noreferrer">View property listing ↗</a
          >{/if}
        <div class="journey-placeholder">
          <span aria-hidden="true">↔</span>
          <p>
            <strong>Commute planning comes next.</strong><br />No journey times or fares are
            connected yet.
          </p>
        </div>
        <div class="selection-actions">
          <button class="outline" onclick={() => openEditor('rental', selected)}>Edit rental</button
          ><button class="text-button danger" onclick={() => removeCandidate(selected!)}
            >Remove rental</button
          >
        </div>
      </section>
    {:else}
      <div class="map-intro">
        <span class="eyebrow">Your next neighbourhood</span>
        <p>Different places.<br /><strong>A clearer picture.</strong></p>
        <span>Add your work and a rental to get started.</span>
      </div>
    {/if}
    <div class="map-stage-label">
      01 — Locations only <span>Public transport planning follows in the next milestone.</span>
    </div>
  </section>
</main>
<div class="announcement" role="status" aria-live="polite">{notice}</div>
