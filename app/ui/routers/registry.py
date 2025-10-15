from collections.abc import Iterable
from typing import Callable

from aiogram import Dispatcher

from .context import ManagementRouterContext

RouteRegistrar = Callable[[Dispatcher, ManagementRouterContext], None]


def register_management_routes(
    dispatcher: Dispatcher,
    context: ManagementRouterContext,
    registrars: Iterable[RouteRegistrar] | None = None,
) -> None:
    """
    Register all management bot routes using the provided dispatcher.

    Parameters
    ----------
    dispatcher:
        The aiogram dispatcher that owns the handler registrations.
    context:
        Shared dependencies for downstream router functions.
    registrars:
        Optional iterable of custom registrar callables. When omitted, the
        default set will be imported lazily to avoid circular dependencies.
    """

    if registrars is None:
        registrars = tuple(_default_registrars())

    for registrar in registrars:
        registrar(dispatcher, context)


def _default_registrars() -> Iterable[RouteRegistrar]:
    """
    Yield the built-in registrar functions.

    Keeping the imports inside this generator prevents circular imports while
    the refactor is still in flight.
    """

    from . import auto_click  # noqa: WPS433
    from . import command_forwarding  # noqa: WPS433
    from . import core  # noqa: WPS433
    from . import curate_alpha  # noqa: WPS433
    from . import dynamic_reply  # noqa: WPS433
    from . import groups  # noqa: WPS433
    from . import menu  # noqa: WPS433
    from . import notifications  # noqa: WPS433
    from . import pnl  # noqa: WPS433
    from . import schedules  # noqa: WPS433
    from . import settings  # noqa: WPS433
    from . import sources  # noqa: WPS433
    from . import templates  # noqa: WPS433
    from . import userbots  # noqa: WPS433
    from . import gain_alerts  # noqa: WPS433

    yield core.register
    yield menu.register
    yield groups.register
    yield userbots.register
    yield sources.register
    yield pnl.register
    yield command_forwarding.register
    yield notifications.register
    yield auto_click.register
    yield dynamic_reply.register
    yield curate_alpha.register
    yield templates.register
    yield schedules.register
    yield settings.register
    yield gain_alerts.register
