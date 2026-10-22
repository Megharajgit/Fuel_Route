(() => {
  const form = document.querySelector("#route-form");
  const empty = document.querySelector("#empty");
  const loading = document.querySelector("#loading");
  const result = document.querySelector("#result");
  const error = document.querySelector("#error");
  const button = document.querySelector("#submit");
  let map;
  let layers;

  function dollars(value) { return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value); }

  function showMap(data) {
    if (!window.L) return;
    if (!map) {
      map = L.map("map", { scrollWheelZoom: false, zoomControl: true });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(map);
    }
    if (layers) layers.forEach((layer) => layer.remove());
    layers = [];
    const route = data.route.coordinates;
    const line = L.polyline(route, { color: "#216d53", weight: 5, opacity: 0.9, lineCap: "round" }).addTo(map);
    layers.push(line);
    const start = data.start;
    const finish = data.finish;
    [[start, "S", "#285b47"], [finish, "F", "#e79057"]].forEach(([point, label, color]) => {
      layers.push(L.marker([point.latitude, point.longitude], { icon: L.divIcon({ className: "map-marker", html: `<span style="--marker:${color}">${label}</span>`, iconSize: [30, 30], iconAnchor: [15, 15] }) }).addTo(map));
    });
    data.stops.forEach((stop, index) => {
      const marker = L.marker([stop.latitude, stop.longitude], { icon: L.divIcon({ className: "map-marker", html: `<span class="stop-marker">${index + 1}</span>`, iconSize: [28, 28], iconAnchor: [14, 14] }) }).addTo(map);
      marker.bindPopup(`<strong>${stop.name}</strong><br>${stop.city}, ${stop.state}<br>${dollars(stop.pricePerGallon)}/gal`);
      layers.push(marker);
    });
    map.fitBounds(line.getBounds(), { padding: [28, 28] });
    setTimeout(() => map.invalidateSize(), 50);
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
    showMap(data);
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
        signal: AbortSignal.timeout(55000),
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
    form.start.focus();
  });
})();
