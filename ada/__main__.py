"""Allow ``python -m ada`` to start the server.

@decision DEC-CORE-004
@title load_dotenv bridges .env into os.environ before startup
@status accepted
@rationale pydantic-settings' DotEnvSettingsSource reads .env values into the
    Settings model only — it never calls os.environ.__setitem__, so every
    os.environ.get() call in the codebase (ClaudeConfig.api_key,
    OpenAICompatConfig.api_key, AuthConfig.secret_key, LLM factory) sees an
    empty string even when the key is present in .env.  Calling
    load_dotenv(override=False) here — before main() touches os.environ —
    populates the real process environment from the repo-root .env file.
    override=False preserves the existing "export in shell" workaround: a
    shell-exported variable always wins over .env.  The call is placed in
    __main__.py (the ``python -m ada`` entry point) rather than main.py so
    that importing ada.main in tests does not have a side effect of loading a
    developer .env file.
"""

from dotenv import load_dotenv

# Bridge .env into os.environ BEFORE any code reads os.environ.
# override=False means shell-exported vars take precedence over .env values.
load_dotenv(override=False)

from ada.main import main  # noqa: E402 — import after load_dotenv is intentional

main()
