"""OBERFLAECHE: Marktampel oben, Toene, Zukunftsdesign und Erklaerungen der
Scanner-Kriterien (Mathias und Gerhard, 23.09.2026).

Die Auftraege, woertlich:
  * "Baue bei jedem Feld im Scanner eine Schaltflaeche unter wirklich jedem
    Kriterium ein, die bei Anklicken eine kurze Erklaerung des Kriteriums auf
    Deutsch liefert." Die Merkmale tragen ihre Erklaerung selbst
    (scanner_ansicht.FELDER); hier stehen die uebrigen Kriterien.
  * "Per Button soll ein wirklich cooles, futuristisches Design aktivierbar
    sein mit Animationen etc." DESIGN_ZUKUNFT, reines CSS: Es veraendert
    nichts an Aufbau, Reihenfolge oder Beschriftung, ein Screenreader liest
    also Zeichen fuer Zeichen dasselbe. Alles Bewegte steht still, wenn das
    System weniger Bewegung verlangt (prefers-reduced-motion).
  * "Baue Sounds ein, die das erfolgreiche Durchfuehren einer Aktion
    anzeigen ... Erstelle coole Sounds und mache sie waehlbar." KLANG_JS
    erzeugt die Toene im Browser (Web Audio), es gibt keine Tondateien. Ein
    Tastendruck oder Klick irgendwo auf der Seite schaltet den Ton frei; das
    verlangen die Browser, auch das iPhone.
  * "die Marktampel muss auf jeder Seite des gesamten Streamlit-Tools
    ersichtlich sein, sie muss ganz oben". ampel_saetze und ampel_html.

Aufruf:
    python oberflaeche.py --selbsttest
"""

import argparse
import html
import sys
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Marktampel
# ---------------------------------------------------------------------------

# Der Nachtscan rechnet um 00:00 Wiener Zeit, das ist 18:00 in New York; bis
# die Ampel im Repo steht, vergeht etwa eine halbe Stunde. Ab dieser Stunde
# New Yorker Zeit muss die Ampel dem Schluss des Tages gelten.
AMPEL_AB_STUNDE_NY = 19
SCHLUSS_NY = (16, 30)


def _werktag_davor(tag: date) -> date:
    tag -= timedelta(days=1)
    while tag.weekday() >= 5:
        tag -= timedelta(days=1)
    return tag


def ampel_tage(jetzt_ny: datetime) -> tuple:
    """(fruehester, spaetester) Schluss, dem die Ampel jetzt gelten darf. Ab
    AMPEL_AB_STUNDE_NY Uhr New Yorker Zeit muss sie dem Tag selbst gelten;
    zwischen Handelsschluss und dieser Stunde darf sie noch dem Schluss davor
    gelten oder schon dem heutigen. Feiertage kennt die App nicht: An einem
    US-Feiertag heisst es deshalb, die Ampel sei nicht verfuegbar."""
    tag = jetzt_ny.date()
    werktag = tag.weekday() < 5
    spaet = tag if werktag and (jetzt_ny.hour, jetzt_ny.minute) >= SCHLUSS_NY else _werktag_davor(tag)
    frueh = tag if werktag and jetzt_ny.hour >= AMPEL_AB_STUNDE_NY else _werktag_davor(tag)
    return frueh, spaet


def ampel_saetze(daten, jetzt_ny: datetime, nachtscan_tag=None) -> tuple:
    """(Farbe oder None, Kopfsatz, Satz mit den Einzelheiten oder "").

    OBEN EIN EINFACHER SATZ (Antwort 29 vom 24.09.2026): Farbe, Schluss
    und was die Farbe heute bedeutet; darunter die Einzelheiten je Index in
    den Worten der ersten Meldung des Waechters (marktampel.zeile) und der
    Satz aus Antwort 30, dass die Farbe den Ampelregeln folgt und die Zaehlung
    nach IBD nur Auskunft ist.

    DER MASSSTAB (Antwort 10 vom 24.09.2026): der letzte Handelstag, den
    der Nachtscan tatsaechlich gerechnet hat (nachtscan_tag, aus der
    Sektor-Rangliste desselben Laufs). So steht die Ampel auch an einem
    US-Feiertag, und eine Ampel, die der Nachtscan nicht erneuert hat, faellt
    trotzdem auf. Ohne nachtscan_tag gilt die Rechnung nach Wochentagen
    (ampel_tage). Eine Farbe steht nur da, wenn die Ampel diesem Schluss gilt;
    eine Farbe vom falschen Tag waere schlimmer als keine (Gerhard, Etappe 0)."""
    import marktampel
    if not isinstance(daten, dict) or daten.get("farbe") not in marktampel.FARBWORT:
        return None, "Marktampel nicht verfügbar; es liegt keine Berechnung vor.", ""
    tag = str(daten.get("handelstag") or "")[:10]
    soll = str(nachtscan_tag or "")[:10]
    if soll:
        gilt = tag >= soll
    else:
        gilt = tag in {d.isoformat() for d in ampel_tage(jetzt_ny)}
    if not gilt:
        kopf = ("Marktampel nicht verfügbar; die letzte Berechnung gilt dem Schluss vom "
                f"{marktampel._datum_de(tag)}")
        if soll:
            kopf += f", der Nachtscan hat schon den Schluss vom {marktampel._datum_de(soll)} gerechnet"
        return None, kopf + ".", ""
    teile = marktampel.zeile(daten, vortag=tag).split("; ")
    kopf = f"{teile[0]}: {marktampel.einfacher_satz(daten)}."
    einzeln = ("Einzelheiten: " + "; ".join(teile[1:]) + ". ") if len(teile) > 1 else ""
    return daten["farbe"], kopf, einzeln + marktampel.REGEL_SATZ


# DAS AUGENSYMBOL IM PASSWORTFELD (Antwort 28 vom 24.09.2026): Neben dem
# Passwortfeld liegt Streamlits Knopf zum Anzeigen des Passworts; ein
# Screenreader las ihn als "visibility" vor, das Wort des Symbols. Das Skript
# gibt dem Knopf einen Namen, der zum Zustand passt, und blendet das Symbolwort
# fuer Screenreader aus. Es laeuft in der Seite der App (st.html mit
# unsafe_allow_javascript) und beobachtet die Seite, weil das Feld erst nach dem
# Skript entstehen kann und der Knopf beim Umschalten neu gezeichnet wird. Kein
# Kleiner-Zeichen, damit es sicher in einem script-Element steht.
PASSWORT_AUGE_JS = """(function () {
  if (window.__heliotPwWache) { window.__heliotPwWache.beschriften(); return; }
  function beschriften() {
    var felder = document.querySelectorAll('input[type="password"], input[data-heliot-pw]');
    felder.forEach(function (feld) {
      feld.setAttribute("data-heliot-pw", "1");
      var wurzel = feld.closest('[data-testid="stTextInputRootElement"]') || feld.closest('[data-baseweb="input"]');
      if (!wurzel) { return; }
      var name = feld.type === "password" ? "Passwort zeigen" : "Passwort verbergen";
      wurzel.querySelectorAll("button").forEach(function (knopf) {
        if (knopf.getAttribute("aria-label") !== name) {
          knopf.setAttribute("aria-label", name);
          knopf.setAttribute("title", name);
        }
        knopf.querySelectorAll("span, i, svg").forEach(function (zeichen) {
          zeichen.setAttribute("aria-hidden", "true");
        });
      });
    });
  }
  var geplant = false;
  var wache = new MutationObserver(function () {
    if (geplant) { return; }
    geplant = true;
    window.requestAnimationFrame(function () { geplant = false; beschriften(); });
  });
  wache.observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ["type"]});
  window.__heliotPwWache = {beschriften: beschriften, wache: wache};
  beschriften();
})();
"""


def ampel_html(farbe, kopf: str, satz: str) -> str:
    """Die Ampel als HTML fuer st.html: ein farbiger Punkt fuer Sehende,
    fuer Screenreader verborgen, und der Text. Kein Emoji (Mathias)."""
    klasse = f"heliot-ampel heliot-ampel-{farbe or 'grau'}"
    zeile = f'<p class="heliot-ampel-kopf"><span class="heliot-orb" aria-hidden="true"></span>{html.escape(kopf)}</p>'
    if satz:
        zeile += f'<p class="heliot-ampel-satz">{html.escape(satz)}</p>'
    return f'<div class="{klasse}">{zeile}</div>'


# Die Ampel im Standarddesign: nur der Punkt braucht Stil.
AMPEL_CSS = """
.heliot-ampel{margin:0 0 .5rem 0}
.heliot-ampel p{margin:.1rem 0}
.heliot-ampel-kopf{font-weight:600}
.heliot-ampel-satz{font-size:.9rem;opacity:.85}
.heliot-orb{display:inline-block;width:.8rem;height:.8rem;border-radius:50%;margin-right:.5rem;
  vertical-align:middle;background:#9aa4b2;box-shadow:0 0 0 2px rgba(0,0,0,.08)}
.heliot-ampel-gruen .heliot-orb{background:#1faa59}
.heliot-ampel-gelb .heliot-orb{background:#e6b800}
.heliot-ampel-rot .heliot-orb{background:#e53935}
"""

# ---------------------------------------------------------------------------
# Toene (Web Audio im Browser)
# ---------------------------------------------------------------------------

KLANG_JS = r"""export default function (component) {
  const d = component.data || {};
  const w = window;
  if (!w.__heliotKlang) {
    const K = { ctx: null, gespielt: new Set() };
    K.wecken = function () {
      try {
        if (!K.ctx) {
          const AC = w.AudioContext || w.webkitAudioContext;
          if (AC) { K.ctx = new AC(); }
        }
        if (K.ctx && K.ctx.state === "suspended") { K.ctx.resume(); }
      } catch (e) { /* ohne Ton weiter */ }
    };
    ["pointerdown", "keydown", "touchend"].forEach(function (typ) {
      document.addEventListener(typ, K.wecken, { capture: true, passive: true });
    });
    function ton(ctx, ziel, o) {
      const t0 = ctx.currentTime + (o.start || 0);
      const osz = ctx.createOscillator();
      const g = ctx.createGain();
      osz.type = o.typ || "sine";
      osz.frequency.setValueAtTime(o.f, t0);
      if (o.f2) { osz.frequency.exponentialRampToValueAtTime(o.f2, t0 + (o.gleiten || o.dauer)); }
      if (o.verstimmen) { osz.detune.setValueAtTime(o.verstimmen, t0); }
      const a = o.a || 0.005;
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(o.laut || 0.3, t0 + a);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + o.dauer);
      osz.connect(g);
      g.connect(o.filter || ziel);
      osz.start(t0);
      osz.stop(t0 + o.dauer + 0.05);
    }
    function echo(ctx, ziel, zeit, rueck) {
      const eingang = ctx.createGain();
      const verz = ctx.createDelay(1.0);
      const fb = ctx.createGain();
      verz.delayTime.value = zeit;
      fb.gain.value = rueck;
      eingang.connect(ziel);
      eingang.connect(verz);
      verz.connect(fb);
      fb.connect(verz);
      verz.connect(ziel);
      return eingang;
    }
    function rauschen(ctx, dauer) {
      const n = Math.floor(ctx.sampleRate * dauer);
      const buf = ctx.createBuffer(1, n, ctx.sampleRate);
      const k = buf.getChannelData(0);
      for (let i = 0; i < n; i++) { k[i] = Math.random() * 2 - 1; }
      const q = ctx.createBufferSource();
      q.buffer = buf;
      return q;
    }
    const KLAENGE = {
      kristall: function (ctx, z) {
        [[1318.5, 0], [1975.5, 0.12]].forEach(function (p) {
          [[1, 0.28, 1.1], [2.76, 0.10, 0.6], [5.4, 0.04, 0.35]].forEach(function (t) {
            ton(ctx, z, { f: p[0] * t[0], start: p[1], dauer: t[2], laut: t[1] });
          });
        });
      },
      nova: function (ctx, z) {
        const e = echo(ctx, z, 0.14, 0.32);
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass";
        lp.frequency.setValueAtTime(1200, ctx.currentTime);
        lp.frequency.exponentialRampToValueAtTime(5200, ctx.currentTime + 0.4);
        lp.connect(e);
        [[523.25, 0], [783.99, 0.08], [1046.5, 0.16]].forEach(function (p) {
          ton(ctx, e, { typ: "sawtooth", f: p[0], start: p[1], dauer: 0.28, laut: 0.12, filter: lp });
        });
      },
      sonar: function (ctx, z) {
        const e = echo(ctx, z, 0.28, 0.38);
        ton(ctx, e, { f: 1046.5, f2: 880, gleiten: 0.9, dauer: 1.2, a: 0.01, laut: 0.28 });
      },
      pixel: function (ctx, z) {
        ton(ctx, z, { typ: "square", f: 987.77, dauer: 0.08, laut: 0.10 });
        ton(ctx, z, { typ: "square", f: 1318.5, start: 0.08, dauer: 0.38, laut: 0.10 });
      },
      aurora: function (ctx, z) {
        [440, 554.37, 659.25, 987.77].forEach(function (f, i) {
          ton(ctx, z, { typ: "triangle", f: f, a: 0.15, dauer: 1.3, laut: 0.09, verstimmen: (i % 2 ? 6 : -6) });
        });
      },
      tropfen: function (ctx, z) {
        ton(ctx, z, { f: 1400, f2: 480, gleiten: 0.09, dauer: 0.22, laut: 0.3 });
        ton(ctx, z, { f: 1900, f2: 700, gleiten: 0.08, start: 0.17, dauer: 0.2, laut: 0.22 });
      },
      warp: function (ctx, z) {
        const q = rauschen(ctx, 0.6);
        const bp = ctx.createBiquadFilter();
        bp.type = "bandpass";
        bp.Q.value = 4;
        bp.frequency.setValueAtTime(300, ctx.currentTime);
        bp.frequency.exponentialRampToValueAtTime(3500, ctx.currentTime + 0.5);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, ctx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.16, ctx.currentTime + 0.35);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.6);
        q.connect(bp);
        bp.connect(g);
        g.connect(z);
        q.start();
        ton(ctx, z, { f: 1200, f2: 2400, gleiten: 0.2, start: 0.45, dauer: 0.45, laut: 0.18 });
      },
      // Der feste, tiefe Fehlerton (Frage 5): zwei absteigende, dunkle Toene.
      // Nicht waehlbar; er spielt bei jeder Fehlermeldung.
      fehler: function (ctx, z) {
        ton(ctx, z, { typ: "triangle", f: 311.13, f2: 293.66, gleiten: 0.2, dauer: 0.26, a: 0.01, laut: 0.3 });
        ton(ctx, z, { typ: "triangle", f: 233.08, f2: 220, gleiten: 0.3, start: 0.24, dauer: 0.42, a: 0.01, laut: 0.3 });
      }
    };
    // Gleich laut: Faktoren aus der stummen Vorberechnung vom 23.09.2026,
    // Ziel ein Effektivwert von 0,06 ueber die hoerbare Dauer jedes Tons. Der
    // Fehlerton ist am 25.09.2026 genauso vorberechnet (1,18, mit dem Abgleich
    // an Tropfen 1,11 statt 1,09 auf 1,16 gesetzt).
    const PEGEL = { kristall: 0.68, nova: 2.66, sonar: 0.93, pixel: 2.13, aurora: 1.74, tropfen: 1.09, warp: 1.93,
                    fehler: 1.16 };
    K.spiele = function (name) {
      const f = KLAENGE[name];
      if (!f) { return; }
      K.wecken();
      if (!K.ctx) { return; }
      const master = K.ctx.createGain();
      master.gain.value = 0.9 * (PEGEL[name] || 1);
      master.connect(K.ctx.destination);
      try { f(K.ctx, master); } catch (e) { /* ohne Ton weiter */ }
    };
    K.klaenge = KLAENGE;   // fuer die Messung der Toene (stumm vorberechnet)
    K.pegel = PEGEL;
    w.__heliotKlang = K;
  }
  const K = w.__heliotKlang;
  if (d.id && d.klang && d.klang !== "aus" && !K.gespielt.has(d.id)) {
    K.gespielt.add(d.id);
    K.spiele(d.klang);
  }
}
"""

# ---------------------------------------------------------------------------
# Design Zukunft
# ---------------------------------------------------------------------------

DESIGN_ZUKUNFT = r"""
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Space+Grotesk:wght@400;500;700&display=swap');
:root{--hz-cyan:#00e5ff;--hz-violett:#8a6bff;--hz-magenta:#ff4fd8;--hz-text:#e3edff;--hz-leise:#9fb7d9;
  --hz-glas:rgba(12,18,44,.62);--hz-rand:rgba(120,210,255,.22)}
html,body,.stApp{background:#04050d !important}
.stApp{color:var(--hz-text);font-family:'Space Grotesk',system-ui,sans-serif;
  background:
    radial-gradient(1100px 800px at 8% -10%,rgba(0,229,255,.20),transparent 60%),
    radial-gradient(900px 700px at 105% 5%,rgba(138,107,255,.24),transparent 62%),
    radial-gradient(1000px 900px at 50% 118%,rgba(255,79,216,.16),transparent 60%),
    linear-gradient(160deg,#04050d 0%,#0a1030 48%,#0c0624 100%) !important;
  background-attachment:fixed !important}
.stApp::before{content:"";position:fixed;inset:-60%;pointer-events:none;z-index:0;opacity:.55;
  background-image:
    radial-gradient(1.2px 1.2px at 12% 18%,rgba(255,255,255,.9),transparent 70%),
    radial-gradient(1px 1px at 72% 34%,rgba(180,230,255,.8),transparent 70%),
    radial-gradient(1.4px 1.4px at 38% 76%,rgba(255,200,255,.7),transparent 70%),
    radial-gradient(1px 1px at 88% 82%,rgba(255,255,255,.8),transparent 70%),
    radial-gradient(1px 1px at 55% 8%,rgba(160,255,255,.7),transparent 70%),
    radial-gradient(1.3px 1.3px at 26% 52%,rgba(255,255,255,.6),transparent 70%);
  background-size:340px 340px;animation:hz-sterne 160s linear infinite}
.stApp::after{content:"";position:fixed;left:-20%;right:-20%;top:-30%;height:80%;pointer-events:none;z-index:0;
  background:conic-gradient(from 200deg at 50% 50%,transparent,rgba(0,229,255,.16),rgba(138,107,255,.14),
    rgba(255,79,216,.12),transparent 70%);
  filter:blur(90px);animation:hz-aurora 26s ease-in-out infinite alternate}
@keyframes hz-sterne{from{transform:translate3d(0,0,0)}to{transform:translate3d(-340px,-340px,0)}}
@keyframes hz-aurora{0%{transform:translateX(-6%) rotate(-4deg);opacity:.75}
  50%{transform:translateX(5%) rotate(3deg);opacity:1}100%{transform:translateX(-2%) rotate(6deg);opacity:.8}}
[data-testid="stHeader"]{background:transparent !important}
[data-testid="stMainBlockContainer"]{position:relative;z-index:1;background:var(--hz-glas);
  border:1px solid var(--hz-rand);border-radius:26px;margin-top:2.2rem;margin-bottom:2rem;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.03),0 30px 90px rgba(0,0,0,.55),0 0 70px rgba(0,229,255,.08);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);overflow:hidden}
[data-testid="stMainBlockContainer"]::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(180deg,transparent 0%,rgba(0,229,255,.07) 50%,transparent 100%);
  background-size:100% 260px;background-repeat:no-repeat;animation:hz-scan 9s linear infinite}
@keyframes hz-scan{from{background-position:0 -260px}to{background-position:0 calc(100% + 260px)}}
[data-testid="stMainBlockContainer"] h1{font-family:'Orbitron','Space Grotesk',sans-serif;letter-spacing:.07em;
  font-weight:700;background:linear-gradient(90deg,var(--hz-cyan),var(--hz-violett),var(--hz-magenta),var(--hz-cyan));
  background-size:300% 100%;-webkit-background-clip:text;background-clip:text;color:transparent !important;
  animation:hz-schimmer 9s linear infinite;filter:drop-shadow(0 0 18px rgba(0,229,255,.25))}
@keyframes hz-schimmer{from{background-position:0% 50%}to{background-position:300% 50%}}
[data-testid="stMainBlockContainer"] h2,[data-testid="stMainBlockContainer"] h3,
[data-testid="stMainBlockContainer"] h4,[data-testid="stMainBlockContainer"] h5,
[data-testid="stMainBlockContainer"] h6{font-family:'Space Grotesk',sans-serif;color:#c9ecff !important;
  letter-spacing:.02em;text-shadow:0 0 16px rgba(0,229,255,.28)}
[data-testid="stMainBlockContainer"] h3::after,[data-testid="stMainBlockContainer"] h4::after{content:"";display:block;
  height:2px;margin-top:.35rem;width:3.2rem;border-radius:2px;
  background:linear-gradient(90deg,var(--hz-cyan),var(--hz-magenta));box-shadow:0 0 10px rgba(0,229,255,.6);
  animation:hz-linie 4s ease-in-out infinite}
@keyframes hz-linie{0%,100%{width:3.2rem}50%{width:6.5rem}}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li,
[data-testid="stText"],[data-testid="stWidgetLabel"] p,[data-testid="stWidgetLabel"] label,
[data-testid="stCheckbox"] label p,[data-testid="stRadio"] label p{color:var(--hz-text) !important}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:var(--hz-leise) !important}
[data-testid="stMarkdownContainer"] a{color:var(--hz-cyan) !important;text-shadow:0 0 8px rgba(0,229,255,.4)}
[data-testid="stMarkdownContainer"] strong{color:#ffffff}
hr{border-color:rgba(120,210,255,.18) !important}
[role="tablist"]{gap:.4rem;background:rgba(255,255,255,.035);padding:.35rem;border-radius:999px;
  border:1px solid var(--hz-rand);flex-wrap:wrap}
[data-testid="stTab"]{border-radius:999px !important;padding:.35rem 1rem !important;color:var(--hz-leise) !important;
  background:transparent !important;transition:all .3s ease}
[data-testid="stTab"] p{color:inherit !important}
[data-testid="stTab"]:hover{color:#ffffff !important;background:rgba(0,229,255,.08) !important}
[data-testid="stTab"][aria-selected="true"]{color:#ffffff !important;
  background:linear-gradient(135deg,rgba(0,229,255,.28),rgba(138,107,255,.30)) !important;
  box-shadow:0 0 22px rgba(0,229,255,.35),inset 0 0 0 1px rgba(255,255,255,.12)}
[role="tablist"] .react-aria-SelectionIndicator,[data-testid="stTab"] .react-aria-SelectionIndicator{display:none !important}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{
  background:linear-gradient(135deg,rgba(0,229,255,.12),rgba(138,107,255,.14)) !important;color:#eaf8ff !important;
  border:1px solid rgba(0,229,255,.45) !important;border-radius:999px !important;transition:all .25s ease}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stFormSubmitButton"]>button:hover{
  box-shadow:0 0 24px rgba(0,229,255,.45) !important;border-color:var(--hz-cyan) !important;transform:translateY(-1px)}
.stButton>button p,.stDownloadButton>button p{color:inherit !important}
button[data-testid="stBaseButton-primary"],button[kind="primary"]{
  background:linear-gradient(120deg,#00c6ff,#7b5cff 55%,#ff3fd0) !important;background-size:200% 100% !important;
  border:none !important;color:#ffffff !important;animation:hz-puls 3.4s ease-in-out infinite,hz-verlauf 6s linear infinite}
@keyframes hz-puls{0%,100%{box-shadow:0 0 12px rgba(0,198,255,.35)}50%{box-shadow:0 0 30px rgba(255,63,208,.55)}}
@keyframes hz-verlauf{from{background-position:0% 50%}to{background-position:200% 50%}}
button[data-testid="stBaseButton-tertiary"],button[kind="tertiary"]{background:transparent !important;border:none !important;
  color:#7fdcff !important;box-shadow:none !important;padding-left:0 !important}
button[data-testid="stBaseButton-tertiary"]:hover{color:#ffffff !important;text-shadow:0 0 10px rgba(0,229,255,.8)}
[data-testid="stTextInputRootElement"],[data-testid="stSelectbox"] [role="group"],
[data-testid="stMultiSelect"] [role="group"],[data-testid="stNumberInputContainer"],[data-testid="stTextArea"] textarea{
  background:rgba(6,12,32,.85) !important;border-color:rgba(0,229,255,.35) !important;border-radius:12px !important}
[data-testid="stTextInputField"],[data-testid="stSelectbox"] input,[data-testid="stMultiSelect"] input,
[data-testid="stNumberInputContainer"] input,[data-testid="stTextArea"] textarea{color:#eaf8ff !important;
  background:transparent !important}
[data-testid="stTextInputRootElement"]:focus-within,[data-testid="stSelectbox"] [role="group"]:focus-within{
  box-shadow:0 0 0 2px rgba(0,229,255,.45) !important}
input::placeholder,textarea::placeholder{color:rgba(159,183,217,.7) !important}
[role="listbox"]{background:#0b1230 !important;border:1px solid var(--hz-rand) !important}
[role="option"]{color:#eaf8ff !important}
[role="option"]:hover,[role="option"][data-focused]{background:rgba(0,229,255,.15) !important}
[data-testid="stCheckbox"] label>span+div,[data-testid="stRadio"] label>span+div{background:rgba(6,12,32,.85) !important;
  border-color:var(--hz-cyan) !important;box-shadow:0 0 8px rgba(0,229,255,.35)}
[data-testid="stCheckbox"] label[data-selected="true"]>span+div,[data-testid="stRadio"] label[data-selected="true"]>span+div{
  background:linear-gradient(135deg,#00c6ff,#7b5cff) !important;border-color:transparent !important}
[data-testid="stAlertContainer"]{background:rgba(10,20,48,.72) !important;border:1px solid var(--hz-rand) !important;
  border-radius:16px !important;backdrop-filter:blur(8px);animation:hz-einblenden .5s ease both}
[data-testid="stAlertContainer"] p{color:var(--hz-text) !important}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]){border-color:rgba(0,255,170,.55) !important;
  box-shadow:0 0 22px rgba(0,255,170,.18)}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]){border-color:rgba(255,80,120,.6) !important;
  box-shadow:0 0 22px rgba(255,80,120,.2)}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]){border-color:rgba(255,200,60,.55) !important}
@keyframes hz-einblenden{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
[data-testid="stFileUploaderDropzone"]{background:rgba(6,12,32,.7) !important;border:1px dashed rgba(0,229,255,.5) !important;
  border-radius:16px !important}
[data-testid="stFileUploaderDropzone"] *{color:var(--hz-text) !important}
[data-testid="stCode"] pre,code{background:rgba(6,12,32,.85) !important;color:#9ff3ff !important}
[data-testid="stPlotlyChart"]{border-radius:18px;overflow:hidden;box-shadow:0 0 30px rgba(0,229,255,.12)}
.heliot-ampel-gruen{--hz-ampel:#20f0a0}.heliot-ampel-gelb{--hz-ampel:#ffd23f}.heliot-ampel-rot{--hz-ampel:#ff4d6d}
.heliot-ampel-grau{--hz-ampel:#8aa0c0}
.heliot-ampel{position:relative;padding:.7rem 1rem .7rem 1rem;margin:.2rem 0 .8rem 0;border-radius:18px;
  background:rgba(8,14,36,.7);border:1px solid var(--hz-ampel,#8aa0c0);overflow:hidden;
  animation:hz-rand 3.6s ease-in-out infinite}
@keyframes hz-rand{0%,100%{box-shadow:0 0 12px -6px var(--hz-ampel,#8aa0c0),inset 0 0 18px -12px var(--hz-ampel,#8aa0c0)}
  50%{box-shadow:0 0 30px -4px var(--hz-ampel,#8aa0c0),inset 0 0 26px -10px var(--hz-ampel,#8aa0c0)}}
.heliot-ampel::after{content:"";position:absolute;top:0;bottom:0;left:-45%;width:40%;pointer-events:none;
  background:linear-gradient(100deg,transparent,rgba(255,255,255,.10),transparent);animation:hz-glanz 7s ease-in-out infinite}
@keyframes hz-glanz{0%{left:-45%}55%,100%{left:125%}}
.heliot-ampel p{color:var(--hz-text) !important}
.heliot-ampel-kopf{font-family:'Orbitron','Space Grotesk',sans-serif;letter-spacing:.05em}
.heliot-orb{width:1rem !important;height:1rem !important;background:var(--hz-ampel,#8aa0c0) !important;
  box-shadow:0 0 10px var(--hz-ampel,#8aa0c0),0 0 26px var(--hz-ampel,#8aa0c0) !important;
  animation:hz-orb 2.6s ease-in-out infinite}
@keyframes hz-orb{0%,100%{transform:scale(1);filter:brightness(1)}50%{transform:scale(1.25);filter:brightness(1.4)}}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-track{background:#070b1d}
::-webkit-scrollbar-thumb{background:linear-gradient(180deg,var(--hz-cyan),var(--hz-violett));border-radius:10px}
@media (prefers-reduced-motion: reduce){
  .stApp::before,.stApp::after,[data-testid="stMainBlockContainer"]::before,.heliot-ampel,.heliot-ampel::after,.heliot-orb,
  [data-testid="stMainBlockContainer"] h1,[data-testid="stMainBlockContainer"] h3::after,
  [data-testid="stMainBlockContainer"] h4::after,button,[data-testid="stAlertContainer"]{animation:none !important;
  transition:none !important}}
"""

# ---------------------------------------------------------------------------
# Erklaerungen der Scanner-Kriterien ohne eigenen Erklaertext
# ---------------------------------------------------------------------------

SCANNER_ERKLAERUNGEN = {
    "strategie": "Wählt ein Muster oder ein Chart-Signal, das jede Aktie erfüllen muss; ohne Wahl filtern nur die "
                 "Einstellungen in Teil 2. Ein Chart-Signal filtert genauso wie das gleichnamige Merkmal in Teil 2.",
    "toleranz": "Streng heißt, jede Regel des Musters ist erfüllt. Mit Toleranz dürfen Schwellen in Prozent, "
                "Verhältnisse und Dauern knapp verfehlt werden; ein solcher Treffer bekommt weniger Punkte beim "
                "Rating.",
    "handelbar": "Lässt Aktien weg, die zu billig sind, zu wenig gehandelt werden oder zu kurz an der Börse sind. "
                 "Gemessen wird der durchschnittliche Tagesumsatz über 50 Tage, derselbe Wert wie das Merkmal in "
                 "Teil 2.",
    "langweilig": "Nur bei der Darvas Box: lässt Boxen von Aktien weg, die sich kaum bewegen. Übrig bleiben Boxen "
                  "mit genug Schwung für einen Ausbruch.",
    "rs_vorlaeufig": "Aktien mit weniger als einem Jahr Kurshistorie haben nur ein vorläufiges RS aus den "
                     "vorhandenen Quartalen. Angehakt zählen sie trotzdem mit.",
    "termine": "Zeigt nur Aktien, die an den angehakten Zeitpunkten Quartalszahlen bringen. Die Zeitpunkte stehen "
               "darunter.",
    "termine_heute_vor": "Zahlen heute vor Handelsbeginn in New York.",
    "termine_heute_nach": "Zahlen heute nach Handelsschluss in New York.",
    "termine_morgen_vor": "Zahlen am nächsten Handelstag vor Handelsbeginn.",
    "termine_morgen_nach": "Zahlen am nächsten Handelstag nach Handelsschluss.",
    "termine_ohne_zeit": "Nimmt auch Aktien mit, die ihre Zahlen während des Handels bringen oder deren Tageszeit "
                         "nicht bekannt ist.",
    "termine_umfang": "Ganzer Markt heißt alle Stammaktien des US-Markts; sonst nur die Aktien der zwei "
                      "Wochenlisten.",
}

SEKTOR_ERKLAERUNGEN = {
    "Basic Materials": "Chemie, Metalle, Bergbau, Papier und Baustoffe.",
    "Consumer Discretionary": "Waren und Dienste, auf die Haushalte in schlechten Zeiten eher verzichten, etwa "
                              "Autos, Handel, Freizeit und Reisen.",
    "Consumer Staples": "Güter des täglichen Bedarfs wie Lebensmittel, Getränke und Körperpflege.",
    "Energy": "Öl, Gas, Kohle und die dazugehörigen Dienste.",
    "Finance": "Banken, Versicherungen, Vermögensverwalter, Börsen und Finanzdienste.",
    "Health Care": "Pharma, Biotechnologie, Medizintechnik und Gesundheitsdienste.",
    "Industrials": "Maschinenbau, Luftfahrt und Rüstung, Transport, Bau und Dienste für die Industrie.",
    "Miscellaneous": "Unternehmen, die die Einteilung der Nasdaq keinem der übrigen Sektoren zuordnet.",
    "Real Estate": "Immobiliengesellschaften und Immobilienfonds.",
    "Technology": "Software, Halbleiter, Computer, Internet und elektronische Geräte.",
    "Telecommunications": "Telefon-, Kabel- und Funknetzbetreiber.",
    "Utilities": "Strom, Gas und Wasser.",
    "": "Aktien, zu denen die Daten keinen Sektor nennen.",
}


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest() -> int:
    fehler = []

    def p(text, ok, info=""):
        print(("  OK    " if ok else "  FEHLER ") + text + (f" ({info})" if info and not ok else ""))
        if not ok:
            fehler.append(text)

    print("oberflaeche.py, Selbsttest")
    ny = lambda s: datetime.fromisoformat(s)  # noqa: E731
    p("Dienstag 20:00: nur der Dienstag", ampel_tage(ny("2026-09-22T20:00")) == (date(2026, 9, 22), date(2026, 9, 22)))
    p("Dienstag 17:00: Montag oder Dienstag", ampel_tage(ny("2026-09-22T17:00")) == (date(2026, 9, 21), date(2026, 9, 22)))
    p("Dienstag 12:00: nur der Montag", ampel_tage(ny("2026-09-22T12:00")) == (date(2026, 9, 21), date(2026, 9, 21)))
    p("Montag 09:00: nur der Freitag", ampel_tage(ny("2026-09-21T09:00")) == (date(2026, 9, 18), date(2026, 9, 18)))
    p("Samstag: nur der Freitag", ampel_tage(ny("2026-09-26T21:00")) == (date(2026, 9, 25), date(2026, 9, 25)))
    daten = {"farbe": "gruen", "handelstag": "2026-09-22",
             "indizes": {"S&P 500": {"ueber_ema21": True, "ueber_sma50": True, "ema21_ueber_sma50": True,
                                     "sma50_steigt": True},
                         "Nasdaq": {"ueber_ema21": False, "ueber_sma50": True, "ema21_ueber_sma50": True,
                                    "sma50_steigt": False}}}
    import marktampel
    f, k, s = ampel_saetze(daten, ny("2026-09-23T10:00"))
    p("Ampel vom richtigen Tag: Farbe, Datum und oben ein einfacher Satz (Antwort 29)",
      f == "gruen" and k == "Marktampel grün, Schluss vom 22.09.2026: S&P 500 und Nasdaq stehen beide im "
                             "Aufwärtstrend.", k)
    p("Ampel: darunter die Einzelheiten beider Indizes und der Satz zur IBD-Zählung (Antwort 30)",
      s == "Einzelheiten: S&P 500 über EMA 21 und SMA 50, SMA 50 steigt; Nasdaq unter EMA 21, über SMA 50, SMA 50 "
           "steigt nicht. " + marktampel.REGEL_SATZ, s)
    f, k, s = ampel_saetze(daten, ny("2026-09-23T20:00"), nachtscan_tag="2026-09-22")
    p("Maßstab ist der Tag, den der Nachtscan gerechnet hat (Antwort 10)", f == "gruen", k)
    f, k, s = ampel_saetze(daten, ny("2026-09-23T10:00"), nachtscan_tag="2026-09-23")
    p("Hat der Nachtscan schon weitergerechnet, steht keine Farbe da",
      f is None and "der Nachtscan hat schon den Schluss vom 23.09.2026 gerechnet" in k, k)
    feiertag = {**daten, "handelstag": "2026-09-04"}
    f, k, s = ampel_saetze(feiertag, ny("2026-09-08T10:00"), nachtscan_tag="2026-09-04")
    p("Nach einem US-Feiertag bleibt die Ampel stehen", f == "gruen", k)
    f, k, s = ampel_saetze(daten, ny("2026-09-23T17:00"))
    p("Nach Handelsschluss gilt der Vortag noch", f == "gruen")
    f, k, s = ampel_saetze(daten, ny("2026-09-23T20:00"))
    p("Ampel vom falschen Tag: keine Farbe", f is None and k.endswith("gilt dem Schluss vom 22.09.2026.") and not s, k)
    f, k, s = ampel_saetze(None, ny("2026-09-23T20:00"))
    p("Ohne Ampel: nicht verfügbar", f is None and k.startswith("Marktampel nicht verfügbar"))
    h = ampel_html("gruen", "Marktampel grün <x>", "a & b")
    p("HTML: Punkt verborgen, Text maskiert", 'aria-hidden="true"' in h and "&lt;x&gt;" in h and "a &amp; b" in h)
    verboten = ("–", "—", "|")
    texte = list(SCANNER_ERKLAERUNGEN.values()) + list(SEKTOR_ERKLAERUNGEN.values())
    p("Erklärungen ohne Gedankenstrich und senkrechten Strich", not any(z in t for t in texte for z in verboten))
    p("Erklärungen kurz, höchstens 220 Zeichen", all(0 < len(t) <= 220 for t in texte))
    try:
        import scanner_ansicht as sa
        p("Jeder Sektor des Scanners hat eine Erklärung",
          all(s in SEKTOR_ERKLAERUNGEN for s in list(sa.SEKTOREN) + [""]),
          ", ".join(s for s in sa.SEKTOREN if s not in SEKTOR_ERKLAERUNGEN))
        p("Jeder Zahlentermin hat eine Erklärung",
          all(f"termine_{k}" in SCANNER_ERKLAERUNGEN for k, *_ in sa.TERMIN_TEILE))
    except Exception as ex:  # noqa: BLE001
        p("scanner_ansicht ladbar", False, f"{type(ex).__name__}: {ex}")
    import einstellungen as es
    p("Jeder Ton hat einen Klang im Browser", all(k == "aus" or f"      {k}: function" in KLANG_JS
                                                    for k, _n, _b in es.KLAENGE))
    p("Das Augensymbol heißt Passwort zeigen oder Passwort verbergen und steht sicher im Skript (Antwort 28)",
      "Passwort zeigen" in PASSWORT_AUGE_JS and "Passwort verbergen" in PASSWORT_AUGE_JS
      and "<" not in PASSWORT_AUGE_JS and 'aria-hidden", "true"' in PASSWORT_AUGE_JS
      and "window.__heliotPwWache" in PASSWORT_AUGE_JS)
    p("Der feste Fehlerton ist im Browser gebaut (Antwort 5)", "      fehler: function" in KLANG_JS
      and "fehler:" in KLANG_JS.split("PEGEL")[1])
    p("Das Design bewegt sich nicht, wenn weniger Bewegung verlangt ist", "prefers-reduced-motion" in DESIGN_ZUKUNFT)
    p("Kein Kleiner-Zeichen im CSS, sonst verwirft Streamlit den ganzen Stilblock",
      "<" not in DESIGN_ZUKUNFT and "<" not in AMPEL_CSS)
    p("Das Design erzeugt keinen Text, jeder content ist leer",
      all(x.startswith('""') for x in DESIGN_ZUKUNFT.split("content:")[1:]))
    print(f"ERGEBNIS: {len(fehler)} FEHLGESCHLAGEN" if fehler else "ERGEBNIS: alles bestanden")
    return 1 if fehler else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Oberflaeche: Ampel, Toene, Design, Erklaerungen")
    ap.add_argument("--selbsttest", action="store_true")
    a = ap.parse_args()
    if a.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
