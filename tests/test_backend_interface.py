"""Both DockerBackend implementations must implement the whole interface
(homeserver-docker-backend skill: never let them partially diverge)."""

from __future__ import annotations

import inspect

import homeserver as hs


def test_both_backends_implement_every_abstract_method():
    for cls in (hs.SubprocessBackend, hs.PythonOnWhalesBackend):
        assert not getattr(cls, "__abstractmethods__", set()), f"{cls.__name__} missing {cls.__abstractmethods__}"


def test_backend_signatures_match_the_interface():
    abstract = {n for n, f in inspect.getmembers(hs.DockerBackend, inspect.isfunction)
                if getattr(f, "__isabstractmethod__", False)}
    for cls in (hs.SubprocessBackend, hs.PythonOnWhalesBackend):
        for name in abstract:
            want = list(inspect.signature(getattr(hs.DockerBackend, name)).parameters)
            got = list(inspect.signature(getattr(cls, name)).parameters)
            assert got == want, f"{cls.__name__}.{name}{got} != interface {want}"


def test_no_direct_docker_calls_outside_the_backends():
    """subprocess may only build docker/compose commands inside the two
    backend classes; elsewhere it's limited to host tools (fuser, wsl, ip...)."""
    src = (hs.BASE_DIR / "homeserver.py").read_text()
    start = src.index("class SubprocessBackend")
    end = src.index("def create_backend")
    outside = src[:start] + src[end:]
    assert "[RUNTIME" not in outside and '"docker", "exec"' not in outside, \
        "docker invoked directly outside SubprocessBackend/PythonOnWhalesBackend"
