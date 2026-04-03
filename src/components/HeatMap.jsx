import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// ── simpleheat inline (Vladimir Agafonkin, ISC) ──────────────────────────────
function Simpleheat(canvas) {
  this._canvas = canvas;
  this._ctx = canvas.getContext('2d');
  this._width = canvas.width;
  this._height = canvas.height;
  this._max = 1;
  this._data = [];
}
Simpleheat.prototype = {
  defaultRadius: 25,
  defaultGradient: { 0.4: 'blue', 0.65: 'lime', 0.8: 'yellow', 1.0: 'red' },
  data(d)  { this._data = d; return this; },
  max(m)   { this._max = m; return this; },
  radius(r, blur) {
    blur = blur == null ? 15 : blur;
    const c = this._circle = document.createElement('canvas');
    const ctx = c.getContext('2d');
    const e = (this._r = r + blur) * 2;
    c.width = c.height = e;
    ctx.shadowOffsetX = ctx.shadowOffsetY = 200;
    ctx.shadowBlur = blur;
    ctx.shadowColor = 'black';
    ctx.beginPath();
    ctx.arc(e / 2 - 200, e / 2 - 200, r, 0, Math.PI * 2, true);
    ctx.closePath();
    ctx.fill();
    return this;
  },
  gradient(grad) {
    const c = document.createElement('canvas');
    const ctx = c.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 0, 256);
    c.width = 1; c.height = 256;
    for (const s in grad) g.addColorStop(+s, grad[s]);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 1, 256);
    this._grad = ctx.getImageData(0, 0, 1, 256).data;
    return this;
  },
  draw(minOpacity) {
    if (!this._circle) this.radius(this.defaultRadius);
    if (!this._grad)   this.gradient(this.defaultGradient);
    const ctx = this._ctx;
    ctx.clearRect(0, 0, this._width, this._height);
    for (const p of this._data) {
      ctx.globalAlpha = Math.max(p[2] / this._max, minOpacity || 0.05);
      ctx.drawImage(this._circle, p[0] - this._r, p[1] - this._r);
    }
    const img = ctx.getImageData(0, 0, this._width, this._height);
    this._colorize(img.data, this._grad);
    ctx.putImageData(img, 0, 0);
    return this;
  },
  _colorize(pixels, grad) {
    for (let i = 3, len = pixels.length; i < len; i += 4) {
      const v = pixels[i] * 4;
      if (v) { pixels[i-3] = grad[v]; pixels[i-2] = grad[v+1]; pixels[i-1] = grad[v+2]; }
    }
  },
};

// ── HeatLayer para Leaflet ───────────────────────────────────────────────────
const HeatLayer = L.Layer.extend({
  initialize(latlngs, opts) { this._latlngs = latlngs; L.setOptions(this, opts); },
  onAdd(map) {
    this._map = map;
    const canvas = this._canvas = L.DomUtil.create('canvas', 'leaflet-heatmap-layer leaflet-layer');
    const size = map.getSize();
    canvas.width = size.x; canvas.height = size.y;
    const animated = map.options.zoomAnimation && L.Browser.any3d;
    L.DomUtil.addClass(canvas, 'leaflet-zoom-' + (animated ? 'animated' : 'hide'));
    map.getPanes().overlayPane.appendChild(canvas);
    this._heat = new Simpleheat(canvas);
    this._updateOptions();
    map.on('moveend', this._reset, this);
    if (animated) map.on('zoomanim', this._animateZoom, this);
    this._reset();
  },
  onRemove(map) {
    map.getPanes().overlayPane.removeChild(this._canvas);
    map.off('moveend', this._reset, this);
    if (map.options.zoomAnimation) map.off('zoomanim', this._animateZoom, this);
  },
  _updateOptions() {
    const o = this.options;
    this._heat.radius(o.radius || 25, o.blur);
    if (o.gradient) this._heat.gradient(o.gradient);
    if (o.max) this._heat.max(o.max);
  },
  _reset() {
    const topLeft = this._map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(this._canvas, topLeft);
    const size = this._map.getSize();
    if (this._heat._width !== size.x)  { this._canvas.width  = this._heat._width  = size.x; }
    if (this._heat._height !== size.y) { this._canvas.height = this._heat._height = size.y; }
    this._redraw();
  },
  _redraw() {
    const r = this._heat._r;
    const size = this._map.getSize();
    const bounds = new L.Bounds(L.point([-r, -r]), size.add([r, r]));
    const pts = [];
    for (const ll of this._latlngs) {
      const p = this._map.latLngToContainerPoint(ll);
      if (bounds.contains(p)) pts.push([Math.round(p.x), Math.round(p.y), ll[2] ?? 1]);
    }
    this._heat.data(pts).draw(this.options.minOpacity);
    this._frame = null;
  },
  _animateZoom(e) {
    const scale = this._map.getZoomScale(e.zoom);
    const offset = this._map._getCenterOffset(e.center)._multiplyBy(-scale).subtract(this._map._getMapPanePos());
    L.DomUtil.setTransform(this._canvas, offset, scale);
  },
});

// ── Bounding box Portugal continental + ilhas ────────────────────────────────
const PT = { minLat: 30, maxLat: 43, minLon: -33, maxLon: 0 };

export default function HeatMap({ pontos }) {
  const divRef = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    if (!divRef.current || mapRef.current) return;

    const map = L.map(divRef.current, { zoomControl: true, scrollWheelZoom: false });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 17,
    }).addTo(map);

    const maxCount = Math.max(...pontos.map((p) => p.count), 1);
    const heatData = pontos.map((p) => [p.lat, p.lon, p.count / maxCount]);

    new HeatLayer(heatData, {
      radius: 22,
      blur: 20,
      max: 1,
      minOpacity: 0.03,
      gradient: { 0.3: '#fef3c7', 0.55: '#fbbf24', 0.75: '#d97706', 0.92: '#92400e', 1.0: '#7c2d12' },
    }).addTo(map);

    // Zoom para mostrar todos os pontos de Portugal (continental + ilhas)
    const ptPontos = pontos.filter(p => p.lat >= PT.minLat && p.lat <= PT.maxLat && p.lon >= PT.minLon && p.lon <= PT.maxLon);
    if (ptPontos.length > 0) {
      const bounds = L.latLngBounds(ptPontos.map(p => [p.lat, p.lon]));
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 9 });
    } else {
      map.setView([39.5, -8], 7);
    }

    mapRef.current = map;
    return () => { if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; } };
  }, []);

  return (
    <div ref={divRef} style={{ height: '380px', width: '100%', borderRadius: '0.5rem', overflow: 'hidden' }} />
  );
}
