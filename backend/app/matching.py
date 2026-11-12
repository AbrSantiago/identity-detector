"""Correlación de identidades: el "cerebro" del detector.

Idea central (criterio de los estudios de la EFF, Panopticlick/Cover Your
Tracks): cada característica compartida aporta bits de información igual a
`-log2(frecuencia del valor)`. Una zona horaria que todos comparten aporta
~0 bits; un renderer de GPU raro aporta muchos. El que suma más bits de
evidencia es, con más probabilidad, la misma persona.

Problemas que resuelve este módulo:

1. **Población chica.** Con 3 usuarios la frecuencia observada es ruido puro.
   Combinamos dos cosas:
     - Suavizado de Laplace sobre la frecuencia observada, con la cardinalidad
       de cada atributo atada a sus bits a priori (K = 2^prior_bits). Así el
       prior y el suavizado son coherentes: un valor raro tiende a `prior_bits`,
       uno común aporta menos.
     - Una mezcla con la tabla de pesos a priori, ponderada por el tamaño de la
       población: `w = N / (N + N0)`. Con N chico mandan los priors; con N
       grande manda lo observado. Resultado: funciona con 3 y con 300.

2. **Comparaciones tolerantes.** El User-Agent se compara ignorando la versión
   menor; las fuentes por solapamiento de Jaccard; la IP con crédito parcial si
   coincide la /24 (o /64).

3. **Dos niveles.** Puntaje de *navegador* (canvas, audio, UA...) y de
   *dispositivo* (GPU, pantalla, fuentes, zona horaria, IP...). El nivel
   dispositivo reconoce a la misma persona aunque use Chrome en el chat y
   Firefox en el detector.

El puntaje de un nivel = bits coincidentes / bits comparables (0..1). El titular
es `max(navegador, dispositivo)`: alcanza con que uno de los dos sea alto.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .models import (
    Candidate,
    Fingerprint,
    Identity,
    MatchResult,
    NetworkInfo,
    ScoreBreakdownRow,
)

# --- Parámetros del algoritmo (configurables) --------------------------------

# Suavizado de Laplace.
ALPHA = 1.0
# Peso de la población en la mezcla observado/prior: w = N / (N + N0).
PRIOR_N0 = 6.0
# Tope: lo observado puede superar al prior a lo sumo este factor (valores
# ultra-raros en poblaciones chicas no deben disparar bits absurdos).
BITS_CAP = 1.5

# Tabla de pesos a priori por atributo (bits de entropía "típicos"). Es la
# distintividad esperada de cada dato cuando todavía no hay población para
# medirla. Editable: subir un valor = darle más peso a ese atributo.
PRIOR_BITS: dict[str, float] = {
    # Navegador
    "canvas": 11.0,
    "audio": 7.0,
    "user_agent": 8.0,
    "plugins": 3.0,
    "voices": 5.0,
    "do_not_track": 1.0,
    # Dispositivo
    "webgl_renderer": 9.0,
    "webgl_vendor": 3.0,
    "fonts": 8.0,
    "screen": 5.0,
    "cores": 2.0,
    "memory": 1.5,
    "touch": 1.0,
    "timezone": 3.0,
    "languages": 2.5,
    "platform": 2.0,
    "media_queries": 1.5,
    "ip": 7.0,
    "webrtc_public": 7.0,
}


# --- Comparadores tolerantes -------------------------------------------------

def _jaccard(a: Any, b: Any) -> float:
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


_UA_RE = re.compile(
    r"(Firefox|Edg|OPR|Chrome|Safari)/(\d+)", re.IGNORECASE
)


def parse_ua(ua: Optional[str]) -> Optional[tuple[str, int]]:
    """Reduce un User-Agent a (familia, versión mayor). Ignora la versión menor.

    Preferimos marcas específicas (Edge/Opera/Firefox) sobre Chrome/Safari, que
    aparecen en el UA de casi todos por compatibilidad.
    """
    if not ua:
        return None
    found: dict[str, int] = {}
    for m in _UA_RE.finditer(ua):
        fam = m.group(1).lower()
        found[fam] = int(m.group(2))
    for fam in ("edg", "opr", "firefox", "chrome", "safari"):
        if fam in found:
            canonical = {"edg": "edge", "opr": "opera"}.get(fam, fam)
            return (canonical, found[fam])
    return None


def _cmp_ua(a: tuple[str, int], b: tuple[str, int]) -> float:
    if a[0] != b[0]:
        return 0.0
    return 1.0 if a[1] == b[1] else 0.5  # misma familia, versión mayor distinta


def _cmp_ip(a: tuple[Optional[str], Optional[str]], b: tuple[Optional[str], Optional[str]]) -> float:
    """IP exacta = 1.0; solo coincide la red (/24 o /64) = 0.6; nada = 0."""
    ip_a, net_a = a
    ip_b, net_b = b
    if ip_a and ip_b and ip_a == ip_b:
        return 1.0
    if net_a and net_b and net_a == net_b:
        return 0.6
    return 0.0


def _cmp_media(a: dict, b: dict) -> float:
    a = a or {}
    b = b or {}
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    same = sum(1 for k in keys if a.get(k) == b.get(k))
    return same / len(keys)


# --- Especificación de atributos ---------------------------------------------

@dataclass
class AttributeSpec:
    name: str
    level: str  # "browser" o "device"
    extract: Callable[[Fingerprint, NetworkInfo], Any]
    compare: Callable[[Any, Any], float]
    set_valued: bool = False  # si True, usa prior * Jaccard (sin frecuencia observada)
    freq_key: Callable[[Any], Any] = repr  # clave para contar frecuencia

    @property
    def prior_bits(self) -> float:
        return PRIOR_BITS.get(self.name, 2.0)


def _screen(fp: Fingerprint, _net: NetworkInfo):
    if fp.screen_width is None or fp.screen_height is None:
        return None
    return (fp.screen_width, fp.screen_height, fp.device_pixel_ratio, fp.color_depth)


SPECS: list[AttributeSpec] = [
    # --- Navegador ---
    AttributeSpec("canvas", "browser", lambda fp, n: fp.canvas_hash, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("audio", "browser", lambda fp, n: fp.audio_hash, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("user_agent", "browser", lambda fp, n: parse_ua(n.user_agent), _cmp_ua),
    AttributeSpec("plugins", "browser", lambda fp, n: fp.plugins, _jaccard, set_valued=True),
    AttributeSpec("voices", "browser", lambda fp, n: fp.voices, _jaccard, set_valued=True),
    AttributeSpec("do_not_track", "browser", lambda fp, n: fp.do_not_track, lambda a, b: 1.0 if a == b else 0.0),
    # --- Dispositivo ---
    AttributeSpec("webgl_renderer", "device", lambda fp, n: fp.webgl_renderer, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("webgl_vendor", "device", lambda fp, n: fp.webgl_vendor, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("fonts", "device", lambda fp, n: fp.fonts, _jaccard, set_valued=True),
    AttributeSpec("screen", "device", _screen, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("cores", "device", lambda fp, n: fp.hardware_concurrency, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("memory", "device", lambda fp, n: fp.device_memory, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("touch", "device", lambda fp, n: fp.touch_support, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("timezone", "device", lambda fp, n: fp.timezone, lambda a, b: 1.0 if a == b else 0.0),
    AttributeSpec("languages", "device", lambda fp, n: fp.languages, _jaccard, set_valued=True),
    AttributeSpec(
        "platform", "device",
        lambda fp, n: (fp.ua_data or {}).get("platform") if fp.ua_data else n.sec_ch_ua_platform,
        lambda a, b: 1.0 if a == b else 0.0,
    ),
    AttributeSpec("media_queries", "device", lambda fp, n: fp.media_queries, _cmp_media),
    AttributeSpec(
        "ip", "device",
        lambda fp, n: (n.ip, n.ip_network),
        _cmp_ip,
        freq_key=lambda v: v[1],  # contamos por red /24-/64
    ),
    AttributeSpec("webrtc_public", "device", lambda fp, n: fp.webrtc_public_ips, _jaccard, set_valued=True),
]


# --- Frecuencias de la población ---------------------------------------------

def _population_counts(identities: list[Identity]) -> dict[str, Counter]:
    """Para cada atributo escalar, cuenta cuántas identidades tienen cada valor."""
    counts: dict[str, Counter] = {s.name: Counter() for s in SPECS if not s.set_valued}
    for ident in identities:
        for spec in SPECS:
            if spec.set_valued:
                continue
            val = spec.extract(ident.fingerprint, ident.network)
            if val is None:
                continue
            counts[spec.name][spec.freq_key(val)] += 1
    return counts


def _effective_bits(spec: AttributeSpec, cand_value: Any, counts: dict[str, Counter], n: int) -> float:
    """Bits que vale este atributo, mezclando lo observado con el prior."""
    prior = spec.prior_bits
    if spec.set_valued or n <= 0:
        return prior
    # Cardinalidad atada al prior: K = 2^prior_bits (prior uniforme coherente).
    k = 2.0 ** prior
    c = counts[spec.name].get(spec.freq_key(cand_value), 0)
    p = (c + ALPHA) / (n + ALPHA * k)
    observed = -math.log2(p)
    observed = min(observed, prior * BITS_CAP)
    w = n / (n + PRIOR_N0)
    return w * observed + (1.0 - w) * prior


# --- Scoring de un candidato -------------------------------------------------

@dataclass
class _Scored:
    identity: Identity
    browser_score: float
    device_score: float
    matched_bits: float
    rows: list[ScoreBreakdownRow] = field(default_factory=list)

    @property
    def headline(self) -> float:
        return max(self.browser_score, self.device_score)


def _score_candidate(
    visitor_vals: dict[str, Any],
    candidate: Identity,
    counts: dict[str, Counter],
    n: int,
) -> _Scored:
    sums = {
        "browser": [0.0, 0.0],  # [matched_bits, comparable_bits]
        "device": [0.0, 0.0],
    }
    total_matched = 0.0
    rows: list[ScoreBreakdownRow] = []

    for spec in SPECS:
        v_val = visitor_vals.get(spec.name)
        c_val = spec.extract(candidate.fingerprint, candidate.network)
        if v_val is None or c_val is None:
            continue  # no comparable: no entra ni en numerador ni en denominador
        # Dos conjuntos vacíos (p. ej. sin plugins) no son evidencia de nada:
        # no los contamos ni a favor ni en contra.
        if spec.set_valued and not v_val and not c_val:
            continue
        sim = spec.compare(v_val, c_val)
        max_bits = _effective_bits(spec, c_val, counts, n)
        contributed = sim * max_bits
        sums[spec.level][0] += contributed
        sums[spec.level][1] += max_bits
        total_matched += contributed
        rows.append(
            ScoreBreakdownRow(
                attribute=spec.name,
                level=spec.level,
                matched=sim >= 0.5,
                bits=round(contributed, 2),
                detail=_describe(spec, v_val, c_val, sim),
            )
        )

    bscore = sums["browser"][0] / sums["browser"][1] if sums["browser"][1] > 0 else 0.0
    dscore = sums["device"][0] / sums["device"][1] if sums["device"][1] > 0 else 0.0
    rows.sort(key=lambda r: r.bits, reverse=True)
    return _Scored(candidate, bscore, dscore, total_matched, rows)


def _describe(spec: AttributeSpec, v_val: Any, c_val: Any, sim: float) -> str:
    if sim >= 0.999:
        return "coincide"
    if sim <= 0.001:
        return "difiere"
    if spec.name == "user_agent":
        return "misma familia, otra versión"
    if spec.name == "ip":
        return "coincide la red (/24 o /64)"
    return f"coincidencia parcial ({int(round(sim * 100))}%)"


# --- API pública -------------------------------------------------------------

def identify(
    fp: Fingerprint,
    net: NetworkInfo,
    identities: list[Identity],
    threshold: float,
    top_k: int = 3,
) -> MatchResult:
    """Correlaciona al visitante contra las identidades guardadas."""
    n = len(identities)
    counts = _population_counts(identities)
    visitor_vals = {s.name: s.extract(fp, net) for s in SPECS}

    scored = [_score_candidate(visitor_vals, ident, counts, n) for ident in identities]
    # Ordenamos por el titular (max de los dos niveles) y desempatamos por bits.
    scored.sort(key=lambda s: (s.headline, s.matched_bits), reverse=True)

    def to_candidate(s: _Scored) -> Candidate:
        return Candidate(
            nickname=s.identity.nickname,
            avatar=s.identity.avatar,
            browser_score=round(s.browser_score, 4),
            device_score=round(s.device_score, 4),
            combined_score=round(s.headline, 4),
        )

    top = [to_candidate(s) for s in scored[:top_k]]
    best = scored[0] if scored else None
    recognized = bool(best and best.headline >= threshold)

    return MatchResult(
        recognized=recognized,
        best=to_candidate(best) if (best and recognized) else None,
        top=top,
        breakdown=best.rows if best else [],
        observed_network=net,
        observed_fingerprint=fp,
        threshold=threshold,
    )
