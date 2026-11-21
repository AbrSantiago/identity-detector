"""Tests del motor de correlación (matching.py)."""
from __future__ import annotations

from app import matching
from app.matching import identify
from app.models import Fingerprint, Identity, NetworkInfo

THRESHOLD = 0.35


def make_fp(seed: str, **over) -> Fingerprint:
    base = dict(
        fp_id=f"fp-{seed}",
        canvas_hash=f"canvas-{seed}",
        audio_hash=f"audio-{seed}",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer=f"ANGLE NVIDIA {seed}",
        fonts=["Arial", "Calibri", "Segoe UI", "Consolas"],
        screen_width=2560,
        screen_height=1440,
        device_pixel_ratio=1.0,
        color_depth=24,
        hardware_concurrency=8,
        device_memory=16,
        touch_support=False,
        timezone="America/Argentina/Buenos_Aires",
        languages=["es-AR", "es"],
        media_queries={"dark": True, "pointer_fine": True},
        plugins=[],
        voices=["Microsoft Sabina"],
        do_not_track=None,
        webrtc_public_ips=None,
        ua_data={"platform": "Windows"},
    )
    base.update(over)
    return Fingerprint(**base)


def make_net(ua: str = "Mozilla/5.0 Chrome/120.0.0.0", ip: str = "200.1.1.5", net: str = "200.1.1.0/24") -> NetworkInfo:
    return NetworkInfo(ip=ip, ip_network=net, user_agent=ua)


def ident(nick: str, fp: Fingerprint, net: NetworkInfo) -> Identity:
    return Identity(nickname=nick, avatar="🙂", fingerprint=fp, network=net)


def _population() -> list[Identity]:
    a = ident("ana", make_fp("A"), make_net("Mozilla/5.0 Chrome/120.0.0.0", "200.1.1.5", "200.1.1.0/24"))
    b = ident(
        "beto",
        make_fp("B", webgl_renderer="ANGLE AMD B", screen_width=1366, screen_height=768, fonts=["Arial"]),
        make_net("Mozilla/5.0 Firefox/121.0", "190.2.2.2", "190.2.2.0/24"),
    )
    c = ident(
        "caro",
        make_fp("C", webgl_renderer="Apple M2", timezone="Europe/Madrid", fonts=["Helvetica", "Menlo"]),
        make_net("Mozilla/5.0 Safari/17.0", "88.8.8.8", "88.8.8.0/24"),
    )
    return [a, b, c]


def test_same_browser_is_recognized():
    pop = _population()
    # Visitante idéntico a "ana" (mismo navegador y equipo).
    res = identify(make_fp("A"), make_net(), pop, THRESHOLD)
    assert res.recognized
    assert res.best.nickname == "ana"
    assert res.best.browser_score > 0.8
    assert res.best.device_score > 0.8


def test_cross_browser_recognized_by_device_level():
    pop = _population()
    # Misma persona que "ana", pero ahora en Firefox: canvas/audio/UA cambian,
    # pero GPU, pantalla, fuentes, zona horaria e IP son los mismos.
    visitor_fp = make_fp(
        "A",
        canvas_hash="otro-canvas",
        audio_hash="otro-audio",
        fp_id="fp-A2",
    )
    visitor_net = make_net("Mozilla/5.0 Firefox/121.0", "200.1.1.5", "200.1.1.0/24")
    res = identify(visitor_fp, visitor_net, pop, THRESHOLD)
    assert res.recognized
    assert res.best.nickname == "ana"
    assert res.best.device_score > 0.7  # el dispositivo lo delata
    assert res.best.browser_score < res.best.device_score  # el navegador no coincide


def test_unknown_visitor_not_recognized():
    pop = _population()
    stranger_fp = make_fp(
        "Z",
        webgl_renderer="Intel UHD raro",
        screen_width=1024,
        screen_height=600,
        fonts=["FuenteExotica"],
        timezone="Asia/Tokyo",
        languages=["ja"],
        ua_data={"platform": "Linux"},
    )
    stranger_net = make_net("Mozilla/5.0 Chrome/119.0.0.0", "5.5.5.5", "5.5.5.0/24")
    res = identify(stranger_fp, stranger_net, pop, THRESHOLD)
    assert not res.recognized
    assert res.best is None
    # Igual devuelve top (ranking), aunque ninguno supere el umbral.
    assert len(res.top) == 3


def test_hardware_twins_canvas_breaks_the_tie():
    # Dos personas con el MISMO hardware (gemelos): mismos atributos de
    # dispositivo. El canvas (navegador) desempata. Es un límite real: sin el
    # canvas, el dispositivo solo daría un falso positivo.
    twin1 = ident("gemelo1", make_fp("T", canvas_hash="canvas-1", audio_hash="audio-1"), make_net())
    twin2 = ident("gemelo2", make_fp("T", canvas_hash="canvas-2", audio_hash="audio-2"), make_net())
    pop = [twin1, twin2]
    visitor_fp = make_fp("T", canvas_hash="canvas-1", audio_hash="audio-1")
    res = identify(visitor_fp, make_net(), pop, THRESHOLD)
    assert res.recognized
    assert res.best.nickname == "gemelo1"
    # Ambos tienen device_score alto (mismo equipo): el falso positivo de
    # dispositivo existe, por eso el canvas importa.
    assert res.top[0].device_score > 0.7 and res.top[1].device_score > 0.7


def test_rare_value_weighs_more_than_common_value():
    # En una población donde TODOS comparten la zona horaria pero cada uno tiene
    # un renderer único, coincidir el renderer debe aportar más bits que
    # coincidir la zona horaria.
    pop = [
        ident("u1", make_fp("1", webgl_renderer="GPU-1"), make_net(ip="1.1.1.1", net="1.1.1.0/24")),
        ident("u2", make_fp("2", webgl_renderer="GPU-2"), make_net(ip="2.2.2.2", net="2.2.2.0/24")),
        ident("u3", make_fp("3", webgl_renderer="GPU-3"), make_net(ip="3.3.3.3", net="3.3.3.0/24")),
    ]
    counts = matching._population_counts(pop)
    n = len(pop)
    # renderer "GPU-1": aparece 1 vez (raro). timezone: aparece en los 3 (común).
    renderer_spec = next(s for s in matching.SPECS if s.name == "webgl_renderer")
    tz_spec = next(s for s in matching.SPECS if s.name == "timezone")
    bits_renderer = matching._effective_bits(renderer_spec, "GPU-1", counts, n)
    bits_tz = matching._effective_bits(tz_spec, "America/Argentina/Buenos_Aires", counts, n)
    assert bits_renderer > bits_tz


def test_scales_from_small_to_large_population():
    # El mismo atributo raro debe seguir aportando bits razonables con N=3 y N=300.
    spec = next(s for s in matching.SPECS if s.name == "webgl_renderer")
    small = [ident(f"u{i}", make_fp(str(i), webgl_renderer=f"GPU-{i}"), make_net(ip=f"10.0.0.{i}", net=f"10.0.0.0/24")) for i in range(3)]
    large = [ident(f"u{i}", make_fp(str(i), webgl_renderer=f"GPU-{i}"), make_net(ip=f"10.0.{i // 256}.{i % 256}", net="10.0.0.0/24")) for i in range(300)]
    bits_small = matching._effective_bits(spec, "GPU-0", matching._population_counts(small), 3)
    bits_large = matching._effective_bits(spec, "GPU-0", matching._population_counts(large), 300)
    # En ambos casos un renderer único aporta varios bits (no colapsa a 0).
    assert bits_small > 2.0
    assert bits_large > 2.0
