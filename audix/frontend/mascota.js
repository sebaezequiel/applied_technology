// Mascota: hurón con bufanda verde, dibujado en SVG.
// Cuatro estados, según la racha: dormido, despertándose, con auriculares y celebrando.

const Mascota = (() => {
  const CUERPO = {
    cola: '<path d="M58 175 Q18 168 24 138" fill="none" stroke="#3a3a3a" stroke-width="3" stroke-linecap="round"/>',
    cuerpo: '<path d="M60 112 Q40 170 52 192 L112 192 Q126 166 104 112 Z" fill="#fff" stroke="#3a3a3a" stroke-width="3" stroke-linejoin="round"/>',
    orejas:
      '<path d="M42 46 L40 14 L66 34 Z" fill="#fff" stroke="#3a3a3a" stroke-width="3" stroke-linejoin="round"/>' +
      '<path d="M122 46 L124 14 L98 34 Z" fill="#fff" stroke="#3a3a3a" stroke-width="3" stroke-linejoin="round"/>',
    cabeza: '<ellipse cx="82" cy="72" rx="48" ry="42" fill="#fff" stroke="#3a3a3a" stroke-width="3"/>',
    bufanda:
      '<rect x="50" y="110" width="64" height="16" rx="6" fill="#2f6b3a"/>' +
      '<rect x="60" y="110" width="5" height="16" fill="#cfe3c5"/>' +
      '<rect x="78" y="110" width="5" height="16" fill="#cfe3c5"/>' +
      '<rect x="96" y="110" width="5" height="16" fill="#cfe3c5"/>' +
      '<rect x="92" y="122" width="12" height="34" rx="4" fill="#2f6b3a"/>',
  };

  const AURICULARES =
    '<path d="M36 70 Q36 18 82 18 Q128 18 128 70" fill="none" stroke="#2b2a27" stroke-width="5"/>' +
    '<rect x="27" y="62" width="14" height="24" rx="6" fill="#2b2a27"/>' +
    '<rect x="123" y="62" width="14" height="24" rx="6" fill="#2b2a27"/>';

  const ZZZ =
    '<text x="112" y="-2" font-size="18" fill="#8a8579" font-family="sans-serif">z</text>' +
    '<text x="126" y="-18" font-size="13" fill="#8a8579" font-family="sans-serif">z</text>' +
    '<text x="138" y="-32" font-size="10" fill="#8a8579" font-family="sans-serif">z</text>';

  const DESTELLOS =
    '<path d="M30 34 L28 6" stroke="#D97757" stroke-width="3" stroke-linecap="round"/>' +
    '<path d="M82 -4 L82 -18" stroke="#D97757" stroke-width="3" stroke-linecap="round"/>' +
    '<path d="M134 34 L140 8" stroke="#D97757" stroke-width="3" stroke-linecap="round"/>';

  const FUEGO =
    '<path d="M82 -22 Q68 -6 74 8 Q78 -2 82 2 Q86 -2 90 8 Q96 -6 82 -22 Z" fill="#D97757"/>' +
    '<path d="M20 40 Q12 24 22 14 Q22 28 30 32 Q28 18 36 10 Q40 30 32 40 Z" fill="#D97757"/>' +
    '<path d="M140 40 Q148 24 138 14 Q138 28 130 32 Q132 18 124 10 Q120 30 128 40 Z" fill="#D97757"/>';

  const ESTADOS = {
    dormido: {
      alt: "Hurón dormido",
      fx: ZZZ,
      auriculares: "",
      cara:
        '<path d="M60 72 Q66 78 72 72" fill="none" stroke="#222" stroke-width="2.5" stroke-linecap="round"/>' +
        '<path d="M92 72 Q98 78 104 72" fill="none" stroke="#222" stroke-width="2.5" stroke-linecap="round"/>',
      mejillasY: 86,
    },
    despertandose: {
      alt: "Hurón despertándose",
      fx: DESTELLOS,
      auriculares: "",
      cara:
        '<path d="M60 70 Q66 64 72 70" fill="none" stroke="#222" stroke-width="2.5" stroke-linecap="round"/>' +
        '<path d="M92 70 Q98 64 104 70" fill="none" stroke="#222" stroke-width="2.5" stroke-linecap="round"/>' +
        '<path d="M78 86 Q82 90 86 86" fill="none" stroke="#222" stroke-width="2" stroke-linecap="round"/>',
      mejillasY: 86,
    },
    auriculares: {
      alt: "Hurón con auriculares",
      fx: "",
      auriculares: AURICULARES,
      cara:
        '<circle cx="66" cy="70" r="5" fill="#222"/>' +
        '<circle cx="98" cy="70" r="5" fill="#222"/>' +
        '<path d="M78 84 Q82 88 86 84" fill="none" stroke="#222" stroke-width="2" stroke-linecap="round"/>',
      mejillasY: 84,
    },
    celebrando: {
      alt: "Hurón celebrando con fuego",
      fx: FUEGO,
      auriculares: AURICULARES,
      cara:
        '<path d="M60 72 Q66 64 72 72" fill="none" stroke="#222" stroke-width="2.5" stroke-linecap="round"/>' +
        '<path d="M92 72 Q98 64 104 72" fill="none" stroke="#222" stroke-width="2.5" stroke-linecap="round"/>' +
        '<path d="M74 84 Q82 96 90 84" fill="#222"/>',
      mejillasY: 84,
    },
  };

  function svg(estado = "dormido") {
    const e = ESTADOS[estado] || ESTADOS.dormido;
    const mejillas =
      `<circle cx="58" cy="${e.mejillasY}" r="6" fill="#f4a6a0" opacity="0.7"/>` +
      `<circle cx="106" cy="${e.mejillasY}" r="6" fill="#f4a6a0" opacity="0.7"/>`;
    return (
      `<svg viewBox="0 -30 160 230" role="img" aria-label="${e.alt}">` +
      e.fx +
      CUERPO.cola +
      CUERPO.cuerpo +
      CUERPO.orejas +
      CUERPO.cabeza +
      e.auriculares +
      e.cara +
      mejillas +
      CUERPO.bufanda +
      "</svg>"
    );
  }

  return { svg, ESTADOS };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = Mascota;
} else {
  window.Mascota = Mascota;
}
