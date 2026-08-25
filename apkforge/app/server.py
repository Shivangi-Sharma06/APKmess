from __future__ import annotations

from pathlib import Path

from flask import Flask

from .routes import bp


def create_app() -> Flask:
    app = Flask(__name__)
    root = Path(__file__).resolve().parents[2]
    app.config.update(
        MAX_CONTENT_LENGTH=250 * 1024 * 1024,
        APKFORGE_ROOT=root,
        APKFORGE_WORKSPACE=root / "workspace",
        APKFORGE_OUTPUT=root / "output",
    )
    app.register_blueprint(bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

