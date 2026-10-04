"""worker 运行器：循环选择、启动校验、停机流程与命令行解析。"""

import asyncio
import os
import signal

import pytest

from main import _parse_args
from platforms import events, lifecycle
from platforms.config import Settings
from platforms.contract import BackgroundLoop, ModuleSpec
from platforms.worker import runner
from platforms.worker.runner import WorkerConfigError, run_worker, select_loops


async def _noop(ctx) -> None:
    return None


def _spec(name: str, loops=(), **kwargs) -> ModuleSpec:
    return ModuleSpec(name=name, title=name, loops=loops, **kwargs)


def _settings(**kwargs) -> Settings:
    return Settings(**{"enabled_modules": [], **kwargs})


@pytest.fixture
def install_modules(monkeypatch):
    async def dispose():
        return None

    monkeypatch.setattr(lifecycle, "dispose_engine", dispose)

    def install(*specs: ModuleSpec) -> None:
        monkeypatch.setattr(runner, "load_modules", lambda names, package="modules": list(specs))

    yield install
    events.clear()


def _modules() -> list[ModuleSpec]:
    return [
        _spec("base", (BackgroundLoop("base_job", _noop),)),
        _spec("demo", (BackgroundLoop("a", _noop), BackgroundLoop("b", _noop)), depends_on=("base",)),
    ]


def test_selects_only_target_module_loops():
    selected = select_loops(_modules(), ["demo"], [])
    assert [(module, loop.name) for module, loop in selected] == [("demo", "a"), ("demo", "b")]


def test_filters_by_loop_names():
    selected = select_loops(_modules(), ["demo"], ["b"])
    assert [(module, loop.name) for module, loop in selected] == [("demo", "b")]


def test_rejects_unknown_loop_name():
    with pytest.raises(WorkerConfigError, match="不存在循环"):
        select_loops(_modules(), ["demo"], ["missing"])


def test_rejects_loop_names_with_multiple_modules():
    with pytest.raises(WorkerConfigError, match="单个模块"):
        select_loops(_modules(), ["demo", "base"], ["a"])


def test_rejects_module_without_loops():
    with pytest.raises(WorkerConfigError, match="没有可运行"):
        select_loops([_spec("empty")], ["empty"], [])


async def test_refuses_module_not_in_enabled_modules():
    with pytest.raises(WorkerConfigError, match="ENABLED_MODULES"):
        await run_worker(_settings(enabled_modules=["other"]), ["demo"])


async def test_runs_lifecycle_around_loops_and_exits_when_all_finish(install_modules):
    calls = []

    async def startup():
        calls.append("startup")

    async def shutdown():
        calls.append("shutdown")

    async def job(ctx):
        calls.append(f"{ctx.module}.{ctx.name}")

    install_modules(_spec("demo", (BackgroundLoop("job", job),), on_startup=startup, on_shutdown=shutdown))
    await asyncio.wait_for(run_worker(_settings(), ["demo"]), 2)
    assert calls == ["startup", "demo.job", "shutdown"]


async def test_sigterm_stops_loops_gracefully(install_modules):
    stopped = []

    async def job(ctx):
        while await ctx.sleep(10):
            pass
        stopped.append(ctx.name)

    install_modules(_spec("demo", (BackgroundLoop("job", job),)))
    asyncio.get_running_loop().call_later(0.1, os.kill, os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(run_worker(_settings(), ["demo"]), 2)
    assert stopped == ["job"]


async def test_loop_ignoring_stop_is_cancelled_after_timeout(install_modules):
    cancelled = []

    async def stubborn(ctx):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(ctx.name)
            raise

    install_modules(_spec("demo", (BackgroundLoop("stubborn", stubborn, stop_timeout=0.1),)))
    asyncio.get_running_loop().call_later(0.1, os.kill, os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(run_worker(_settings(), ["demo"]), 2)
    assert cancelled == ["stubborn"]


async def test_singleton_loop_runs_through_run_exclusive(install_modules, monkeypatch):
    exclusive = []
    ran = []

    async def fake(ctx, run):
        exclusive.append(ctx.name)
        await run(ctx)

    async def job(ctx):
        ran.append(ctx.name)

    monkeypatch.setattr(runner, "run_exclusive", fake)
    install_modules(
        _spec("demo", (BackgroundLoop("single", job, singleton=True), BackgroundLoop("plain", job)))
    )
    await asyncio.wait_for(run_worker(_settings(), ["demo"]), 2)
    assert exclusive == ["single"]
    assert sorted(ran) == ["plain", "single"]


def test_cli_defaults_to_api():
    assert _parse_args([]).command is None


def test_cli_parses_worker_arguments():
    args = _parse_args(["worker", "a,b", "--loops", "x, y"])
    assert args.command == "worker"
    assert args.modules == ["a", "b"]
    assert args.loops == ["x", "y"]
