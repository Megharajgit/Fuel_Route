import * as maplibregl from "https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.mjs";

(() => {
  const form = document.querySelector("#route-form");
  const layout = document.querySelector(".layout");
  const empty = document.querySelector("#empty");
  const loading = document.querySelector("#loading");
  const result = document.querySelector("#result");
  const error = document.querySelector("#error");
  const button = document.querySelector("#submit");
  let map;
  let routeLayers = [];
  let markers = [];

  function dollars(value) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
  }

  function makeMarker(label, kind) {
    const element = document.createElement("div");
    element.className = `fuel-map-marker ${kind}`;
    const text = document.createElement("span");
    text.textContent = label;
    element.append(text);
    return element;
  }

  function addFuelMarker(point, label, kind, popupLines = []) {
    const marker = new maplibregl.Marker({ element: makeMarker(label, kind), anchor: "bottom" })
      .setLngLat([point.longitude, point.latitude]);
    if (popupLines.length) {
      const content = document.createElement("div");
      content.className = "map-popup";
      popupLines.forEach((line, index) => {
        const item = document.createElement(index === 0 ? "strong" : "span");
        item.textContent = line;
        content.append(item);
      });
      marker.setPopup(new maplibregl.Popup({ offset: 18 }).setDOMContent(content));
    }
    marker.addTo(map);
    markers.push(marker);
  }

  function drawRoute(data) {
    if (!map.isStyleLoaded()) {
      map.once("load", () => drawRoute(data));
      return;
    }
    markers.forEach((marker) => marker.remove());
    markers = [];
    routeLayers.forEach((id) => {
      if (map.getLayer(id)) map.removeLayer(id);
    });
    if (map.getSource("fuelwise-route")) map.removeSource("fuelwise-route");
    routeLayers = [];

    const coordinates = data.route.coordinates.map(([latitude, longitude]) => [longitude, latitude]);
    map.addSource("fuelwise-route", {
      type: "geojson",
      data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } },
    });
    map.addLayer({
      id: "fuelwise-route-casing", type: "line", source: "fuelwise-route",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "fuelwise-route-line", type: "line", source: "fuelwise-route",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#24664f", "line-width": 5 },
    });
    routeLayers = ["fuelwise-route-casing", "fuelwise-route-line"];

    addFuelMarker(data.start, "S", "start-marker");
    addFuelMarker(data.finish, "F", "finish-marker");
    data.stops.forEach((stop, index) => {
      addFuelMarker(stop, String(index + 1), "stop-marker", [
        stop.name,
        `${stop.city}, ${stop.state}`,
        `${dollars(stop.pricePerGallon)} per gallon`,
      ]);
    });

    const bounds = new maplibregl.LngLatBounds();
    coordinates.forEach((coordinate) => bounds.extend(coordinate));
    map.fitBounds(bounds, { padding: 58, maxZoom: 7, duration: 600 });
    window.setTimeout(() => map.resize(), 80);
  }

  function showMap(data) {
    if (!map) {
      map = new maplibregl.Map({
        container: "map",
        style: "https://tiles.openfreemap.org/styles/positron",
        center: [-98.5, 39.8],
        zoom: 3.5,
        cooperativeGestures: true,
        attributionControl: true,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
      map.once("load", () => drawRoute(data));
    } else {
      drawRoute(data);
    }
  }

  function render(data) {
    const startName = data.start.label.split(",")[0];
    const finishName = data.finish.label.split(",")[0];
    document.querySelector("#route-title").textContent = `${startName} to ${finishName}`;
    document.querySelector("#distance").textContent = `${new Intl.NumberFormat().format(data.route.distanceMiles)} mi`;
    document.querySelector("#cost").textContent = dollars(data.fuel.totalEstimatedCost);
    document.querySelector("#stop-count").textContent = data.stops.length;
    document.querySelector("#total-gallons").textContent = `${data.fuel.totalGallons} gal estimated`;
    const list = document.querySelector("#stops");
    list.replaceChildren();
    if (!data.stops.length) {
      const item = document.createElement("li");
      item.className = "no-stops";
      item.textContent = "No intermediate stops needed. Start with enough fuel for the trip.";
      list.append(item);
    }
    data.stops.forEach((stop, index) => {
      const item = document.createElement("li");
      item.className = "stop-item";
      item.innerHTML = `<span class="stop-number">${index + 1}</span><div class="stop-info"><strong>${stop.name}</strong><span>${stop.city}, ${stop.state} · mile ${Math.round(stop.routeMile)}</span><small>${stop.address || "On route"}</small></div><div class="stop-price"><strong>${dollars(stop.pricePerGallon)}<small>/gal</small></strong><span>Fuel to next leg</span></div>`;
      list.append(item);
    });
    document.querySelector("#assumption").textContent = data.assumptions[0] + " " + data.assumptions[1];
    empty.hidden = true;
    loading.hidden = true;
    result.hidden = false;
    layout.classList.add("has-results");
    showMap(data);
    window.setTimeout(() => document.querySelector(".result-heading").scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    result.hidden = true;
    empty.hidden = true;
    loading.hidden = false;
    button.disabled = true;
    button.querySelector("span").textContent = "Planning your route…";
    try {
      const response = await fetch("/api/route/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start: form.start.value, finish: form.finish.value }),
        signal: AbortSignal.timeout(210000),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Could not plan that route.");
      render(payload);
    } catch (cause) {
      loading.hidden = true;
      empty.hidden = false;
      error.textContent = cause.name === "TimeoutError" ? "This route is taking longer than expected. Please try again." : cause.message;
      error.hidden = false;
    } finally {
      button.disabled = false;
      button.querySelector("span").textContent = "Plan my route";
    }
  });

  document.querySelector("#reset").addEventListener("click", () => {
    result.hidden = true;
    empty.hidden = false;
    error.hidden = true;
    layout.classList.remove("has-results");
    form.start.focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
})();