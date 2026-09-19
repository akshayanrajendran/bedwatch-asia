const GEAR = {
  otter: { d: 0.06, label: "Otter trawl (standard doors)" },
  otter_heavy: { d: 0.11, label: "Heavy otter / large doors" },
  beam: { d: 0.14, label: "Beam trawl" },
  dredge: { d: 0.26, label: "Dredge" },
  samba_push: { d: 0.2, label: "Samba seine / push net on meadow" },
};

const HABITAT = {
  mud: { r: 0.65, dMult: 1.0, label: "Soft mud infauna" },
  sand: { r: 0.4, dMult: 1.15, label: "Sand / mixed sediment" },
  seagrass: { r: 0.16, dMult: 3.4, label: "Seagrass meadow (uprooting)" },
  nursery_mud: { r: 0.35, dMult: 1.4, label: "Demersal nursery mud" },
};

function clamp(x, lo = 0, hi = 1) {
  return Math.max(lo, Math.min(hi, x));
}

function depletionPerPass(gear, habitat, practices) {
  let d = GEAR[gear].d * HABITAT[habitat].dMult;
  if (practices.tickler_chains) d *= 1.55;
  if (practices.high_tow_speed) d *= 1.12;
  if (practices.too_shallow_on_bed && habitat === "seagrass") d *= 1.28;
  return clamp(d, 0.01, 0.92);
}

function effectiveFrequency(sweeps, practices) {
  let f = Math.max(0, sweeps);
  if (practices.repeat_same_tracks) f *= 1.45;
  return f;
}

function step(status, f, d, r) {
  const survival = (1 - d) ** f;
  status = status * survival;
  status = status + r * (1 - status);
  return clamp(status);
}

function trajectory(status0, years, f, d, r) {
  let s = clamp(status0);
  const out = [s];
  for (let i = 0; i < years; i += 1) {
    s = step(s, f, d, r);
    out.push(s);
  }
  return out;
}

function yearsToThreshold(path, threshold = 0.2) {
  const idx = path.findIndex((v) => v < threshold);
  return idx === -1 ? null : idx;
}

function nurseryFunction(rbs, practices) {
  let n = rbs;
  if (practices.spawn_season_tows) n *= 0.62;
  if (practices.too_shallow_on_bed) n *= 0.85;
  return clamp(n);
}

function flags(practices, habitat, f, d, r) {
  const items = [];
  if (habitat === "seagrass" && d > 0.25) {
    items.push("Towed gear on seagrass rips shoots and rhizomes, not only infauna.");
  }
  if (practices.tickler_chains) {
    items.push("Tickler chains raise seafloor penetration — inappropriate on vegetated beds.");
  }
  if (practices.too_shallow_on_bed) {
    items.push("Towing too shallow: doors and footrope scour the meadow.");
  }
  if (practices.repeat_same_tracks) {
    items.push("Repeat tows on the same tracks raise local sweep rate above nominal effort.");
  }
  if (practices.spawn_season_tows) {
    items.push("Spawning-season tows hit bed structure and recruitment together.");
  }
  if (practices.high_tow_speed) {
    items.push("High tow speed increases door and groundgear impact.");
  }
  if (f * d > r) {
    items.push("Chronic: yearly depletion exceeds recovery, so bed status trends down.");
  }
  if (!items.length) {
    items.push("Gear, depth, and timing sit in a lower-impact envelope for this habitat.");
  }
  return items;
}

function predict(params) {
  const { gear, habitat, years = 10, status0 = 1 } = params;
  const practices = params.practices || {};
  const f = effectiveFrequency(params.sweeps_per_year, practices);
  const d = depletionPerPass(gear, habitat, practices);
  const r = HABITAT[habitat].r;
  const path = trajectory(status0, years, f, d, r);
  const reformed = {
    tickler_chains: false,
    too_shallow_on_bed: false,
    repeat_same_tracks: false,
    spawn_season_tows: false,
    high_tow_speed: false,
  };
  const f2 = params.sweeps_per_year;
  const d2 = depletionPerPass("otter", habitat, reformed);
  const path2 = trajectory(status0, years, f2, d2, r);
  const f3 = habitat === "seagrass" || habitat === "nursery_mud" ? 0 : Math.min(f2, 1);
  const d3 = depletionPerPass("otter", habitat, reformed);
  const path3 = trajectory(status0, years, f3, d3, r);
  return {
    f,
    d,
    r,
    gearLabel: GEAR[gear].label,
    habitatLabel: HABITAT[habitat].label,
    rbsNow: path[0],
    rbsHorizon: path[path.length - 1],
    rbsReformed: path2[path2.length - 1],
    rbsBedsafe: path3[path3.length - 1],
    nurseryHorizon: nurseryFunction(path[path.length - 1], practices),
    yearsToCollapse: yearsToThreshold(path, 0.2),
    path,
    pathReformed: path2,
    pathBedsafe: path3,
    flags: flags(practices, habitat, f, d, r),
    chronic: f * d > r,
  };
}

window.BedWatchModel = { GEAR, HABITAT, predict, depletionPerPass, effectiveFrequency };
