/* Substance Use Disorder Measures Repository
 * Hierarchical floating-blob view: substance -> construct -> measure.
 * Requires d3 v7.
 */
(function () {
  "use strict";

  var root = document.getElementById("suds-app");
  if (!root || typeof d3 === "undefined") return;

  /* ------------------------------------------------------------------ *
   * constants
   * ------------------------------------------------------------------ */

  var PACK_SIZE = 1000;
  // Substance clusters are spread across a landscape world box rather than
  // stuffed into one circle, so wide screens don't sit half empty.
  var WORLD_W = 1200;
  var WORLD_H = 700;
  var WORLD_FILL = 0.52;
  var DRIFT = 13; // world units of float, kept inside the fitted bounds

  var SUBSTANCE_COLOR = {
    Alcohol: "#b0524a",
    Nicotine: "#c8863c",
    Cannabinoid: "#6d9150",
    Opioid: "#7a5fa8",
    Stimulant: "#c2a02f",
    Benzodiazepine: "#3f8f8a",
    General: "#5b7a9e",
    "Treatment Related": "#9c5c86"
  };
  var FALLBACK_COLOR = "#8b8178";

  var TIERS = ["Adequate", "Good", "Excellent"];

  var reduceMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------------ *
   * dom handles
   * ------------------------------------------------------------------ */

  var figure = root.querySelector(".suds-figure");
  var svg = d3.select(figure).select("svg");
  var gBlobs = svg.append("g").attr("class", "suds-blobs");
  var gLabels = svg.append("g").attr("class", "suds-labels");

  var tip = root.querySelector(".suds-tip");
  var detail = root.querySelector(".suds-detail");
  var crumbs = root.querySelector(".suds-crumbs");
  var empty = root.querySelector(".suds-empty");
  var list = root.querySelector(".suds-list");
  var modeBtn = root.querySelector(".suds-mode");
  var searchInput = root.querySelector("#suds-search");
  var itemsRange = root.querySelector("#suds-items");
  var itemsOut = root.querySelector("#suds-items-out");
  var matchOut = root.querySelector("#suds-matches");

  /* ------------------------------------------------------------------ *
   * state
   * ------------------------------------------------------------------ */

  var hierarchy = null;
  var bounds = { x0: 0, y0: 0, x1: WORLD_W, y1: WORLD_H };
  var entries = []; // flat render records
  var focus = null;
  var view = [PACK_SIZE / 2, PACK_SIZE / 2, PACK_SIZE];
  var viewTarget = view.slice();
  var zoomStart = 0;
  var zoomFrom = view.slice();
  var zoomInterp = null;
  var ZOOM_MS = 780;

  var width = 0;
  var height = 0;
  var selected = null;
  var totalMeasures = 0;
  var mode = "blobs";

  var filters = {
    query: "",
    tiers: {}, // empty => all
    freeOnly: false,
    maxItems: Infinity,
    substances: {} // name -> false when switched off
  };

  var needsRender = true;

  /* ------------------------------------------------------------------ *
   * helpers
   * ------------------------------------------------------------------ */

  function colorFor(name) {
    return SUBSTANCE_COLOR[name] || FALLBACK_COLOR;
  }

  // Rating drives lightness within the substance's hue.
  function leafFill(substance, tier) {
    var base = d3.color(colorFor(substance));
    if (!tier) return "#d8d2cc";
    var pale = d3.color(base).brighter(1.85);
    return d3.interpolateLab(pale, base)(tier / 3);
  }

  function seedOf(text) {
    var h = 0;
    for (var i = 0; i < text.length; i++) {
      h = (h * 31 + text.charCodeAt(i)) % 100000;
    }
    return (h / 100000) * Math.PI * 2;
  }

  var closedLine = d3
    .line()
    .curve(d3.curveCatmullRomClosed.alpha(0.6));

  // A circle with two out-of-phase sine ripples, so blobs breathe organically.
  function blobPath(cx, cy, r, seed, t, amp, lobes) {
    if (r <= 0.4) return "";
    var points = [];
    var n = r > 120 ? 40 : r > 40 ? 30 : 22;
    for (var i = 0; i < n; i++) {
      var a = (i / n) * Math.PI * 2;
      var w =
        Math.sin(a * lobes + t * 0.55 + seed) * amp +
        Math.sin(a * (lobes + 2) - t * 0.4 + seed * 2.1) * amp * 0.5;
      var rr = r * (1 + w);
      points.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr]);
    }
    return closedLine(points);
  }

  function driftOf(node, t) {
    if (!node || node.depth !== 1 || reduceMotion) return [0, 0];
    var s = node.__seed;
    return [
      Math.sin(t * 0.11 + s) * 9 + Math.sin(t * 0.19 + s * 1.6) * 4,
      Math.cos(t * 0.13 + s * 1.3) * 9 + Math.cos(t * 0.23 + s) * 4
    ];
  }

  function measureText(node) {
    var d = node.data;
    return (
      d.abbr +
      " " +
      d.name +
      " " +
      d.constructs.join(" ") +
      " " +
      d.rating +
      " " +
      node.parent.parent.data.name
    ).toLowerCase();
  }

  /* ------------------------------------------------------------------ *
   * layout
   * ------------------------------------------------------------------ */

  function buildHierarchy(data) {
    var tree = {
      name: "root",
      children: data.substances.map(function (s) {
        return {
          name: s.name,
          kind: "substance",
          children: s.constructs.map(function (c) {
            return {
              name: c.name,
              kind: "construct",
              blurb: c.blurb,
              substance: s.name,
              children: c.measures.map(function (m) {
                var leaf = Object.assign({}, m);
                leaf.kind = "measure";
                leaf.substance = s.name;
                leaf.construct = c.name;
                return leaf;
              })
            };
          })
        };
      })
    };

    var h = d3
      .hierarchy(tree)
      // Blob area tracks item count, with a floor so 2-item scales stay clickable.
      .sum(function (d) {
        return d.kind === "measure" ? 3 + d.items : 0;
      })
      .sort(function (a, b) {
        return b.value - a.value;
      });

    d3
      .pack()
      .size([PACK_SIZE, PACK_SIZE])
      .padding(function (d) {
        return d.depth === 0 ? 22 : d.depth === 1 ? 13 : 5;
      })(h);

    h.descendants().forEach(function (n) {
      n.__seed = seedOf(n.data.name + n.depth);
      n.__anc = n.ancestors().filter(function (a) {
        return a.depth === 1;
      })[0];
    });

    // Freeze each node's offset from its substance centre *before* the force
    // layout moves those centres, so clusters travel as rigid units.
    h.descendants()
      .slice(1)
      .forEach(function (n) {
        n.__ox = n.x - n.__anc.x;
        n.__oy = n.y - n.__anc.y;
      });

    layoutWorld(h);
    return h;
  }

  function layoutWorld(h) {
    var subs = h.children;
    var area = d3.sum(subs, function (d) {
      return Math.PI * d.r * d.r;
    });
    var s = Math.sqrt((WORLD_FILL * WORLD_W * WORLD_H) / area);

    // Seed from the packed arrangement, stretched to the landscape box, so the
    // simulation is deterministic and starts somewhere sensible.
    subs.forEach(function (d) {
      d.x = WORLD_W / 2 + (d.x - PACK_SIZE / 2) * s * 2.0;
      d.y = WORLD_H / 2 + (d.y - PACK_SIZE / 2) * s * 0.55;
    });

    // Weak horizontal pull against a strong vertical one flattens the cluster
    // into the landscape shape a wide figure wants.
    var sim = d3
      .forceSimulation(subs)
      .force("x", d3.forceX(WORLD_W / 2).strength(0.006))
      .force("y", d3.forceY(WORLD_H / 2).strength(0.18))
      .force(
        "collide",
        d3
          .forceCollide(function (d) {
            return d.r * s + 12;
          })
          .strength(0.92)
      )
      .stop();

    for (var i = 0; i < 400; i++) sim.tick();

    h.descendants()
      .slice(1)
      .forEach(function (n) {
        n.wr = n.r * s;
        n.wx = n.__anc.x + n.__ox * s;
        n.wy = n.__anc.y + n.__oy * s;
      });

    bounds = {
      x0: d3.min(subs, function (d) { return d.x - d.r * s; }) - DRIFT,
      x1: d3.max(subs, function (d) { return d.x + d.r * s; }) + DRIFT,
      y0: d3.min(subs, function (d) { return d.y - d.r * s; }) - DRIFT,
      y1: d3.max(subs, function (d) { return d.y + d.r * s; }) + DRIFT
    };
  }

  function buildEntries() {
    var nodes = hierarchy
      .descendants()
      .slice(1)
      .sort(function (a, b) {
        return a.depth - b.depth;
      });

    entries = nodes.map(function (n) {
      var kind = n.data.kind;
      var substance = n.__anc.data.name;
      var color = colorFor(substance);

      var g = gBlobs
        .append("g")
        .attr("class", "suds-blob suds-" + kind)
        .node();
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");

      if (kind === "substance") {
        path.setAttribute("fill", d3.color(color).copy({ opacity: 0.06 }) + "");
        path.setAttribute("stroke", d3.color(color).copy({ opacity: 0.3 }) + "");
        path.setAttribute("stroke-width", "1.4");
      } else if (kind === "construct") {
        path.setAttribute("fill", d3.color(color).copy({ opacity: 0.09 }) + "");
        path.setAttribute("stroke", d3.color(color).copy({ opacity: 0.22 }) + "");
        path.setAttribute("stroke-width", "1");
      } else {
        var fill = leafFill(substance, n.data.tier);
        path.setAttribute("fill", n.data.accessible ? fill + "" : "#fbf8f4");
        path.setAttribute("stroke", fill + "");
        path.setAttribute("stroke-width", n.data.accessible ? "0.8" : "1.8");
        if (!n.data.accessible) path.setAttribute("stroke-dasharray", "4 3");
      }
      g.appendChild(path);

      var label = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "text"
      );
      label.setAttribute("class", "suds-label suds-label-" + kind);
      label.setAttribute("fill", kind === "measure" ? "#2f2b29" : color);
      label.textContent =
        kind === "measure" ? n.data.abbr : n.data.name.toUpperCase();
      gLabels.node().appendChild(label);

      var rec = {
        node: n,
        kind: kind,
        g: g,
        path: path,
        label: label,
        seed: n.__seed,
        amp: kind === "measure" ? 0.075 : kind === "construct" ? 0.035 : 0.028,
        lobes: kind === "measure" ? 3 : 4,
        text: kind === "measure" ? measureText(n) : ""
      };

      g.addEventListener("click", function (event) {
        event.stopPropagation();
        onBlobClick(rec);
      });
      g.addEventListener("mousemove", function (event) {
        showTip(rec, event);
      });
      g.addEventListener("mouseleave", hideTip);

      return rec;
    });

    totalMeasures = entries.filter(function (e) {
      return e.kind === "measure";
    }).length;
  }

  /* ------------------------------------------------------------------ *
   * accessible list view
   *
   * The blob figure is unreachable by keyboard and screen readers, so the
   * same data is always present as a semantic list. It sits visually hidden
   * behind the figure until the reader tabs into it or toggles list view.
   * ------------------------------------------------------------------ */

  function buildList(data) {
    var html = "";
    data.substances.forEach(function (s) {
      html +=
        '<section class="suds-list-sub" data-list-substance="' +
        s.name +
        '"><h3><i style="background:' +
        colorFor(s.name) +
        '"></i>' +
        s.name +
        " <span>" +
        s.count +
        " measures</span></h3>";

      s.constructs.forEach(function (c) {
        html +=
          '<div class="suds-list-con"><h4>' +
          c.name +
          (c.blurb ? " <span>" + c.blurb + "</span>" : "") +
          "</h4><ul>";

        c.measures.forEach(function (m) {
          html +=
            '<li data-list-measure="' +
            m.abbr +
            "|" +
            m.name +
            '"><a href="' +
            (m.link || m.scholar) +
            '" target="_blank" rel="noopener"><b>' +
            m.abbr +
            "</b> " +
            m.name +
            "</a><em>" +
            m.items +
            " items · " +
            m.rating +
            (m.accessible ? "" : " · not freely available") +
            "</em></li>";
        });
        html += "</ul></div>";
      });
      html += "</section>";
    });
    list.innerHTML = html;

    // pair each measure entry with its blob record so filters drive both
    var byKey = {};
    entries.forEach(function (e) {
      if (e.kind !== "measure") return;
      byKey[e.node.data.abbr + "|" + e.node.data.name] = e;
    });
    list.querySelectorAll("[data-list-measure]").forEach(function (li) {
      var e = byKey[li.dataset.listMeasure];
      if (e) e.li = li;
    });

    // tabbing into the hidden list means someone is navigating by keyboard
    list.addEventListener("focusin", function () {
      if (list.classList.contains("is-sr")) setMode("list");
    });
  }

  function setMode(next) {
    mode = next;
    list.classList.toggle("is-sr", mode !== "list");
    figure.hidden = mode === "list";
    modeBtn.textContent = mode === "list" ? "Blob view" : "List view";
    modeBtn.setAttribute("aria-pressed", mode === "list");
    if (mode === "blobs") {
      resize();
    }
  }

  /* ------------------------------------------------------------------ *
   * rendering loop
   * ------------------------------------------------------------------ */

  function resize() {
    var rect = figure.getBoundingClientRect();
    width = rect.width;
    height = rect.height;
    svg.attr("viewBox", "0 0 " + width + " " + height);
    // The visible span depends on the figure's aspect ratio, so re-derive it.
    if (focus) {
      viewTarget = focus.depth === 0 ? fitView() : nodeView(focus);
      if (!zoomInterp) view = viewTarget.slice();
    }
    updateCenterShift();
  }

  // Cached so the animation loop never reads layout (offsetWidth) per frame.
  var centerShift = 0;

  function updateCenterShift() {
    var wide = window.innerWidth >= 768;
    var open = detail.classList.contains("is-open");
    centerShift = wide && open ? detail.offsetWidth / 2 : 0;
    needsRender = true;
  }

  function frame(now) {
    requestAnimationFrame(frame);
    render(now);
  }

  function render(now) {
    var t = now / 1000;
    var animating = zoomInterp !== null;

    if (zoomInterp) {
      var p = Math.min(1, (now - zoomStart) / ZOOM_MS);
      view = zoomInterp(p);
      if (p >= 1) {
        zoomInterp = null;
        view = viewTarget.slice();
      }
      needsRender = true;
    }

    if (reduceMotion && !needsRender && !animating) return;
    needsRender = false;

    var k = width / view[2];
    var cx0 = width / 2 - centerShift;
    var cy0 = height / 2;
    var fd = !focus || focus.depth === 0 ? [0, 0] : driftOf(focus.__anc, t);

    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var dr = driftOf(e.node.__anc, t);
      var sx = (e.node.wx + dr[0] - view[0] - fd[0]) * k + cx0;
      var sy = (e.node.wy + dr[1] - view[1] - fd[1]) * k + cy0;
      var sr = e.node.wr * k;

      // cheap offscreen cull
      if (sx + sr < -60 || sx - sr > width + 60 || sy + sr < -60 || sy - sr > height + 60) {
        if (e.path.getAttribute("d") !== "") e.path.setAttribute("d", "");
        if (e.label.style.display !== "none") e.label.style.display = "none";
        continue;
      }

      e.path.setAttribute("d", blobPath(sx, sy, sr, e.seed, t, e.amp, e.lobes));

      // label visibility + size follow on-screen radius
      var show, fs, ly;
      if (e.kind === "measure") {
        show = sr > 13;
        fs = Math.max(8, Math.min(sr * 0.46, 19));
        ly = sy + fs * 0.35;
      } else if (e.kind === "construct") {
        show = sr > 32;
        fs = Math.max(8, Math.min(sr * 0.17, 14));
        ly = sy - sr * 0.72;
      } else {
        show = sr > 40;
        fs = Math.max(10, Math.min(sr * 0.115, 24));
        ly = sy - sr * 0.83;
      }

      if (show) {
        e.label.style.display = "";
        e.label.setAttribute("x", sx.toFixed(1));
        e.label.setAttribute("y", ly.toFixed(1));
        e.label.setAttribute("font-size", fs.toFixed(1));
      } else if (e.label.style.display !== "none") {
        e.label.style.display = "none";
      }
    }
  }

  /* ------------------------------------------------------------------ *
   * zoom
   * ------------------------------------------------------------------ */

  // view = [worldCx, worldCy, world units spanning the figure's width]
  function fitView() {
    var bw = bounds.x1 - bounds.x0;
    var bh = bounds.y1 - bounds.y0;
    return [
      (bounds.x0 + bounds.x1) / 2,
      (bounds.y0 + bounds.y1) / 2,
      Math.max(bw, (bh * width) / Math.max(height, 1)) * 1.02
    ];
  }

  function nodeView(node) {
    var diameter = node.wr * 2 * 1.08;
    return [
      node.wx,
      node.wy,
      (width * diameter) / Math.max(Math.min(width, height), 1)
    ];
  }

  function zoomTo(node) {
    focus = node;
    viewTarget = node.depth === 0 ? fitView() : nodeView(node);

    if (reduceMotion) {
      view = viewTarget.slice();
      zoomInterp = null;
      needsRender = true;
    } else {
      zoomFrom = view.slice();
      zoomInterp = d3.interpolateZoom(zoomFrom, viewTarget);
      ZOOM_MS = Math.max(420, Math.min(1000, zoomInterp.duration * 0.55));
      zoomStart = performance.now();
    }
    renderCrumbs();
  }

  function renderCrumbs() {
    crumbs.innerHTML = "";
    var chain = focus ? focus.ancestors().reverse() : [hierarchy];

    chain.forEach(function (n, i) {
      if (i > 0) {
        var sep = document.createElement("span");
        sep.textContent = "›";
        crumbs.appendChild(sep);
      }
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = n.depth === 0 ? "All substances" : n.data.name;
      btn.addEventListener("click", function (event) {
        event.stopPropagation();
        zoomTo(n);
      });
      crumbs.appendChild(btn);
    });
  }

  function onBlobClick(rec) {
    if (rec.kind === "measure") {
      openDetail(rec);
    } else {
      closeDetail();
      zoomTo(rec.node);
    }
  }

  /* ------------------------------------------------------------------ *
   * tooltip
   * ------------------------------------------------------------------ */

  function showTip(rec, event) {
    var d = rec.node.data;
    var html;
    if (rec.kind === "measure") {
      html =
        "<b>" +
        d.abbr +
        "</b><span>" +
        d.name +
        "</span><span>" +
        d.items +
        " items · " +
        d.rating +
        (d.accessible ? "" : " · not freely available") +
        "</span>";
    } else if (rec.kind === "construct") {
      html =
        "<b>" +
        d.name +
        "</b><span>" +
        (d.blurb || "") +
        "</span><span>" +
        rec.node.leaves().length +
        " measures</span>";
    } else {
      html =
        "<b>" +
        d.name +
        "</b><span>" +
        rec.node.leaves().length +
        " measures across " +
        rec.node.children.length +
        " constructs</span>";
    }
    tip.innerHTML = html;
    var box = figure.getBoundingClientRect();
    tip.style.left = event.clientX - box.left + "px";
    tip.style.top = event.clientY - box.top - 8 + "px";
    tip.classList.add("is-on");
  }

  function hideTip() {
    tip.classList.remove("is-on");
  }

  /* ------------------------------------------------------------------ *
   * detail panel
   * ------------------------------------------------------------------ */

  function dots(rating) {
    var n = TIERS.indexOf(rating) + 1;
    var out = '<span class="suds-dots">';
    for (var i = 1; i <= 3; i++) {
      out += '<i class="' + (i <= n ? "is-on" : "") + '"></i>';
    }
    return out + "</span>";
  }

  function psyRow(label, value) {
    if (!value) {
      return (
        "<tr><th>" +
        label +
        '</th><td class="is-none">Not reported</td></tr>'
      );
    }
    return (
      "<tr><th>" + label + "</th><td>" + value + dots(value) + "</td></tr>"
    );
  }

  function openDetail(rec) {
    var d = rec.node.data;
    var p = d.psychometrics;
    var color = colorFor(d.substance);

    if (selected) selected.g.classList.remove("is-active");
    selected = rec;
    rec.g.classList.add("is-active");

    var tags =
      '<span class="suds-tag is-substance" style="background:' +
      color +
      '">' +
      d.substance +
      "</span>";
    d.constructs.forEach(function (c) {
      tags += '<span class="suds-tag">' + c + "</span>";
    });
    tags += '<span class="suds-tag">' + d.items + " items</span>";
    tags += '<span class="suds-tag">' + d.rating + "</span>";
    if (!d.accessible) {
      tags +=
        '<span class="suds-tag is-warn">Not freely available</span>';
    } else if (d.accessType === "Needs formatting") {
      tags += '<span class="suds-tag is-warn">Needs formatting</span>';
    }

    var validity = p.validity && p.validity.length ? p.validity.join(", ") : "";
    var ts =
      p.treatmentSensitivity === true
        ? "Demonstrated"
        : p.treatmentSensitivity === false
        ? "Not applicable"
        : "";

    detail.querySelector(".suds-detail-body").innerHTML =
      "<h2>" +
      d.abbr +
      "</h2>" +
      '<p class="suds-fullname">' +
      d.name +
      "</p>" +
      '<div class="suds-tags">' +
      tags +
      "</div>" +
      "<h3>Psychometric evidence</h3>" +
      '<table class="suds-psy">' +
      psyRow("Internal consistency", p.internalConsistency) +
      psyRow("Test–retest reliability", p.testRetest) +
      psyRow("Normative data", p.norms) +
      "<tr><th>Validity evidence</th><td" +
      (validity ? ">" + validity : ' class="is-none">Not reported') +
      "</td></tr>" +
      "<tr><th>Treatment sensitivity</th><td" +
      (ts === "Demonstrated"
        ? ">" + ts
        : ' class="is-none">' + (ts || "Not reported")) +
      "</td></tr>" +
      "</table>" +
      '<div class="suds-links">' +
      (d.link
        ? '<a class="suds-btn suds-btn-primary" href="' +
          d.link +
          '" target="_blank" rel="noopener">Open measure</a>'
        : "") +
      '<a class="suds-btn suds-btn-ghost" href="' +
      d.scholar +
      '" target="_blank" rel="noopener">Google Scholar</a>' +
      "</div>" +
      (d.source
        ? '<p class="suds-cite">Primary reference: ' + d.source + "</p>"
        : "");

    detail.classList.add("is-open");
    updateCenterShift();
  }

  function closeDetail() {
    detail.classList.remove("is-open");
    if (selected) selected.g.classList.remove("is-active");
    selected = null;
    updateCenterShift();
  }

  /* ------------------------------------------------------------------ *
   * filtering
   * ------------------------------------------------------------------ */

  function matches(rec) {
    var d = rec.node.data;
    if (filters.substances[d.substance] === false) return false;
    if (filters.freeOnly && !d.accessible) return false;
    if (d.items > filters.maxItems) return false;
    var tierKeys = Object.keys(filters.tiers);
    if (tierKeys.length && !filters.tiers[d.rating]) return false;
    if (filters.query && rec.text.indexOf(filters.query) === -1) return false;
    return true;
  }

  function applyFilters() {
    var hits = 0;
    var live = new Set();

    entries.forEach(function (e) {
      if (e.kind !== "measure") return;
      var ok = matches(e);
      e.g.classList.toggle("is-dim", !ok);
      if (e.li) e.li.hidden = !ok;
      if (ok) {
        hits++;
        e.node.ancestors().forEach(function (a) {
          live.add(a);
        });
      }
    });

    entries.forEach(function (e) {
      if (e.kind === "measure") return;
      e.g.classList.toggle("is-dim", !live.has(e.node));
    });

    // collapse list sections that no longer hold a visible measure
    list.querySelectorAll(".suds-list-con").forEach(function (el) {
      el.hidden = !el.querySelector("li:not([hidden])");
    });
    list.querySelectorAll(".suds-list-sub").forEach(function (el) {
      el.hidden = !el.querySelector(".suds-list-con:not([hidden])");
    });

    matchOut.textContent =
      hits === totalMeasures
        ? totalMeasures + " measures"
        : hits + " of " + totalMeasures + " measures";
    empty.classList.toggle("is-on", hits === 0);
    needsRender = true;
  }

  /* ------------------------------------------------------------------ *
   * controls
   * ------------------------------------------------------------------ */

  function wireControls() {
    searchInput.addEventListener("input", function () {
      filters.query = this.value.trim().toLowerCase();
      applyFilters();
    });

    root.querySelectorAll("[data-tier]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tier = btn.dataset.tier;
        if (filters.tiers[tier]) delete filters.tiers[tier];
        else filters.tiers[tier] = true;
        btn.setAttribute("aria-pressed", !!filters.tiers[tier]);
        applyFilters();
      });
    });

    var freeBtn = root.querySelector("[data-free]");
    freeBtn.addEventListener("click", function () {
      filters.freeOnly = !filters.freeOnly;
      freeBtn.setAttribute("aria-pressed", filters.freeOnly);
      applyFilters();
    });

    itemsRange.addEventListener("input", function () {
      var v = +this.value;
      filters.maxItems = v >= +this.max ? Infinity : v;
      itemsOut.textContent = v >= +this.max ? "any" : "≤ " + v;
      applyFilters();
    });

    root.querySelectorAll("[data-substance]").forEach(function (key) {
      key.addEventListener("click", function () {
        var name = key.dataset.substance;
        var on = filters.substances[name] !== false;
        filters.substances[name] = !on;
        key.setAttribute("aria-pressed", !on);
        applyFilters();
      });
    });

    root.querySelector(".suds-reset").addEventListener("click", function () {
      filters = {
        query: "",
        tiers: {},
        freeOnly: false,
        maxItems: Infinity,
        substances: {}
      };
      searchInput.value = "";
      itemsRange.value = itemsRange.max;
      itemsOut.textContent = "any";
      root.querySelectorAll('[aria-pressed="true"]').forEach(function (el) {
        if (el.hasAttribute("data-substance")) return;
        el.setAttribute("aria-pressed", "false");
      });
      root.querySelectorAll("[data-substance]").forEach(function (el) {
        el.setAttribute("aria-pressed", "true");
      });
      applyFilters();
      closeDetail();
      zoomTo(hierarchy);
    });

    modeBtn.addEventListener("click", function () {
      setMode(mode === "list" ? "blobs" : "list");
    });

    detail
      .querySelector(".suds-detail-close")
      .addEventListener("click", closeDetail);

    svg.node().addEventListener("click", function () {
      hideTip();
      if (detail.classList.contains("is-open")) {
        closeDetail();
        return;
      }
      if (focus && focus.depth > 0) zoomTo(focus.parent);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      if (detail.classList.contains("is-open")) closeDetail();
      else if (focus && focus.depth > 0) zoomTo(focus.parent);
    });

    window.addEventListener("resize", resize);

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) needsRender = true;
    });
  }

  /* ------------------------------------------------------------------ *
   * boot
   * ------------------------------------------------------------------ */

  function fillStats(data) {
    var constructs = new Set();
    data.substances.forEach(function (s) {
      s.constructs.forEach(function (c) {
        constructs.add(c.name);
      });
    });
    var stats = {
      "suds-n-measures": data.meta.included,
      "suds-n-substances": data.substances.length,
      "suds-n-constructs": constructs.size,
      "suds-n-screened": data.meta.screened
    };
    Object.keys(stats).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = stats[id];
    });
  }

  d3.json(root.dataset.src)
    .then(function (data) {
      fillStats(data);
      hierarchy = buildHierarchy(data);
      buildEntries();
      buildList(data);
      focus = hierarchy;
      resize();
      view = fitView();
      viewTarget = view.slice();
      renderCrumbs();
      wireControls();
      applyFilters();

      var max = d3.max(hierarchy.leaves(), function (d) {
        return d.data.items;
      });
      itemsRange.max = max;
      itemsRange.value = max;
      itemsOut.textContent = "any";

      // Paint once synchronously: rAF never fires while the tab is in the
      // background, which would otherwise leave the figure blank on load.
      render(performance.now());
      requestAnimationFrame(frame);
      figure.style.opacity = 1;
    })
    .catch(function (err) {
      figure.style.opacity = 1;
      empty.textContent =
        "The measures data could not be loaded. Please refresh the page.";
      empty.classList.add("is-on");
      if (window.console) console.error(err);
    });
})();
