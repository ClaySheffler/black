import asyncio
from functools import partial
from typing import Optional

import black
import click


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "-l",
    "--line-length",
    type=int,
    default=black.DEFAULT_LINE_LENGTH,
    help="How many character per line to allow.",
    show_default=True,
)
@click.option(
    "--py36",
    is_flag=True,
    help=(
        "Allow using Python 3.6-only syntax on all input files.  This will put "
        "trailing commas in function signatures and calls also after *args and "
        "**kwargs.  [default: per-file auto-detection]"
    ),
)
@click.option(
    "--pyi",
    is_flag=True,
    help=(
        "Format all input files like typing stubs regardless of file extension "
        "(useful when piping source on standard input)."
    ),
)
@click.option(
    "-S",
    "--skip-string-normalization",
    is_flag=True,
    help="Don't normalize string quotes or prefixes.",
)
@click.option(
    "--fast/--safe",
    is_flag=True,
    help="If --fast given, skip temporary sanity checks. [default: --safe]",
)
@click.option(
    "--config",
    type=click.Path(
        exists=False, file_okay=True, dir_okay=False, readable=True, allow_dash=False
    ),
    is_eager=True,
    callback=black.read_pyproject_toml,
    help="Read configuration from PATH.",
)
@click.option(
    "--bind-host", type=str, help="Address to bind the server to.", default="localhost"
)
@click.option("--bind-port", type=int, help="Port to listen on", default=45484)
@click.version_option(version=black.__version__)
@click.pass_context
def main(
    ctx: click.Context,
    line_length: int,
    fast: bool,
    pyi: bool,
    py36: bool,
    skip_string_normalization: bool,
    config: Optional[str],
    bind_host: str,
    bind_port: int,
) -> None:
    mode = black.FileMode.from_configuration(
        py36=py36, pyi=pyi, skip_string_normalization=skip_string_normalization
    )
    loop = asyncio.get_event_loop()
    req_handler = partial(new_req, line_length=line_length, mode=mode, fast=fast)
    try:
        server = loop.run_until_complete(
            asyncio.start_server(req_handler, host=bind_host, port=bind_port)
        )
        ver = black.__version__
        black.out(f"blackd version {ver} listening on {bind_host} port {bind_port}")
        loop.run_forever()
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())


async def new_req(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    line_length: int,
    fast: bool,
    mode: black.FileMode,
) -> None:
    try:
        peer = writer.get_extra_info("peername")
        req_bytes = await reader.read()
        black.out(f"[{peer}] got {len(req_bytes)} bytes")
        req_str = req_bytes.decode("utf8")
        formatted = black.format_file_contents(
            req_str, line_length=line_length, fast=fast, mode=mode
        ).encode("utf8")
        writer.write(b"OK\n" + formatted)
        black.out(f"[{peer}] format done, sending {len(formatted)} bytes")
    except black.NothingChanged:
        writer.write(b"OK NO CHANGE\n")
        black.out(f"[{peer}] format done, no changes")
    except Exception as e:
        writer.write(b"ERROR\n" + str(e).encode("utf8"))
        black.out(f"[{peer}] error while formatting: {e}")
    finally:
        await writer.drain()
        writer.close()


if __name__ == "__main__":
    black.patch_click()
    main()
