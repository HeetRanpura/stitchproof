"""Tiny builders so tests read like patterns."""
from stitchproof.schema import (
    IntoOne,
    LineProgram,
    Repeat,
    Skip,
    Start,
    Together,
    TurningChain,
    Work,
    WorkRest,
)


def sc(n=1, stitch="sc"):
    return Work(stitch=stitch, n=n)


def inc(k=2, stitch="sc"):
    return IntoOne(stitch=stitch, k=k)


def dec(k=2, stitch="sc"):
    return Together(stitch=stitch, k=k)


def rest(stitch="sc", leave=0):
    return WorkRest(stitch=stitch, leave=leave)


def skip(n=1):
    return Skip(n=n)


def turn(n=1, counts=False):
    return TurningChain(n=n, counts_as_stitch=counts)


def rep(times, *body):
    return Repeat(times=times, body=list(body))


def rnd(label, *ops, stated=None, kind="round", start=None, rng=None, must_use_all=True):
    rs, re_ = rng if rng else (None, None)
    return LineProgram(
        kind=kind,
        label=label,
        range_start=rs,
        range_end=re_,
        start=start or Start(),
        ops=list(ops),
        stated_count=stated,
        must_use_all=must_use_all,
    )


def row(label, *ops, stated=None, start=None, rng=None, must_use_all=True):
    return rnd(label, *ops, stated=stated, kind="row", start=start, rng=rng, must_use_all=must_use_all)


def mr(label, n, stated=None):
    return rnd(label, sc(n), stated=stated, start=Start(type="magic_ring"))


def chain(n, label=None, stated=None):
    return LineProgram(kind="foundation", label=label, start=Start(type="chain", chain_count=n), stated_count=stated)


def note():
    return LineProgram(kind="note")


def unsupported(reason="chain spaces", stated=None, label=None):
    return LineProgram(kind="unsupported", label=label, unsupported_reason=reason, stated_count=stated)
