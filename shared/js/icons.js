const NS = "http://www.w3.org/2000/svg";
const PATHS = {
  chat: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
  gauge: ["M3 17a9 9 0 1 1 18 0", "M12 17l4-5", "M5 20h14"],
  bell: ["M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9", "M13.7 21a2 2 0 0 1-3.4 0"],
  clock: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M12 6v6l4 2"],
  monitor: ["M3 4h18v12H3z", "M8 20h8", "M12 16v4"],
  sliders: ["M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"],
  send: ["M22 2L11 13", "M22 2l-7 20-4-9-9-4z"],
  trash: ["M3 6h18", "M8 6V4h8v2", "M19 6l-1 14H6L5 6"],
  plus: ["M12 5v14M5 12h14"],
  refresh: ["M23 4v6h-6", "M1 20v-6h6", "M3.5 9a9 9 0 0 1 15-3.4L23 10M1 14l4.5 4.4A9 9 0 0 0 20.5 15"],
  lock: ["M5 11h14v10H5z", "M8 11V7a4 4 0 0 1 8 0v4"],
  volume: ["M11 5L6 9H2v6h4l5 4z", "M15.5 8.5a5 5 0 0 1 0 7"],
  sun: ["M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"],
  globe: ["M2 12a10 10 0 1 0 20 0 10 10 0 0 0-20 0", "M2 12h20", "M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"],
  power: ["M18.4 6.6a9 9 0 1 1-12.8 0", "M12 2v10"],
  check: ["M20 6L9 17l-5-5"],
  x: ["M18 6L6 18M6 6l12 12"],
  shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"],
  mic: ["M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z", "M19 11a7 7 0 0 1-14 0", "M12 18v3"],
  copy: ["M9 9h11v11H9z", "M5 15H4V4h11v1"],
  down: ["M6 9l6 6 6-6"],
  moon: ["M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z"],
  offline: ["M2 8.8a15 15 0 0 1 4-2.4M22 8.8a15 15 0 0 0-8.5-3.7M5 12.9a10 10 0 0 1 3.5-2M19 12.9a10 10 0 0 0-3.2-1.8M8.5 16.4a5 5 0 0 1 7 0", "M12 20h.01", "M2 2l20 20"],
  info: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M12 16v-5", "M12 8h.01"],
  mail: ["M3 5h18v14H3z", "M3 6l9 7 9-7"],
  calendar: ["M3 5h18v16H3z", "M3 10h18", "M8 3v4M16 3v4"],
  sparkle: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"],
  cloud: ["M7 18a4 4 0 0 1-.6-7.96A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9z"],
  folder: ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
};

export function icon(name, size = 20) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  for (const d of PATHS[name] || []) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}
