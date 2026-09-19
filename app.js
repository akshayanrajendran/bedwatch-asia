const { GEAR, HABITAT, predict } = window.BedWatchModel;

const map = L.map("map", { zoomControl: true }).setView([8.5, 100], 4);

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}", {
  attribution: "Tiles &copy; Esri — Ocean Basemap",
  maxZoom: 13,
}).addTo(map);

const layers = {
  seagrass: L.layerGroup(),
  trawl: L.layerGroup().addTo(map),
  mpa: L.layerGroup(),
  forecast: L.layerGroup().addTo(map),
  unep: L.layerGroup().addTo(map),
};

let hotspots = [];
let selectedId = "palk-bay";
let scenario = "current";
let forecastLayers = [];
let formState = null;

function styleKind(kind, intensity = 0.5) {
  if (kind === "seagrass") {
    return { color: "#3d9b6e", weight: 1.2, fillColor: "#3d9b6e", fillOpacity: 0.22 };
  }
  if (kind === "trawl") {
    return { color: "#c45c2c", weight: 1, fillColor: "#c45c2c", fillOpacity: 0.18 + intensity * 0.2 };
  }
  return { color: "#4d7ec9", weight: 1.4, dashArray: "4 3", fillColor: "#4d7ec9", fillOpacity: 0.12 };
}

function rbsColor(v) {
  if (v < 0.2) return "#c45c2c";
  if (v < 0.4) return "#d4b43a";
  return "#3d9b6e";
}

function rbsFromScenario(props) {
  if (scenario === "reformed") return props.rbs10_reformed;
  if (scenario === "bedsafe") return props.rbs10_bedsafe ?? 0.85;
  return props.rbs10;
}

function paintForecast() {
  forecastLayers.forEach((layer) => {
    const v = rbsFromScenario(layer.feature.properties);
    layer.setStyle({
      color: rbsColor(v),
      weight: 0.6,
      fillColor: rbsColor(v),
      fillOpacity: 0.55,
    });
  });
}

function defaultModel(h) {
  return (
    h.model || {
      gear: "otter",
      habitat: "seagrass",
      sweeps_per_year: 2,
      status0: (h.bedHealth || 50) / 100,
      practices: {
        tickler_chains: false,
        too_shallow_on_bed: false,
        repeat_same_tracks: false,
        spawn_season_tows: false,
        high_tow_speed: false,
      },
    }
  );
}

function pct(x) {
  return `${Math.round(x * 100)}%`;
}

function spark(paths) {
  const w = 260;
  const h = 88;
  const pad = 6;
  const n = paths.current.length - 1;
  const xy = (arr) =>
    arr
      .map((y, i) => {
        const x = pad + (i / n) * (w - pad * 2);
        const yy = h - pad - y * (h - pad * 2);
        return `${x.toFixed(1)},${yy.toFixed(1)}`;
      })
      .join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="Ten year relative benthic status">
    <text x="${pad}" y="10" fill="#9aaca3" font-size="9">RBS</text>
    <text x="${w - 28}" y="${h - 2}" fill="#9aaca3" font-size="9">yr ${n}</text>
    <polyline fill="none" stroke="#c45c2c" stroke-width="1.8" points="${xy(paths.current)}" />
    <polyline fill="none" stroke="#d4b43a" stroke-width="1.4" points="${xy(paths.reformed)}" />
    <polyline fill="none" stroke="#3d9b6e" stroke-width="1.4" points="${xy(paths.bedsafe)}" />
  </svg>
  <div class="spark-key">
    <span><i class="swatch trawl"></i> current</span>
    <span><i class="swatch risk"></i> reform procedures</span>
    <span><i class="swatch seagrass"></i> no tow on bed</span>
  </div>`;
}

function readForm() {
  const root = document.getElementById("predictor");
  if (!root) return formState;
  const practices = {};
  root.querySelectorAll("[data-practice]").forEach((el) => {
    practices[el.dataset.practice] = el.checked;
  });
  formState = {
    gear: root.querySelector("[name=gear]").value,
    habitat: root.querySelector("[name=habitat]").value,
    sweeps_per_year: Number(root.querySelector("[name=sweeps]").value),
    status0: Number(root.querySelector("[name=status0]").value) / 100,
    years: 10,
    practices,
  };
  return formState;
}

function bindPredictor() {
  const root = document.getElementById("predictor");
  if (!root) return;
  root.querySelectorAll("input, select").forEach((el) => {
    el.addEventListener("input", () => {
      formState = readForm();
      renderDetail(hotspots.find((x) => x.id === selectedId), false);
    });
  });
}

function renderStats(list) {
  const preds = list.map((h) => predict({ ...defaultModel(h), years: 10 }));
  const collapsing = preds.filter((p) => p.rbsHorizon < 0.2).length;
  const chronic = preds.filter((p) => p.chronic).length;
  document.getElementById("stats").innerHTML = `
    <div class="stat"><strong>${list.length}</strong><span>waterbodies in model</span></div>
    <div class="stat"><strong>${chronic}</strong><span>chronic (F·d &gt; r)</span></div>
    <div class="stat"><strong>${collapsing}</strong><span>RBS &lt; 0.2 in 10 years</span></div>
    <div class="stat"><strong>Palk Bay</strong><span>spatial forecast grid</span></div>
  `;
}

function renderList(list, selected) {
  const el = document.getElementById("hotspot-list");
  el.innerHTML = list
    .map((h) => {
      const p = predict({ ...defaultModel(h), years: 10 });
      return `<button class="hotspot ${h.id === selected ? "active" : ""}" data-id="${h.id}">
        <div class="row"><strong>${h.name}</strong><span class="risk-num">${pct(p.rbsHorizon)}</span></div>
        <div class="row"><span>${h.region}</span><span>10-yr RBS</span></div>
      </button>`;
    })
    .join("");
  el.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => selectHotspot(btn.dataset.id));
  });
}

function renderDetail(h, resetForm) {
  if (resetForm) formState = { ...defaultModel(h), years: 10, practices: { ...defaultModel(h).practices } };
  const m = formState;
  const pred = predict(m);
  const gearOpts = Object.entries(GEAR)
    .map(([k, v]) => `<option value="${k}" ${m.gear === k ? "selected" : ""}>${v.label}</option>`)
    .join("");
  const habOpts = Object.entries(HABITAT)
    .map(([k, v]) => `<option value="${k}" ${m.habitat === k ? "selected" : ""}>${v.label}</option>`)
    .join("");
  const chk = (key, label) =>
    `<label><input type="checkbox" data-practice="${key}" ${m.practices[key] ? "checked" : ""} /> ${label}</label>`;

  const collapse =
    pred.yearsToCollapse == null
      ? "Bed stays above collapse threshold (RBS 0.2) in this 10-year window."
      : `Predicted collapse (RBS &lt; 0.2) in year ${pred.yearsToCollapse}.`;

  document.getElementById("detail").innerHTML = `
    <p class="eyebrow">${h.region}${h.deepDive ? " · spatial grid on map" : ""}</p>
    <h2>${h.name}</h2>
    <p class="headline">
      10-year bed status <strong>${pct(pred.rbsHorizon)}</strong>
      ${pred.chronic ? "<em class='warn'>chronic decline</em>" : "<em>not chronic</em>"}
    </p>
    <p class="note">Depletion per pass d=${pred.d.toFixed(2)} · effective sweeps F=${pred.f.toFixed(2)} · recovery r=${pred.r.toFixed(2)}. Nursery function at horizon ${pct(pred.nurseryHorizon)}.</p>
    ${spark({ current: pred.path, reformed: pred.pathReformed, bedsafe: pred.pathBedsafe })}
    <p class="note">${collapse} Reform procedures → ${pct(pred.rbsReformed)}. No tow on sensitive bed → ${pct(pred.rbsBedsafe)}.</p>
    <form id="predictor">
      <h2>Trawl procedure</h2>
      <label class="stack">Gear<select name="gear">${gearOpts}</select></label>
      <label class="stack">Habitat<select name="habitat">${habOpts}</select></label>
      <label class="stack">Sweeps per year (SAR) <span id="sweep-val">${m.sweeps_per_year}</span>
        <input name="sweeps" type="range" min="0" max="10" step="0.1" value="${m.sweeps_per_year}" />
      </label>
      <label class="stack">Starting bed status ${Math.round(m.status0 * 100)}%
        <input name="status0" type="range" min="5" max="100" step="1" value="${Math.round(m.status0 * 100)}" />
      </label>
      <h2>Inappropriate practices</h2>
      ${chk("tickler_chains", "Tickler chains / extra groundgear")}
      ${chk("too_shallow_on_bed", "Tow too shallow on the bed")}
      ${chk("repeat_same_tracks", "Repeat the same tracks")}
      ${chk("spawn_season_tows", "Tow in spawn / nursery season")}
      ${chk("high_tow_speed", "High tow speed")}
    </form>
    <h2>Why this run is damaging</h2>
    <ul class="actions">${pred.flags.map((f) => `<li>${f}</li>`).join("")}</ul>
    <p class="note">Site context: ${h.drivers.join("; ")}</p>
  `;
  const sweep = document.querySelector("[name=sweeps]");
  if (sweep) {
    sweep.addEventListener("input", () => {
      const label = document.getElementById("sweep-val");
      if (label) label.textContent = sweep.value;
    });
  }
  bindPredictor();
}

function selectHotspot(id) {
  selectedId = id;
  const h = hotspots.find((x) => x.id === id);
  if (!h) return;
  renderList(hotspots, id);
  renderDetail(h, true);
  map.flyTo(h.center, h.zoom, { duration: 0.8 });
}

document.getElementById("layer-seagrass").addEventListener("change", (e) => {
  e.target.checked ? map.addLayer(layers.seagrass) : map.removeLayer(layers.seagrass);
});
document.getElementById("layer-trawl").addEventListener("change", (e) => {
  e.target.checked ? map.addLayer(layers.trawl) : map.removeLayer(layers.trawl);
});
document.getElementById("layer-mpa").addEventListener("change", (e) => {
  e.target.checked ? map.addLayer(layers.mpa) : map.removeLayer(layers.mpa);
});
document.getElementById("layer-forecast").addEventListener("change", (e) => {
  e.target.checked ? map.addLayer(layers.forecast) : map.removeLayer(layers.forecast);
});
document.getElementById("layer-unep").addEventListener("change", (e) => {
  e.target.checked ? map.addLayer(layers.unep) : map.removeLayer(layers.unep);
});

function renderSources(doc) {
  const el = document.getElementById("source-list");
  el.innerHTML = doc.sources
    .filter((s) => ["gfw-map", "unep-seagrass", "allen", "protected-planet"].includes(s.id))
    .map(
      (s) => `<a class="source-card" href="${s.palkUrl || s.url}" target="_blank" rel="noopener">
        <strong>${s.name}</strong>
        <span>${s.role}</span>
      </a>`
    )
    .join("");
}

document.getElementById("scenario-bar").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-scenario]");
  if (!btn) return;
  scenario = btn.dataset.scenario;
  document.querySelectorAll("#scenario-bar button").forEach((b) => b.classList.toggle("active", b === btn));
  paintForecast();
});

async function boot() {
  const [hotspotDoc, geo, forecast, sources, unepPoly, unepPts] = await Promise.all([
    fetch("./data/hotspots.json").then((r) => r.json()),
    fetch("./data/layers.geojson").then((r) => r.json()),
    fetch("./data/palk_forecast.geojson").then((r) => r.json()),
    fetch("./data/sources.json").then((r) => r.json()),
    fetch("./data/seagrass_unep_palk.geojson").then((r) => r.json()),
    fetch("./data/seagrass_unep_palk_pts.geojson").then((r) => r.json()),
  ]);
  hotspots = hotspotDoc.hotspots;
  renderSources(sources);

  L.geoJSON(unepPoly, {
    style: { color: "#7dcea0", weight: 1.2, fillColor: "#3d9b6e", fillOpacity: 0.35 },
    onEachFeature: (feat, layer) => {
      layer.bindPopup("UNEP-WCMC seagrass polygon v7.1 (Palk–Mannar extract)");
      layer.on("click", () => selectHotspot("palk-bay"));
      layers.unep.addLayer(layer);
    },
  });
  L.geoJSON(unepPts, {
    pointToLayer: (_f, latlng) =>
      L.circleMarker(latlng, { radius: 4, color: "#7dcea0", fillColor: "#7dcea0", fillOpacity: 0.9, weight: 1 }),
    onEachFeature: (feat, layer) => {
      layer.bindPopup("UNEP-WCMC seagrass point v7.1");
      layer.on("click", () => selectHotspot("palk-bay"));
      layers.unep.addLayer(layer);
    },
  });

  L.geoJSON(geo, {
    style: (feat) => styleKind(feat.properties.kind, feat.properties.intensity),
    onEachFeature: (feat, layer) => {
      const kind = feat.properties.kind;
      const hid = feat.properties.hotspot;
      layer.bindPopup(`<strong>${feat.properties.name}</strong><br>${kind}`);
      layer.on("click", () => selectHotspot(hid));
      if (kind === "seagrass") layers.seagrass.addLayer(layer);
      else if (kind === "trawl") layers.trawl.addLayer(layer);
      else if (kind === "mpa") layers.mpa.addLayer(layer);
    },
  });

  L.geoJSON(forecast, {
    onEachFeature: (feat, layer) => {
      const v = feat.properties.rbs10;
      layer.bindPopup(
        `Palk cell · ${feat.properties.sweeps} sweeps/yr<br>10-yr RBS ${Math.round(v * 100)}%` +
          (feat.properties.chronic ? " · chronic" : "")
      );
      layer.on("click", () => selectHotspot("palk-bay"));
      layers.forecast.addLayer(layer);
      forecastLayers.push(layer);
    },
  });
  paintForecast();

  renderStats(hotspots);
  selectHotspot("palk-bay");
}

boot().catch((err) => {
  const msg = `Could not load data: ${err.message}. Use python3 -m http.server from the project folder.`;
  document.getElementById("detail").innerHTML = `<p>${msg}</p>`;
  document.getElementById("stats").innerHTML = `<p class="note">${msg}</p>`;
});
