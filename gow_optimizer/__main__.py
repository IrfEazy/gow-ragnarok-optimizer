"""python -m gow_optimizer — start the web UI."""

import logging

from gow_optimizer.web import app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app.run(debug=True, port=5000)
