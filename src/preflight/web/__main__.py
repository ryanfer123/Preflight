"""Start Preflight on loopback; Docker overrides the host explicitly."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("preflight.web.app:application", factory=True, host="127.0.0.1", port=8000)
